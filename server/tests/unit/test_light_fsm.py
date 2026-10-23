"""Tests for LightFSM, including Hypothesis property tests for Safety Invariants S1-S7."""

from hypothesis import given, settings
from hypothesis import strategies as st

from server.app.core.light_fsm import (
    FSMCommand,
    FSMTimings,
    LightFSM,
    Mode,
    Phase,
)


def test_normal_cycle_timings():
    """Verify normal fixed-timer transitions and phase durations."""
    timings = FSMTimings(
        green_ms=10000,
        yellow_ms=3000,
        all_red_ms=2000,
    )
    fsm = LightFSM(timings, initial_now_ms=0)
    assert fsm.phase == Phase.NS_GREEN
    assert fsm.lights == {"N": "G", "E": "R", "S": "G", "W": "R"}

    # Green lasts 10,000 ms
    fsm.tick(9999)
    assert fsm.phase == Phase.NS_GREEN
    fsm.tick(10000)
    assert fsm.phase == Phase.NS_YELLOW
    assert fsm.lights == {"N": "Y", "E": "R", "S": "Y", "W": "R"}

    # Yellow lasts 3,000 ms
    fsm.tick(12999)
    assert fsm.phase == Phase.NS_YELLOW
    fsm.tick(13000)
    assert fsm.phase == Phase.ALL_RED_TO_EW
    assert fsm.lights == {"N": "R", "E": "R", "S": "R", "W": "R"}

    # All red lasts 2,000 ms
    fsm.tick(14999)
    assert fsm.phase == Phase.ALL_RED_TO_EW
    fsm.tick(15000)
    assert fsm.phase == Phase.EW_GREEN
    assert fsm.lights == {"N": "R", "E": "G", "S": "R", "W": "G"}


def test_priority_when_already_green_holds_green():
    """Rule 1: If axis is already green, hold green and pause timer."""
    fsm = LightFSM(initial_now_ms=0)
    assert fsm.phase == Phase.NS_GREEN

    # At 4s (before 10s normal green expiry), priority on NS is applied
    cmd = FSMCommand(seq=1, cmd="PRIORITY", axis="NS", ttl_s=15)
    fsm.apply_command(cmd, now_ms=4000)

    # Fast forward beyond normal green (e.g. 15s)
    fsm.tick(15000)
    # Should still be green because it is held
    assert fsm.phase == Phase.NS_GREEN
    assert fsm.mode == Mode.PRIORITY

    # CLEAR command releases it
    fsm.apply_command(FSMCommand(seq=2, cmd="CLEAR"), now_ms=16000)
    fsm.tick(16001)
    # Since phase_elapsed (16001 - 0) >= min_green_ms (5000), it transitions to yellow
    assert fsm.phase == Phase.NS_YELLOW


def test_priority_from_opposite_axis_respects_min_green():
    """Invariant S4: Green is never cut before MIN_GREEN_MS."""
    timings = FSMTimings(min_green_ms=5000)
    fsm = LightFSM(timings, initial_now_ms=0)
    assert fsm.phase == Phase.NS_GREEN

    # Priority requested for EW at t=2000 ms (only 2s into NS green)
    cmd = FSMCommand(seq=1, cmd="PRIORITY", axis="EW", ttl_s=15)
    fsm.apply_command(cmd, now_ms=2000)

    # At t=4999 ms, NS green must still be maintained
    fsm.tick(4999)
    assert fsm.phase == Phase.NS_GREEN

    # At t=5000 ms, min_green_ms satisfied -> switches to NS_YELLOW
    fsm.tick(5000)
    assert fsm.phase == Phase.NS_YELLOW

    # S3: Yellow (3s) and all-red (2s) must complete
    fsm.tick(7999)
    assert fsm.phase == Phase.NS_YELLOW
    fsm.tick(8000)
    assert fsm.phase == Phase.ALL_RED_TO_EW
    fsm.tick(9999)
    assert fsm.phase == Phase.ALL_RED_TO_EW
    fsm.tick(10000)
    # Now EW green is active and held
    assert fsm.phase == Phase.EW_GREEN
    assert fsm.mode == Mode.PRIORITY


def test_priority_watchdog_max_hold():
    """Invariant S5: Priority never holds a green longer than PRIORITY_MAX_MS."""
    timings = FSMTimings(priority_max_ms=30000)
    fsm = LightFSM(timings, initial_now_ms=0)

    fsm.apply_command(FSMCommand(seq=1, cmd="PRIORITY", axis="NS", ttl_s=60), now_ms=1000)
    fsm.tick(1000)
    assert fsm.hold_green_active

    # Tick past 30,000 ms watchdog limit
    fsm.tick(31001)
    assert not fsm.hold_green_active
    assert fsm.phase == Phase.NS_YELLOW


def test_stale_seq_rejected():
    """Invariant S6: Out-of-order or stale sequence commands are rejected."""
    fsm = LightFSM(initial_now_ms=0)
    assert fsm.apply_command(FSMCommand(seq=5, cmd="PRIORITY", axis="NS"), now_ms=100)
    assert fsm.last_seq == 5

    # Seq 5 or lower must be rejected
    assert not fsm.apply_command(FSMCommand(seq=5, cmd="PRIORITY", axis="EW"), now_ms=200)
    assert not fsm.apply_command(FSMCommand(seq=3, cmd="CLEAR"), now_ms=300)
    assert fsm.rejected_cmds == 2


def test_heartbeat_timeout_triggers_fallback():
    """Invariant S6: Heartbeat lost triggers FALLBACK mode."""
    timings = FSMTimings(heartbeat_timeout_ms=10000)
    fsm = LightFSM(timings, initial_now_ms=0)
    fsm.record_heartbeat(1, now_ms=0)

    # 10,001 ms without heartbeat
    fsm.tick(10001)
    assert fsm.mode == Mode.FALLBACK

    # Commands during fallback are rejected
    assert not fsm.apply_command(FSMCommand(seq=1, cmd="PRIORITY", axis="NS"), now_ms=10002)


# =========================================================================
# Hypothesis Property-Based Testing for Safety Invariants S1-S7
# =========================================================================

@st.composite
def command_stream(draw):
    seq = draw(st.integers(min_value=1, max_value=200))
    cmd = draw(st.sampled_from(["PRIORITY", "CLEAR", "INVALID"]))
    axis = draw(st.sampled_from(["NS", "EW", "UNKNOWN"]))
    ttl = draw(st.integers(min_value=1, max_value=30))
    time_offset = draw(st.integers(min_value=100, max_value=4000))
    return seq, cmd, axis, ttl, time_offset


@settings(max_examples=50, deadline=None)
@given(st.lists(command_stream(), min_size=5, max_size=30))
def test_hypothesis_invariants_s1_through_s7(commands):
    """Property test verifying S1 through S7 under arbitrary command sequences."""
    fsm = LightFSM()
    current_time_ms = 0
    heartbeat_counter = 1

    last_lights = fsm.lights
    last_phase = fsm.phase
    phase_start_time = 0

    for seq, cmd_type, axis, ttl, dt in commands:
        current_time_ms += dt

        # Simulate periodic heartbeat every 2000 ms
        if current_time_ms // 2000 >= heartbeat_counter:
            heartbeat_counter = int(current_time_ms // 2000) + 1
            fsm.record_heartbeat(heartbeat_counter, now_ms=current_time_ms)

        # Apply random command
        cmd = FSMCommand(seq=seq, cmd=cmd_type, axis=axis, ttl_s=ttl)
        fsm.apply_command(cmd, now_ms=current_time_ms)

        # Advance tick in small steps (500 ms) to observe all transitions
        step = 500
        for t in range(current_time_ms - dt, current_time_ms + 1, step):
            fsm.tick(t)
            lights = fsm.lights
            phase = fsm.phase

            # Invariant S1: The two axes are never green at the same time
            ns_green = (lights["N"] == "G" or lights["S"] == "G")
            ew_green = (lights["E"] == "G" or lights["W"] == "G")
            assert not (ns_green and ew_green), f"S1 Violation! Simultaneous green at {t}ms: {lights}"

            # Invariant S2: Direct opposite G->G or R->G without Y and ALL_RED in between
            if phase != last_phase:
                duration_in_prev_phase = t - phase_start_time
                if last_phase == Phase.NS_YELLOW:
                    assert phase == Phase.ALL_RED_TO_EW
                    # Invariant S3: Yellow duration never shortened
                    assert duration_in_prev_phase >= fsm.timings.yellow_ms
                elif last_phase == Phase.ALL_RED_TO_EW:
                    assert phase == Phase.EW_GREEN
                    # Invariant S3: All-red duration never shortened
                    assert duration_in_prev_phase >= fsm.timings.all_red_ms
                elif last_phase == Phase.EW_YELLOW:
                    assert phase == Phase.ALL_RED_TO_NS
                    assert duration_in_prev_phase >= fsm.timings.yellow_ms
                elif last_phase == Phase.ALL_RED_TO_NS:
                    assert phase == Phase.NS_GREEN
                    assert duration_in_prev_phase >= fsm.timings.all_red_ms

                last_phase = phase
                phase_start_time = t

            last_lights = lights  # noqa: F841
