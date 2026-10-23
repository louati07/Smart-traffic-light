"""Priority Engine: Arbitrates detections into safe sequenced commands.

Contract (PLAN.md Section 4.4, Section 5.1, Section 8 P3):
- Maps approach (N, S -> NS; E, W -> EW).
- Consumes confirmed detections.
- Issues PRIORITY command (increments seq strictly, writes to Firebase, logs to Mongo).
- Automatically releases via CLEAR when no confirmed detection for release_after_s (default 3.0s).
- Enforces priority cooldown (default 2.0s).
- Handles conflicts: first-come wins, second queued (max wait 15.0s).
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
        self.active_priority_axis: Axis | None = None
        self.active_approach: str | None = None
        self.active_vehicle_class: str | None = None
        self.active_event_id: str | None = None
        self.active_priority_started_s: float = 0.0
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
            # If priority already active for this axis, refresh detection timestamp
            if self.active_priority_axis == axis:
                self.last_detection_time_s = now
                return None

            # If priority active for the opposite axis, queue conflict
            if self.active_priority_axis is not None and self.active_priority_axis != axis:
                if not any(q.axis == axis for q in self.conflict_queue):
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
            )

        # Update engine state
        self.active_priority_axis = axis
        self.active_approach = approach
        self.active_vehicle_class = vehicle_class
        self.active_priority_started_s = now_s
        self.last_detection_time_s = now_s
        self.active_event_id = str(uuid.uuid4())

        # Write to Firebase
        self.firebase.set_command(cmd_payload, self.intersection_id)

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
    ) -> dict[str, Any]:
        """Manual override from dashboard."""
        now = now_s if now_s is not None else time.time()
        with self._lock:
            self.seq += 1
            cmd_upper = cmd.upper()
            axis_upper = axis.upper() if axis else None

            cmd_payload: dict[str, Any] = {
                "seq": self.seq,
                "cmd": cmd_upper,
                "ttl_s": ttl_s,
                "issued_by": issued_by,
            }
            if axis_upper:
                cmd_payload["axis"] = axis_upper

            if self.hmac_secret:
                cmd_payload["sig"] = sign_command(
                    self.hmac_secret,
                    self.seq,
                    cmd_upper,
                    axis_upper,
                    ttl_s,
                )

            if cmd_upper == "PRIORITY" and axis_upper:
                self.active_priority_axis = Axis(axis_upper)
                self.active_approach = axis_upper[0]
                self.active_vehicle_class = "manual"
                self.active_priority_started_s = now
                self.last_detection_time_s = now
            elif cmd_upper == "CLEAR":
                self._clear_active_priority(now, outcome="manual_cleared")

            self.firebase.set_command(cmd_payload, self.intersection_id)
            self.mongo.insert_command(cmd_payload)
            return cmd_payload

    def _clear_active_priority(self, now_s: float, outcome: str = "completed") -> dict[str, Any] | None:
        if self.active_priority_axis is None:
            return None

        self.seq += 1
        cmd_payload: dict[str, Any] = {
            "seq": self.seq,
            "cmd": "CLEAR",
            "ttl_s": self.command_ttl_s,
            "issued_by": "priority-engine",
        }
        if self.hmac_secret:
            cmd_payload["sig"] = sign_command(
                self.hmac_secret,
                self.seq,
                "CLEAR",
                None,
                self.command_ttl_s,
            )

        if self.active_event_id:
            self.mongo.update_event(
                self.active_event_id,
                {
                    "released_at": datetime.datetime.now(datetime.UTC).isoformat(),
                    "outcome": outcome,
                },
            )

        self.active_priority_axis = None
        self.active_approach = None
        self.active_vehicle_class = None
        self.active_event_id = None
        self.cooldown_until_s = now_s + self.cooldown_s

        self.firebase.set_command(cmd_payload, self.intersection_id)
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
                elapsed_since_det = now - self.last_detection_time_s
                if elapsed_since_det >= self.release_after_s:
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
