"""Priority Engine: Arbitrates detections into safe sequenced commands.

Contract (PLAN.md Section 4.4, Section 5.1, Section 8 P3):
- Maps each approach to its axis and includes both values in PRIORITY commands.
- Consumes confirmed detections.
- Issues PRIORITY command (increments seq strictly, writes to Firebase, logs to Mongo).
- Waits for the controller to report the requested approach green before releasing after detections stop for release_after_s (default 3.0s).
- Enforces priority cooldown (default 2.0s).
- Handles conflicts between approaches: first-come wins, others queue (max wait 15.0s).
- Signs command if hmac_secret is provided.
"""

import datetime
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from server.app.clients.firebase import FirebaseClientBase
from server.app.clients.mongo import MongoClientBase
from server.app.core.light_fsm import Axis
from server.app.core.signing import sign_command

logger = logging.getLogger(__name__)


@dataclass
class ConfirmedDetection:
    camera_id: str
    approach: str
    vehicle_class: str
    confidence: float
    bbox_area_ratio: float
    frame_id: int
    source_ts_ms: int
    received_at_s: float


@dataclass
class QueuedConflict:
    axis: Axis
    approach: str
    vehicle_class: str
    requested_at_s: float
    max_wait_s: float = 15.0


class PriorityEngine:
    """Orchestrates traffic light priority commands from detection inputs."""

    def __init__(
        self,
        firebase_client: FirebaseClientBase,
        mongo_client: MongoClientBase,
        intersection_id: str = "i1",
        release_after_s: float = 3.0,
        cooldown_s: float = 2.0,
        conflict_max_wait_s: float = 15.0,
        command_ttl_s: int = 15,
        hmac_secret: str = "",
        hmac_enforce: bool = False,
    ) -> None:
        self.firebase = firebase_client
        self.mongo = mongo_client
        self.intersection_id = intersection_id
        self.release_after_s = release_after_s
        self.cooldown_s = cooldown_s
        self.conflict_max_wait_s = conflict_max_wait_s
        self.command_ttl_s = command_ttl_s
        self.hmac_secret = hmac_secret
        self.hmac_enforce = hmac_enforce

        self._lock = threading.Lock()
        self.seq: int = 0
        try:
            last_command = self.firebase.get_command(self.intersection_id) or {}
            last_state = self.firebase.get_state(self.intersection_id) or {}
            self.seq = max(
                int(last_command.get("seq", 0) or 0),
                int(last_state.get("last_seq", 0) or 0),
            )
        except Exception as exc:
            logger.warning("Could not restore command sequence from mailbox: %s", exc)
        self.active_priority_axis: Axis | None = None
        self.active_priority_approach: str | None = None
        self.active_priority_seq: int | None = None
        self.active_approach: str | None = None
        self.active_vehicle_class: str | None = None
        self.active_event_id: str | None = None
        self.active_priority_started_s: float = 0.0
        self.active_priority_granted_s: float | None = None
        self.active_priority_ttl_s: int = command_ttl_s
        self.last_detection_time_s: float = 0.0
        self.cooldown_until_s: float = 0.0

        self.conflict_queue: list[QueuedConflict] = []

    @staticmethod
    def approach_to_axis(approach: str) -> Axis | None:
        app = approach.upper().strip()
        if app in ("N", "S"):
            return Axis.NS
        if app in ("E", "W"):
            return Axis.EW
        return None

    def handle_detection(self, det: ConfirmedDetection, now_s: float | None = None) -> dict[str, Any] | None:
        """Process an incoming confirmed detection."""
        now = now_s if now_s is not None else time.time()
        axis = self.approach_to_axis(det.approach)
        if not axis:
            logger.warning("Unknown approach: %s", det.approach)
            return None

        with self._lock:
            # Only detections from the approach currently receiving green refresh
            # that hold. An opposite approach on the same axis must be queued.
            if self.active_priority_approach == det.approach:
                self.last_detection_time_s = now
                return None

            # The priority phase serves one approach at a time.
            if self.active_priority_axis is not None:
                if not any(q.approach == det.approach for q in self.conflict_queue):
                    self.conflict_queue.append(
                        QueuedConflict(
                            axis=axis,
                            approach=det.approach,
                            vehicle_class=det.vehicle_class,
                            requested_at_s=now,
                            max_wait_s=self.conflict_max_wait_s,
                        )
                    )
                    logger.info("Conflict: Priority already active for %s; queued %s", self.active_priority_axis, axis)
                return None

            # Check cooldown
            if now < self.cooldown_until_s:
                logger.info("Priority on cooldown until %.2f (now %.2f)", self.cooldown_until_s, now)
                return None

            # Issue PRIORITY command
            return self._issue_priority_command(
                axis=axis,
                approach=det.approach,
                vehicle_class=det.vehicle_class,
                now_s=now,
            )

    def _issue_priority_command(
        self,
        axis: Axis,
        approach: str,
        vehicle_class: str,
        now_s: float,
    ) -> dict[str, Any]:
        self.seq += 1
        cmd_type = "PRIORITY"
        axis_str = axis.value

        cmd_payload: dict[str, Any] = {
            "seq": self.seq,
            "cmd": cmd_type,
            "axis": axis_str,
            "approach": approach,
            "ttl_s": self.command_ttl_s,
            "issued_by": "priority-engine",
        }

        if self.hmac_secret:
            cmd_payload["sig"] = sign_command(
                self.hmac_secret,
                self.seq,
                cmd_type,
                axis_str,
                self.command_ttl_s,
                approach=approach,
            )

        # Publish before committing engine state. A failed write leaves the
        # engine eligible to retry on the next confirmed detection.
        self.firebase.set_command(cmd_payload, self.intersection_id)

        # Update engine state only after the mailbox accepted the command.
        self.active_priority_axis = axis
        self.active_priority_approach = approach
        self.active_approach = approach
        self.active_priority_seq = self.seq
        self.active_vehicle_class = vehicle_class
        self.active_priority_started_s = now_s
        self.active_priority_granted_s = None
        self.active_priority_ttl_s = self.command_ttl_s
        self.last_detection_time_s = now_s
        self.active_event_id = str(uuid.uuid4())

        # Log to Mongo commands and events
        self.mongo.insert_command(cmd_payload)
        self.mongo.insert_event({
            "event_id": self.active_event_id,
            "approach": approach,
            "axis": axis_str,
            "class": vehicle_class,
            "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "released_at": None,
            "light_change_latency_ms": None,
            "outcome": "in_progress",
        })

        logger.info("Issued PRIORITY seq=%d for axis=%s approach=%s", self.seq, axis_str, approach)
        return cmd_payload

    def issue_manual_command(
        self,
        cmd: str,
        axis: str | None = None,
        ttl_s: int = 15,
        issued_by: str = "operator",
        now_s: float | None = None,
        approach: str | None = None,
    ) -> dict[str, Any]:
        """Manual override from dashboard."""
        now = now_s if now_s is not None else time.time()
        with self._lock:
            cmd_upper = cmd.upper()
            axis_upper = axis.upper() if axis else None

            if cmd_upper == "CLEAR":
                return self._clear_active_priority(now, outcome="manual_cleared", issued_by=issued_by)

            approach_upper = approach.upper() if approach else None
            if approach_upper is None and axis_upper:
                approach_upper = "N" if axis_upper == "NS" else "E"
            if approach_upper:
                if approach_upper not in {"N", "E", "S", "W"}:
                    raise ValueError("Approach must be N, E, S, or W")
                approach_axis = "NS" if approach_upper in ("N", "S") else "EW"
                if axis_upper and axis_upper != approach_axis:
                    raise ValueError("Approach must belong to the selected axis")
                axis_upper = approach_axis

            self.seq += 1

            cmd_payload: dict[str, Any] = {
                "seq": self.seq,
                "cmd": cmd_upper,
                "ttl_s": ttl_s,
                "issued_by": issued_by,
            }
            if axis_upper:
                cmd_payload["axis"] = axis_upper
            if approach_upper:
                cmd_payload["approach"] = approach_upper

            if self.hmac_secret:
                cmd_payload["sig"] = sign_command(
                    self.hmac_secret,
                    self.seq,
                    cmd_upper,
                    axis_upper,
                    ttl_s,
                    approach=approach_upper,
                )

            self.firebase.set_command(cmd_payload, self.intersection_id)
            if cmd_upper == "PRIORITY" and axis_upper:
                self.active_priority_axis = Axis(axis_upper)
                self.active_priority_approach = approach_upper
                self.active_approach = approach_upper
                self.active_priority_seq = self.seq
                self.active_vehicle_class = "manual"
                self.active_priority_started_s = now
                self.active_priority_granted_s = None
                self.active_priority_ttl_s = ttl_s
                self.last_detection_time_s = now
            self.mongo.insert_command(cmd_payload)
            return cmd_payload

    def _clear_active_priority(
        self,
        now_s: float,
        outcome: str = "completed",
        issued_by: str = "priority-engine",
    ) -> dict[str, Any]:
        self.seq += 1
        cmd_payload: dict[str, Any] = {
            "seq": self.seq,
            "cmd": "CLEAR",
            "ttl_s": self.command_ttl_s,
            "issued_by": issued_by,
        }
        if self.hmac_secret:
            cmd_payload["sig"] = sign_command(
                self.hmac_secret,
                self.seq,
                "CLEAR",
                None,
                self.command_ttl_s,
            )

        # Keep the active hold intact if the CLEAR write fails; the ticker can
        # retry it rather than losing track of a controller that is still held.
        self.firebase.set_command(cmd_payload, self.intersection_id)

        if self.active_event_id:
            self.mongo.update_event(
                self.active_event_id,
                {
                    "released_at": datetime.datetime.now(datetime.UTC).isoformat(),
                    "outcome": outcome,
                },
            )

        self.active_priority_axis = None
        self.active_priority_approach = None
        self.active_priority_seq = None
        self.active_approach = None
        self.active_vehicle_class = None
        self.active_event_id = None
        self.active_priority_granted_s = None
        self.active_priority_ttl_s = self.command_ttl_s
        self.cooldown_until_s = now_s + self.cooldown_s

        self.mongo.insert_command(cmd_payload)
        logger.info("Issued CLEAR seq=%d (outcome=%s)", self.seq, outcome)
        return cmd_payload

    def tick(self, now_s: float | None = None) -> list[dict[str, Any]]:
        """Periodic tick to check release timeout and resolve conflict queues."""
        now = now_s if now_s is not None else time.time()
        actions: list[dict[str, Any]] = []

        with self._lock:
            # 1. Release active priority if detection has ceased
            if self.active_priority_axis is not None:
                if self.active_vehicle_class == "manual":
                    state = self.firebase.get_state(self.intersection_id) or {}
                    acknowledged = int(state.get("last_seq", 0) or 0) >= (self.active_priority_seq or 0)
                    granted = acknowledged and state.get("priority_approach") == self.active_priority_approach
                    if granted and self.active_priority_granted_s is None:
                        self.active_priority_granted_s = now
                    if self.active_priority_granted_s is not None and now - self.active_priority_granted_s >= self.active_priority_ttl_s:
                        clear_cmd = self._clear_active_priority(now, outcome="auto_released")
                        if clear_cmd:
                            actions.append(clear_cmd)
                    elif self.active_priority_granted_s is None and now - self.active_priority_started_s >= max(self.active_priority_ttl_s + 15, 30):
                        logger.warning("Manual priority seq=%s was not granted before timeout", self.active_priority_seq)
                        clear_cmd = self._clear_active_priority(now, outcome="auto_released")
                        if clear_cmd:
                            actions.append(clear_cmd)
                else:
                    elapsed_since_det = now - self.last_detection_time_s
                    if elapsed_since_det >= self.release_after_s:
                        state = self.firebase.get_state(self.intersection_id) or {}
                        acknowledged = int(state.get("last_seq", 0) or 0) >= (self.active_priority_seq or 0)
                        granted = (
                            acknowledged
                            and state.get("priority_approach") == self.active_priority_approach
                        )
                        command_timed_out = now - self.active_priority_started_s >= self.command_ttl_s + 2.0
                        # Do not cancel a request while the controller is still
                        # completing its mandatory yellow/all-red transition.
                        if granted or command_timed_out:
                            clear_cmd = self._clear_active_priority(now, outcome="auto_released")
                            if clear_cmd:
                                actions.append(clear_cmd)

            # 2. Prune expired conflicts
            valid_queue: list[QueuedConflict] = []
            for item in self.conflict_queue:
                if (now - item.requested_at_s) <= item.max_wait_s:
                    valid_queue.append(item)
                else:
                    logger.warning("Conflict request expired for axis %s", item.axis)
            self.conflict_queue = valid_queue

            # 3. If idle and not in cooldown, service next conflict
            if self.active_priority_axis is None and now >= self.cooldown_until_s and self.conflict_queue:
                next_conflict = self.conflict_queue.pop(0)
                cmd = self._issue_priority_command(
                    axis=next_conflict.axis,
                    approach=next_conflict.approach,
                    vehicle_class=next_conflict.vehicle_class,
                    now_s=now,
                )
                actions.append(cmd)

        return actions
