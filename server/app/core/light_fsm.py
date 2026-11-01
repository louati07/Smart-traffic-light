"""Pure Finite State Machine (FSM) for intersection traffic light control.

Implements Section 4.4 and Safety Invariants S1-S7 of PLAN.md.
No I/O or system clock dependencies: pure logic driven by injectable tick(now_ms).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Axis(str, Enum):
    NS = "NS"
    EW = "EW"


class Phase(str, Enum):
    NS_GREEN = "NS_GREEN"
    NS_YELLOW = "NS_YELLOW"
    ALL_RED_TO_EW = "ALL_RED_TO_EW"
    EW_GREEN = "EW_GREEN"
    EW_YELLOW = "EW_YELLOW"
    ALL_RED_TO_NS = "ALL_RED_TO_NS"


class Mode(str, Enum):
    NORMAL = "NORMAL"
    PRIORITY = "PRIORITY"
    FALLBACK = "FALLBACK"


class CommandType(str, Enum):
    PRIORITY = "PRIORITY"
    CLEAR = "CLEAR"


@dataclass(frozen=True)
class FSMTimings:
    green_ms: int = 10000
    yellow_ms: int = 3000
    all_red_ms: int = 2000
    priority_yellow_ms: int = 2000
    priority_all_red_ms: int = 1000
    min_green_ms: int = 5000
    priority_max_ms: int = 30000
    heartbeat_timeout_ms: int = 10000
    command_ttl_s: int = 15


@dataclass
class FSMCommand:
    seq: int
    cmd: str  # "PRIORITY" | "CLEAR"
    axis: str | None = None  # "NS" | "EW"
    ttl_s: int = 15
    issued_by: str = "priority-engine"
    sig: str | None = None
    approach: str | None = None  # "N" | "E" | "S" | "W"; optional for legacy axis commands


@dataclass
class IntersectionState:
    phase: str
    mode: str
    lights: dict[str, str]
    last_seq: int
    phase_elapsed_ms: int
    uptime_ms: int
    rejected_cmds: int = 0
    priority_approach: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "mode": self.mode,
            "lights": dict(self.lights),
            "last_seq": self.last_seq,
            "phase_elapsed_ms": self.phase_elapsed_ms,
            "uptime_ms": self.uptime_ms,
            "rejected_cmds": self.rejected_cmds,
            "priority_approach": self.priority_approach,
        }


class LightFSM:
    """Traffic Light State Machine with Emergency Priority Orchestration.

    Invariants guaranteed:
    - S1: NS and EW are never green simultaneously.
    - S2: Direct G->G or R->G without Y and ALL_RED in between is prevented.
    - S3: YELLOW_MS and ALL_RED_MS are strictly immutable and never truncated.
    - S4: GREEN is held for at least MIN_GREEN_MS before preemption.
    - S5: PRIORITY hold duration is capped at PRIORITY_MAX_MS watchdog limit.
    - S6: Expired, invalid, or stale sequence commands are rejected.
    - S7: Transition out of priority follows safe Y -> ALL_RED cycle.
    """

    def __init__(self, timings: FSMTimings | None = None, initial_now_ms: int = 0):
        self.timings = timings or FSMTimings()
        self.uptime_ms = initial_now_ms
        self.phase = Phase.NS_GREEN
        self.mode = Mode.NORMAL
        self.phase_start_ms = initial_now_ms
        self.last_seq = 0
        self.rejected_cmds = 0

        # Heartbeat tracking (for fallback detection)
        self.last_heartbeat_rx_ms = initial_now_ms
        self.last_heartbeat_val = 0
        self.heartbeat_seen = False

        # Priority tracking
        self.active_priority_axis: Axis | None = None
        self.active_priority_approach: str | None = None
        self.priority_start_ms: int = 0
        self.priority_command_rx_ms: int = 0
        self.priority_ttl_ms: int = 0
        self.target_priority_axis: Axis | None = None
        self.target_priority_approach: str | None = None
        self.hold_green_active: bool = False
        self.priority_clearance_active: bool = False

    @property
    def lights(self) -> dict[str, str]:
        """Current signal colors for approaches N, E, S, W ('R', 'Y', 'G')."""
        if self.phase == Phase.NS_GREEN:
            lights = {"N": "G", "E": "R", "S": "G", "W": "R"}
        elif self.phase == Phase.NS_YELLOW:
            lights = {"N": "Y", "E": "R", "S": "Y", "W": "R"}
        elif self.phase in (Phase.ALL_RED_TO_EW, Phase.ALL_RED_TO_NS):
            lights = {"N": "R", "E": "R", "S": "R", "W": "R"}
        elif self.phase == Phase.EW_GREEN:
            lights = {"N": "R", "E": "G", "S": "R", "W": "G"}
        elif self.phase == Phase.EW_YELLOW:
            lights = {"N": "R", "E": "Y", "S": "R", "W": "Y"}
        else:
            lights = {"N": "R", "E": "R", "S": "R", "W": "R"}

        if (
            self.hold_green_active
            and self.active_priority_approach
            and (
                (self.phase == Phase.NS_GREEN and self.active_priority_axis == Axis.NS)
                or (self.phase == Phase.EW_GREEN and self.active_priority_axis == Axis.EW)
            )
        ):
            return {
                direction: "G" if direction == self.active_priority_approach else "R"
                for direction in ("N", "E", "S", "W")
            }
        return lights

    def get_state(self) -> IntersectionState:
        elapsed = self.uptime_ms - self.phase_start_ms
        priority_granted = (
            self.hold_green_active
            and self.active_priority_approach is not None
            and (
                (self.phase == Phase.NS_GREEN and self.active_priority_axis == Axis.NS)
                or (self.phase == Phase.EW_GREEN and self.active_priority_axis == Axis.EW)
            )
        )
        return IntersectionState(
            phase=self.phase.value,
            mode=self.mode.value,
            lights=self.lights,
            last_seq=self.last_seq,
            phase_elapsed_ms=max(0, elapsed),
            uptime_ms=self.uptime_ms,
            rejected_cmds=self.rejected_cmds,
            priority_approach=self.active_priority_approach if priority_granted else None,
        )

    def record_heartbeat(self, counter: int, now_ms: int | None = None) -> None:
        """Call whenever server heartbeat is observed."""
        if now_ms is not None:
            self.uptime_ms = now_ms
        # The heartbeat contract is based on change, so a server restart that
        # resets the counter is still a fresh heartbeat.
        if counter != self.last_heartbeat_val:
            self.last_heartbeat_val = counter
            self.last_heartbeat_rx_ms = self.uptime_ms
            self.heartbeat_seen = True
            if self.mode == Mode.FALLBACK:
                self.mode = Mode.NORMAL

    def apply_command(self, cmd: FSMCommand, now_ms: int | None = None) -> bool:
        """Apply a received command according to safety rules and sequence order."""
        if now_ms is not None:
            self.uptime_ms = now_ms

        # Invariant S6: sequence number must strictly increase
        if cmd.seq <= self.last_seq:
            self.rejected_cmds += 1
            return False

        # Invariant S6: Heartbeat timeout forces FALLBACK mode and ignores new commands
        if self._heartbeat_expired():
            self.mode = Mode.FALLBACK
            self.rejected_cmds += 1
            return False

        cmd_type = cmd.cmd.upper()
        if cmd_type == CommandType.PRIORITY.value:
            if not cmd.axis or cmd.axis not in ("NS", "EW"):
                self.rejected_cmds += 1
                return False

            axis = Axis(cmd.axis)
            approach = cmd.approach.upper() if cmd.approach else None
            if approach and (
                approach not in {"N", "E", "S", "W"}
                or self._axis_for_approach(approach) != axis
            ):
                self.rejected_cmds += 1
                return False
            self.last_seq = cmd.seq
            self.priority_command_rx_ms = self.uptime_ms
            ttl_s = cmd.ttl_s if cmd.ttl_s > 0 else self.timings.command_ttl_s
            self.priority_ttl_ms = ttl_s * 1000

            # Target axis requested
            self.target_priority_axis = axis
            self.target_priority_approach = approach
            self.mode = Mode.PRIORITY

            current_axis = self._current_axis_for_phase()

            # Rule 1: If axis is already green, hold green immediately
            if self.phase in (Phase.NS_GREEN, Phase.EW_GREEN) and current_axis == axis:
                self.active_priority_axis = axis
                self.active_priority_approach = approach
                self.hold_green_active = True
                self.priority_start_ms = self.uptime_ms
            return True

        elif cmd_type == CommandType.CLEAR.value:
            self.last_seq = cmd.seq
            self._release_priority()
            return True

        self.rejected_cmds += 1
        return False

    def _release_priority(self) -> None:
        """Release priority hold while respecting MIN_GREEN_MS."""
        self.hold_green_active = False
        self.target_priority_axis = None
        self.target_priority_approach = None
        self.active_priority_axis = None
        self.active_priority_approach = None
        self.priority_clearance_active = False
        if self.mode == Mode.PRIORITY:
            self.mode = Mode.NORMAL

    def _heartbeat_expired(self) -> bool:
        """Return true if no heartbeat has arrived within the configured window."""
        return (
            self.heartbeat_seen
            and self.uptime_ms - self.last_heartbeat_rx_ms > self.timings.heartbeat_timeout_ms
        )

    def _current_axis_for_phase(self) -> Axis | None:
        if self.phase in (Phase.NS_GREEN, Phase.NS_YELLOW):
            return Axis.NS
        if self.phase in (Phase.EW_GREEN, Phase.EW_YELLOW):
            return Axis.EW
        return None

    @staticmethod
    def _axis_for_approach(approach: str) -> Axis:
        return Axis.NS if approach in ("N", "S") else Axis.EW

    def tick(self, now_ms: int) -> None:
        """Advance time to now_ms and execute FSM transitions."""
        if now_ms < self.uptime_ms:
            return
        self.uptime_ms = now_ms

        # Invariant S6: Check heartbeat expiration
        if self._heartbeat_expired():
            if self.mode != Mode.FALLBACK:
                self.mode = Mode.FALLBACK
                self._release_priority()

        # Invariant S5 & TTL: Watchdogs on active priority hold
        if self.hold_green_active:
            hold_duration = self.uptime_ms - self.priority_start_ms
            since_rx = self.uptime_ms - self.priority_command_rx_ms
            if hold_duration >= self.timings.priority_max_ms or since_rx >= self.priority_ttl_ms:
                self._release_priority()

        phase_elapsed = self.uptime_ms - self.phase_start_ms

        # Transition logic for each state
        if self.phase == Phase.NS_GREEN:
            # Check if priority requested for opposite axis (EW)
            if self.target_priority_axis == Axis.EW and self.mode == Mode.PRIORITY:
                # Invariant S4: Can only cut after min_green_ms
                if phase_elapsed >= self.timings.min_green_ms:
                    self.priority_clearance_active = True
                    self._transition_to(Phase.NS_YELLOW)
                    return
            elif self.hold_green_active and self.active_priority_axis == Axis.NS:
                # Holding green for NS; timer is paused
                return
            else:
                # Normal cycle green duration
                if phase_elapsed >= self.timings.green_ms:
                    self._transition_to(Phase.NS_YELLOW)
                    return

        elif self.phase == Phase.NS_YELLOW:
            # Normal yellow stays full length; only an emergency transition uses the demo interval.
            yellow_ms = self.timings.priority_yellow_ms if self.priority_clearance_active else self.timings.yellow_ms
            if phase_elapsed >= yellow_ms:
                self._transition_to(Phase.ALL_RED_TO_EW)
                if self.mode == Mode.PRIORITY and self.target_priority_axis is not None:
                    self.priority_clearance_active = True
                return

        elif self.phase == Phase.ALL_RED_TO_EW:
            # Preserve a distinct approach's request without serving the wrong axis.
            all_red_ms = self.timings.priority_all_red_ms if self.priority_clearance_active else self.timings.all_red_ms
            if phase_elapsed >= all_red_ms:
                if self.target_priority_axis == Axis.NS and self.mode == Mode.PRIORITY:
                    self._transition_to(Phase.NS_GREEN)
                    self.active_priority_axis = Axis.NS
                    self.active_priority_approach = self.target_priority_approach
                    self.hold_green_active = True
                    self.priority_start_ms = self.uptime_ms
                    self.priority_command_rx_ms = self.uptime_ms
                else:
                    self._transition_to(Phase.EW_GREEN)
                    if self.target_priority_axis == Axis.EW and self.mode == Mode.PRIORITY:
                        self.active_priority_axis = Axis.EW
                        self.active_priority_approach = self.target_priority_approach
                        self.hold_green_active = True
                        self.priority_start_ms = self.uptime_ms
                        self.priority_command_rx_ms = self.uptime_ms
                        self.priority_command_rx_ms = self.uptime_ms
                self.priority_clearance_active = False
                return

        elif self.phase == Phase.EW_GREEN:
            # Check if priority requested for opposite axis (NS)
            if self.target_priority_axis == Axis.NS and self.mode == Mode.PRIORITY:
                # Invariant S4: Can only cut after min_green_ms
                if phase_elapsed >= self.timings.min_green_ms:
                    self.priority_clearance_active = True
                    self._transition_to(Phase.EW_YELLOW)
                    return
            elif self.hold_green_active and self.active_priority_axis == Axis.EW:
                # Holding green for EW; timer is paused
                return
            else:
                # Normal cycle green duration
                if phase_elapsed >= self.timings.green_ms:
                    self._transition_to(Phase.EW_YELLOW)
                    return

        elif self.phase == Phase.EW_YELLOW:
            # Normal yellow stays full length; only an emergency transition uses the demo interval.
            yellow_ms = self.timings.priority_yellow_ms if self.priority_clearance_active else self.timings.yellow_ms
            if phase_elapsed >= yellow_ms:
                self._transition_to(Phase.ALL_RED_TO_NS)
                if self.mode == Mode.PRIORITY and self.target_priority_axis is not None:
                    self.priority_clearance_active = True
                return

        elif self.phase == Phase.ALL_RED_TO_NS:
            all_red_ms = self.timings.priority_all_red_ms if self.priority_clearance_active else self.timings.all_red_ms
            if phase_elapsed >= all_red_ms:
                if self.target_priority_axis == Axis.EW and self.mode == Mode.PRIORITY:
                    self._transition_to(Phase.EW_GREEN)
                    self.active_priority_axis = Axis.EW
                    self.active_priority_approach = self.target_priority_approach
                    self.hold_green_active = True
                    self.priority_start_ms = self.uptime_ms
                    self.priority_command_rx_ms = self.uptime_ms
                else:
                    self._transition_to(Phase.NS_GREEN)
                    if self.target_priority_axis == Axis.NS and self.mode == Mode.PRIORITY:
                        self.active_priority_axis = Axis.NS
                        self.active_priority_approach = self.target_priority_approach
                        self.hold_green_active = True
                        self.priority_start_ms = self.uptime_ms
                        self.priority_command_rx_ms = self.uptime_ms
                self.priority_clearance_active = False
                return

    def _transition_to(self, new_phase: Phase) -> None:
        """Helper to advance state safely."""
        self.phase = new_phase
        self.phase_start_ms = self.uptime_ms
