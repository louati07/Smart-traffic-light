"""Deterministic discrete-event traffic simulator for intersection A/B evaluation.

Implements Section 4 & P1 of PLAN.md:
- 0.5 s discrete tick
- Seeded Poisson vehicle arrivals per approach
- 2.0 s departure headway while green
- Baseline (fixed timer) vs Priority (LightFSM with pre-detection)
- Computes KPIs and compact JSON replay traces.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any

from server.app.core.light_fsm import (
    CommandType,
    FSMCommand,
    FSMTimings,
    LightFSM,
)


@dataclass
class Vehicle:
    id: int
    approach: str
    arrival_time_s: float
    is_ambulance: bool = False
    departure_time_s: float | None = None
    wait_time_s: float = 0.0


@dataclass
class SimKPIs:
    ambulance_wait_s: float
    ambulance_crossing_time_s: float
    avg_other_delay_s: float
    max_queue_len: int
    extra_delay_others_s: float = 0.0
    recovery_time_s: float = 0.0
    total_vehicles_served: int = 0


@dataclass
class ReplayFrame:
    time_s: float
    phase: str
    mode: str
    lights: dict[str, str]
    queues: dict[str, int]
    ambulance: dict[str, Any] | None = None


@dataclass
class SimResult:
    controller_type: str  # "baseline" | "priority"
    seed: int
    duration_s: float
    kpis: SimKPIs
    trace: list[ReplayFrame]


class TrafficSimulator:
    """Deterministic, seeded traffic simulator comparing fixed timer vs priority."""

    def __init__(
        self,
        seed: int = 42,
        timings: FSMTimings | None = None,
        tick_s: float = 0.5,
        arrival_rate_per_approach: float = 0.1,  # veh / s
        departure_headway_s: float = 2.0,
        detect_lead_s: float = 8.0,
        command_latency_s: float = 1.5,
    ):
        self.seed = seed
        self.timings = timings or FSMTimings()
        self.tick_s = tick_s
        self.arrival_rate = arrival_rate_per_approach
        self.headway_s = departure_headway_s
        self.detect_lead_s = detect_lead_s
        self.command_latency_s = command_latency_s

    def generate_arrivals(
        self,
        duration_s: float,
        ambulance_approach: str = "N",
        ambulance_arrival_s: float = 18.0,
    ) -> dict[str, list[Vehicle]]:
        """Generate deterministic vehicle arrivals using the seeded PRNG."""
        prng = random.Random(self.seed)
        approaches = ["N", "E", "S", "W"]
        arrivals: dict[str, list[Vehicle]] = {a: [] for a in approaches}
        veh_id = 1

        # Poisson process generation for background traffic
        for a in approaches:
            current_t = 0.0
            while current_t < duration_s:
                # Exponential inter-arrival time
                u = max(1e-6, prng.random())
                inter_t = -math.log(u) / self.arrival_rate
                current_t += inter_t
                if current_t < duration_s:
                    arrivals[a].append(
                        Vehicle(
                            id=veh_id,
                            approach=a,
                            arrival_time_s=round(current_t, 2),
                            is_ambulance=False,
                        )
                    )
                    veh_id += 1

        # Inject single ambulance
        amb = Vehicle(
            id=9999,
            approach=ambulance_approach,
            arrival_time_s=round(ambulance_arrival_s, 2),
            is_ambulance=True,
        )
        arrivals[ambulance_approach].append(amb)
        arrivals[ambulance_approach].sort(key=lambda v: v.arrival_time_s)

        return arrivals

    def run_single(
        self,
        controller_type: str,
        arrivals: dict[str, list[Vehicle]],
        duration_s: float = 90.0,
        ambulance_approach: str = "N",
        ambulance_arrival_s: float = 18.0,
    ) -> SimResult:
        """Execute one simulation run (baseline or priority) with the given arrivals."""
        # Deep copy vehicle list to maintain separate tracking
        pending_arrivals: dict[str, list[Vehicle]] = {
            a: [Vehicle(**asdict(v)) for v in vehs] for a, vehs in arrivals.items()
        }
        queues: dict[str, list[Vehicle]] = {a: [] for a in ["N", "E", "S", "W"]}
        served_vehicles: list[Vehicle] = []
        last_departure_t: dict[str, float] = {a: -999.0 for a in ["N", "E", "S", "W"]}

        fsm = LightFSM(self.timings)
        trace: list[ReplayFrame] = []
        max_queue = 0

        # Ambulance tracking state
        ambulance_obj: Vehicle | None = None
        ambulance_state = "approaching"  # approaching | queued | crossing | cleared
        ambulance_speed_mps = 12.0  # ~43 km/h
        ambulance_pos_m = 100.0
        amb_crossing_start_s: float | None = None
        amb_cleared_s: float | None = None

        # Priority command scheduling
        priority_sent = False
        clear_sent = False
        seq = 1

        detection_time_s = max(0.0, ambulance_arrival_s - self.detect_lead_s)
        command_effective_s = detection_time_s + self.command_latency_s

        approach_axes = {"N": "NS", "S": "NS", "E": "EW", "W": "EW"}
        amb_axis = approach_axes[ambulance_approach]

        current_t = 0.0
        while current_t <= duration_s:
            now_ms = int(current_t * 1000)

            # Send heartbeat regularly so controller never drops to fallback unexpectedly
            fsm.record_heartbeat(counter=int(current_t // 2) + 1, now_ms=now_ms)

            # Check priority controller injection
            if controller_type == "priority":
                if not priority_sent and current_t >= command_effective_s:
                    fsm.apply_command(
                        FSMCommand(
                            seq=seq,
                            cmd=CommandType.PRIORITY.value,
                            axis=amb_axis,
                            ttl_s=self.timings.command_ttl_s,
                        ),
                        now_ms=now_ms,
                    )
                    seq += 1
                    priority_sent = True

                if (
                    priority_sent
                    and not clear_sent
                    and ambulance_state in ("crossing", "cleared")
                ):
                    fsm.apply_command(
                        FSMCommand(
                            seq=seq,
                            cmd=CommandType.CLEAR.value,
                        ),
                        now_ms=now_ms,
                    )
                    seq += 1
                    clear_sent = True

            # Advance FSM clock
            fsm.tick(now_ms)
            lights = fsm.lights

            # Check new arrivals entering approach queues
            for a in ["N", "E", "S", "W"]:
                while (
                    pending_arrivals[a]
                    and pending_arrivals[a][0].arrival_time_s <= current_t
                ):
                    arriving_v = pending_arrivals[a].pop(0)
                    queues[a].append(arriving_v)
                    if arriving_v.is_ambulance:
                        ambulance_obj = arriving_v
                        ambulance_state = "queued"

            # Check queue departures if green
            for a in ["N", "E", "S", "W"]:
                is_green = lights[a] == "G"
                if is_green and queues[a]:
                    if (current_t - last_departure_t[a]) >= self.headway_s:
                        departing_v = queues[a].pop(0)
                        departing_v.departure_time_s = current_t
                        departing_v.wait_time_s = max(
                            0.0, current_t - departing_v.arrival_time_s
                        )
                        served_vehicles.append(departing_v)
                        last_departure_t[a] = current_t

                        if departing_v.is_ambulance:
                            ambulance_state = "crossing"
                            amb_crossing_start_s = current_t

            # Update ambulance position tracking for animation
            if ambulance_state == "approaching":
                time_to_arrival = ambulance_arrival_s - current_t
                ambulance_pos_m = max(0.0, time_to_arrival * ambulance_speed_mps)
            elif ambulance_state == "queued":
                ambulance_pos_m = 0.0  # waiting at stop line
            elif ambulance_state == "crossing":
                if amb_crossing_start_s is not None:
                    crossing_dur = current_t - amb_crossing_start_s
                    ambulance_pos_m = -(crossing_dur * ambulance_speed_mps)
                    if crossing_dur >= 2.5:
                        ambulance_state = "cleared"
                        amb_cleared_s = current_t
            elif ambulance_state == "cleared":
                ambulance_pos_m = -35.0

            # Record max queue
            current_max_q = max(len(q) for q in queues.values())
            max_queue = max(max_queue, current_max_q)

            # Frame snapshot for 2D Digital Twin
            amb_info = {
                "approach": ambulance_approach,
                "dist_m": round(ambulance_pos_m, 1),
                "status": ambulance_state,
            }
            frame = ReplayFrame(
                time_s=round(current_t, 1),
                phase=fsm.phase.value,
                mode=fsm.mode.value,
                lights=lights,
                queues={a: len(queues[a]) for a in ["N", "E", "S", "W"]},
                ambulance=amb_info,
            )
            trace.append(frame)

            current_t = round(current_t + self.tick_s, 2)

        # Compute KPIs
        amb_wait = 0.0
        amb_crossing = 0.0
        if ambulance_obj and ambulance_obj.departure_time_s is not None:
            amb_wait = round(ambulance_obj.wait_time_s, 2)
            amb_crossing = round(
                (amb_cleared_s or ambulance_obj.departure_time_s + 2.5)
                - ambulance_arrival_s,
                2,
            )
        else:
            amb_wait = round(duration_s - ambulance_arrival_s, 2)
            amb_crossing = amb_wait

        other_waits = [
            v.wait_time_s for v in served_vehicles if not v.is_ambulance
        ]
        avg_other = round(sum(other_waits) / len(other_waits), 2) if other_waits else 0.0

        kpis = SimKPIs(
            ambulance_wait_s=amb_wait,
            ambulance_crossing_time_s=amb_crossing,
            avg_other_delay_s=avg_other,
            max_queue_len=max_queue,
            total_vehicles_served=len(served_vehicles),
        )

        return SimResult(
            controller_type=controller_type,
            seed=self.seed,
            duration_s=duration_s,
            kpis=kpis,
            trace=trace,
        )

    def run_ab_comparison(
        self,
        duration_s: float = 90.0,
        ambulance_approach: str = "N",
        ambulance_arrival_s: float = 18.0,
    ) -> tuple[SimResult, SimResult]:
        """Run both baseline and priority on identical traffic arrivals."""
        arrivals = self.generate_arrivals(
            duration_s=duration_s,
            ambulance_approach=ambulance_approach,
            ambulance_arrival_s=ambulance_arrival_s,
        )

        baseline_res = self.run_single(
            "baseline",
            arrivals,
            duration_s=duration_s,
            ambulance_approach=ambulance_approach,
            ambulance_arrival_s=ambulance_arrival_s,
        )
        priority_res = self.run_single(
            "priority",
            arrivals,
            duration_s=duration_s,
            ambulance_approach=ambulance_approach,
            ambulance_arrival_s=ambulance_arrival_s,
        )

        # Compute comparative differential KPIs
        extra_delay = round(
            priority_res.kpis.avg_other_delay_s - baseline_res.kpis.avg_other_delay_s,
            2,
        )
        priority_res.kpis.extra_delay_others_s = extra_delay

        # Recovery time: time after ambulance clearing when queue lengths equal or beat baseline
        recovery_time = 0.0
        amb_cleared_t = 0.0
        for frame in priority_res.trace:
            if frame.ambulance and frame.ambulance.get("status") == "cleared":
                amb_cleared_t = frame.time_s
                break

        for i, (b_frame, p_frame) in enumerate(
            zip(baseline_res.trace, priority_res.trace)
        ):
            if p_frame.time_s > amb_cleared_t:
                p_sum = sum(p_frame.queues.values())
                b_sum = sum(b_frame.queues.values())
                if p_sum <= b_sum:
                    recovery_time = round(p_frame.time_s - amb_cleared_t, 1)
                    break
        priority_res.kpis.recovery_time_s = recovery_time

        return baseline_res, priority_res
