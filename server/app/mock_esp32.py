"""Mock ESP32 Firmware Digital Twin.

Contract (PLAN.md Section 5.1, Section 8 P3, Section 9):
- Runs light_fsm locally using millis() equivalent.
- Reads /intersections/{id}/command every POLL_MS (default 700ms).
- Observes /intersections/{id}/heartbeat.
- Writes /intersections/{id}/state on phase transitions and at least every 2000ms.
- Verifies HMAC signature if HMAC_ENFORCE is True.
"""

import logging
import threading
import time
from typing import Any

from server.app.clients.firebase import FirebaseClientBase, get_firebase_client
from server.app.config import settings
from server.app.core.light_fsm import (
    FSMCommand,
    FSMTimings,
    LightFSM,
    Phase,
)
from server.app.core.signing import verify_command_signature

logger = logging.getLogger(__name__)


class MockESP32Twin:
    """Software twin emulating Wokwi ESP32 firmware."""

    def __init__(
        self,
        firebase_client: FirebaseClientBase | None = None,
        intersection_id: str = "i1",
        poll_interval_s: float | None = None,
        hmac_secret: str = "",
        hmac_enforce: bool = False,
    ) -> None:
        self.firebase = firebase_client or get_firebase_client(
            mode=settings.firebase_mode,
            db_url=settings.firebase_db_url,
            db_secret=settings.firebase_db_secret,
        )
        self.intersection_id = intersection_id
        self.poll_interval_s = (
            poll_interval_s
            if poll_interval_s is not None
            else float(settings.timings.get("poll_ms", 1000)) / 1000.0
        )
        self.hmac_secret = hmac_secret or settings.hmac_secret
        self.hmac_enforce = hmac_enforce or settings.hmac_enforce

        raw_timings = settings.timings
        self.fsm_timings = FSMTimings(
            green_ms=raw_timings.get("green_ms", 10000),
            yellow_ms=raw_timings.get("yellow_ms", 3000),
            all_red_ms=raw_timings.get("all_red_ms", 2000),
            priority_yellow_ms=raw_timings.get("priority_yellow_ms", 2000),
            priority_all_red_ms=raw_timings.get("priority_all_red_ms", 1000),
            min_green_ms=raw_timings.get("min_green_ms", 5000),
            priority_max_ms=raw_timings.get("priority_max_ms", 30000),
            heartbeat_timeout_ms=raw_timings.get("heartbeat_timeout_ms", 10000),
            command_ttl_s=raw_timings.get("command_ttl_s", 15),
        )

        self.fsm = LightFSM(self.fsm_timings, initial_now_ms=0)
        self.running = False
        self._thread: threading.Thread | None = None

        self.start_epoch_ms = int(time.time() * 1000)
        self.last_phase: Phase | None = None
        self.last_mode: Any = None
        self.last_seq: int = 0
        self.last_state_write_ms: int = 0
        self.last_command_poll_ms: int = 0

    def get_local_now_ms(self) -> int:
        return int(time.time() * 1000) - self.start_epoch_ms

    def step(self, now_ms: int | None = None) -> dict[str, Any]:
        """Execute a single polling and FSM step."""
        current_ms = now_ms if now_ms is not None else self.get_local_now_ms()

        # 1. Update heartbeat from mailbox
        hb_counter = self.firebase.get_heartbeat(self.intersection_id)
        if hb_counter > 0:
            self.fsm.record_heartbeat(hb_counter, now_ms=current_ms)

        # 2. Poll for new command
        poll_interval_ms = int(self.poll_interval_s * 1000)
        if current_ms - self.last_command_poll_ms >= poll_interval_ms:
            self.last_command_poll_ms = current_ms
            cmd_data = self.firebase.get_command(self.intersection_id)
            if cmd_data and isinstance(cmd_data, dict):
                seq = cmd_data.get("seq", 0)
                if seq > self.fsm.last_seq:
                    cmd_str = cmd_data.get("cmd", "")
                    axis_str = cmd_data.get("axis")
                    approach = cmd_data.get("approach")
                    ttl_s = cmd_data.get("ttl_s", 15)
                    sig = cmd_data.get("sig")

                    # HMAC Signature check (Section 5.4 P2)
                    if self.hmac_enforce:
                        valid_sig = verify_command_signature(
                            self.hmac_secret,
                            sig,
                            seq,
                            cmd_str,
                            axis_str,
                            ttl_s,
                            approach=approach,
                        )
                        if not valid_sig:
                            logger.warning("MockESP32 rejected command seq=%d: invalid signature", seq)
                            self.fsm.rejected_cmds += 1
                            cmd_data = None

                    if cmd_data:
                        fsm_cmd = FSMCommand(
                            seq=seq,
                            cmd=cmd_str,
                            axis=axis_str,
                            ttl_s=ttl_s,
                            sig=sig,
                            approach=approach,
                        )
                        self.fsm.apply_command(fsm_cmd, now_ms=current_ms)

        # 3. Advance FSM clock
        self.fsm.tick(current_ms)

        # 4. Check if state should be pushed to mailbox
        state = self.fsm.get_state()
        state_dict = state.to_dict()
        state_dict["controller_id"] = "mock"

        phase_changed = (self.last_phase != self.fsm.phase)
        mode_changed = (self.last_mode != self.fsm.mode)
        seq_changed = (self.last_seq != self.fsm.last_seq)
        time_elapsed = (current_ms - self.last_state_write_ms >= 2000)

        if phase_changed or mode_changed or seq_changed or time_elapsed:
            self.firebase.set_state(state_dict, self.intersection_id)
            self.last_phase = self.fsm.phase
            self.last_mode = self.fsm.mode
            self.last_seq = self.fsm.last_seq
            self.last_state_write_ms = current_ms

        return state_dict

    def start(self) -> None:
        """Start the background execution loop."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("MockESP32Twin started in background")

    def stop(self) -> None:
        """Stop the background execution loop."""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("MockESP32Twin stopped")

    def _run_loop(self) -> None:
        while self.running:
            try:
                self.step()
            except Exception as e:
                logger.error("Error in MockESP32 loop: %s", e)
            time.sleep(self.poll_interval_s)


def run_standalone() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    twin = MockESP32Twin()
    print("🚦 Mock ESP32 Digital Twin running. Press Ctrl+C to stop.")
    try:
        twin.start()
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping Mock ESP32 Twin...")
        twin.stop()


if __name__ == "__main__":
    run_standalone()
