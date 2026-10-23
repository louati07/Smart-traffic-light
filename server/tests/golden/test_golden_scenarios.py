"""Golden scenario tests for the 5 canonical intersection behaviors.

1. Normal cycle
2. Priority from red
3. Priority when already green
4. Priority during yellow
5. Heartbeat loss
"""


from server.app.core.light_fsm import (
    FSMCommand,
    FSMTimings,
    LightFSM,
    Mode,
    Phase,
)


def test_golden_scenario_1_normal():
    """Scenario 1: Complete normal cycle progresses through all 6 phases predictably."""
    timings = FSMTimings(green_ms=10000, yellow_ms=3000, all_red_ms=2000)
    fsm = LightFSM(timings, initial_now_ms=0)

    phases_recorded = []
    # Run for 35,000 ms (more than 1 full cycle of 2 * (10 + 3 + 2) = 30s)
    for t in range(0, 35000, 500):
        fsm.record_heartbeat(int(t // 2000) + 1, now_ms=t)
        fsm.tick(t)
        if not phases_recorded or phases_recorded[-1] != fsm.phase:
            phases_recorded.append(fsm.phase)

    expected_sequence = [
        Phase.NS_GREEN,
        Phase.NS_YELLOW,
        Phase.ALL_RED_TO_EW,
        Phase.EW_GREEN,
        Phase.EW_YELLOW,
        Phase.ALL_RED_TO_NS,
        Phase.NS_GREEN,
    ]
    assert phases_recorded[:7] == expected_sequence
    assert fsm.mode == Mode.NORMAL


def test_golden_scenario_2_priority_from_red():
    """Scenario 2: Priority requested for EW while NS is green cuts green after MIN_GREEN."""
    timings = FSMTimings(green_ms=10000, yellow_ms=3000, all_red_ms=2000, min_green_ms=5000)
    fsm = LightFSM(timings, initial_now_ms=0)

    # At t=1000ms, priority EW arrives
    fsm.apply_command(FSMCommand(seq=1, cmd="PRIORITY", axis="EW", ttl_s=15), now_ms=1000)
    fsm.tick(1000)
    assert fsm.phase == Phase.NS_GREEN
    assert fsm.mode == Mode.PRIORITY

    # Advance to 4999ms -> still green
    fsm.tick(4999)
    assert fsm.phase == Phase.NS_GREEN

    # At 5000ms -> min_green_ms satisfied -> NS_YELLOW
    fsm.tick(5000)
    assert fsm.phase == Phase.NS_YELLOW

    # At 8000ms -> ALL_RED_TO_EW
    fsm.tick(8000)
    assert fsm.phase == Phase.ALL_RED_TO_EW

    # At 10000ms -> EW_GREEN held
    fsm.tick(10000)
    assert fsm.phase == Phase.EW_GREEN
    assert fsm.hold_green_active


def test_golden_scenario_3_priority_already_green():
    """Scenario 3: Priority requested for NS while NS is already green pauses timer."""
    timings = FSMTimings(green_ms=10000, yellow_ms=3000, all_red_ms=2000)
    fsm = LightFSM(timings, initial_now_ms=0)

    # Priority for NS at t=7000ms
    fsm.apply_command(FSMCommand(seq=1, cmd="PRIORITY", axis="NS", ttl_s=20), now_ms=7000)
    fsm.tick(7000)
    assert fsm.phase == Phase.NS_GREEN
    assert fsm.hold_green_active

    # Without priority, green would end at 10000ms. With priority, it holds at 18000ms
    fsm.tick(18000)
    assert fsm.phase == Phase.NS_GREEN
    assert fsm.mode == Mode.PRIORITY

    # Clear at 18000ms
    fsm.apply_command(FSMCommand(seq=2, cmd="CLEAR"), now_ms=18000)
    fsm.tick(18001)
    # Transitions to yellow immediately since 18s > min_green_ms
    assert fsm.phase == Phase.NS_YELLOW


def test_golden_scenario_4_priority_during_yellow():
    """Scenario 4: Priority requested during NS_YELLOW finishes yellow + all-red before granting."""
    timings = FSMTimings(green_ms=10000, yellow_ms=3000, all_red_ms=2000)
    fsm = LightFSM(timings, initial_now_ms=0)

    # Advance to yellow at 10000ms
    fsm.tick(10000)
    assert fsm.phase == Phase.NS_YELLOW

    # Command arrives at 11000ms (1s into yellow) requesting EW
    fsm.apply_command(FSMCommand(seq=1, cmd="PRIORITY", axis="EW", ttl_s=15), now_ms=11000)
    fsm.tick(11000)
    # Does not skip yellow!
    assert fsm.phase == Phase.NS_YELLOW

    # Yellow finishes at 13000ms
    fsm.tick(13000)
    assert fsm.phase == Phase.ALL_RED_TO_EW

    # All-red finishes at 15000ms -> EW_GREEN active and held
    fsm.tick(15000)
    assert fsm.phase == Phase.EW_GREEN
    assert fsm.hold_green_active


def test_golden_scenario_5_heartbeat_loss():
    """Scenario 5: Loss of heartbeat triggers FALLBACK and drops active priority."""
    timings = FSMTimings(heartbeat_timeout_ms=10000)
    fsm = LightFSM(timings, initial_now_ms=0)
    fsm.record_heartbeat(1, now_ms=0)

    # Activate priority on NS
    fsm.apply_command(FSMCommand(seq=1, cmd="PRIORITY", axis="NS"), now_ms=1000)
    fsm.tick(1000)
    assert fsm.mode == Mode.PRIORITY

    # Advance beyond heartbeat timeout (11000ms since last heartbeat at t=0)
    fsm.tick(11001)
    assert fsm.mode == Mode.FALLBACK
    assert not fsm.hold_green_active

    # Subsequent commands are rejected in FALLBACK
    assert not fsm.apply_command(FSMCommand(seq=2, cmd="PRIORITY", axis="EW"), now_ms=11500)
    assert fsm.rejected_cmds == 1
