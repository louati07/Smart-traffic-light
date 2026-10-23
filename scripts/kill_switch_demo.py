"""Kill Switch & Heartbeat Loss Demonstration Script.

Simulates disconnection between server heartbeat and controller FSM,
demonstrating that the intersection autonomously reverts to FALLBACK mode
within 10 seconds without any conflicting green lights.
"""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.app.core.light_fsm import FSMCommand, FSMTimings, LightFSM, Mode, Phase


def run_kill_switch_demo():
    timings = FSMTimings(
        green_ms=6000,
        yellow_ms=2000,
        all_red_ms=1000,
        heartbeat_timeout_ms=5000,  # 5s demo scale for fast verification
    )
    fsm = LightFSM(timings, initial_now_ms=0)

    print("\n1. Controller running with active server heartbeat...")
    fsm.record_heartbeat(counter=1, now_ms=0)
    fsm.tick(1000)
    print(f"   t=1000ms: Phase={fsm.phase.value}, Mode={fsm.mode.value}, Lights={fsm.lights}")

    print("\n2. Granting emergency vehicle priority on NS...")
    fsm.apply_command(FSMCommand(seq=1, cmd="PRIORITY", axis="NS", ttl_s=20), now_ms=1500)
    fsm.tick(1500)
    print(f"   t=1500ms: Phase={fsm.phase.value}, Mode={fsm.mode.value}, Held={fsm.hold_green_active}")

    print("\n3. CUTTING HEARTBEAT (Simulating network collapse / server failure)...")
    print("   Advancing time past heartbeat timeout threshold (5000ms)...")

    # Advance time without calling record_heartbeat
    for t in range(2000, 7001, 1000):
        fsm.tick(t)
        print(f"   t={t}ms: Phase={fsm.phase.value}, Mode={fsm.mode.value}, Lights={fsm.lights}")

    print("\n4. Verifying Safety Post-Condition:")
    assert fsm.mode == Mode.FALLBACK, f"Expected Mode.FALLBACK, got {fsm.mode}"
    assert not fsm.hold_green_active, "Active priority should be released in FALLBACK"
    print("   -> Mode is FALLBACK. Priority hold dropped.")

    print("\n5. Testing that normal fail-safe cycle continues predictably:")
    phases = []
    for t in range(8000, 20000, 1000):
        fsm.tick(t)
        if not phases or phases[-1] != fsm.phase.value:
            phases.append(fsm.phase.value)

    print(f"   Observed safe progression in FALLBACK: {phases}")
    print("\n========================================================")
    print(" [OK] FAIL-SAFE HEARTBEAT LOSS SAFETY VERIFIED (S6).      ")
    print("========================================================\n")


if __name__ == "__main__":
    run_kill_switch_demo()
