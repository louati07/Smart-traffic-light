"""End-to-end integration test: Priority Engine + InMemoryFirebase + MockESP32Twin.

Acceptance criteria (PLAN.md Section 8 P3):
Verifies:
1. Detection confirmed -> Priority command issued to Firebase.
2. MockESP32Twin reads command and executes safe transition.
3. Light change occurs within 2.5 s of simulated time.
4. Ceasing detection -> PriorityEngine auto-releases CLEAR -> Controller returns cleanly to normal.
"""


from server.app.clients.firebase import InMemoryFirebase
from server.app.clients.mongo import InMemoryMongoClient
from server.app.core.light_fsm import Phase
from server.app.core.priority_engine import ConfirmedDetection, PriorityEngine
from server.app.mock_esp32 import MockESP32Twin


def test_full_priority_pipeline_integration():
    # 1. Setup in-memory instances
    firebase = InMemoryFirebase()
    mongo = InMemoryMongoClient()

    engine = PriorityEngine(
        firebase_client=firebase,
        mongo_client=mongo,
        intersection_id="i1",
        release_after_s=2.0,
        cooldown_s=1.0,
        command_ttl_s=15,
    )

    twin = MockESP32Twin(
        firebase_client=firebase,
        intersection_id="i1",
        poll_interval_s=0.05,
    )

    # Initial step at t=0ms
    current_ms = 0
    twin.step(now_ms=current_ms)
    state = firebase.get_state("i1")
    assert state is not None
    assert state["phase"] == Phase.NS_GREEN.value
    assert state["mode"] == "NORMAL"

    # Advance time to 6000ms (NS has satisfied min_green_ms of 5000ms)
    current_ms = 6000
    firebase.increment_heartbeat("i1")
    twin.step(now_ms=current_ms)

    # 2. Incoming confirmed detection on approach 'E' (EW axis)
    det = ConfirmedDetection(
        camera_id="cam-E",
        approach="E",
        vehicle_class="ambulance",
        confidence=0.95,
        bbox_area_ratio=0.04,
        frame_id=1,
        source_ts_ms=1000,
        received_at_s=current_ms / 1000.0,
    )
    cmd = engine.handle_detection(det, now_s=current_ms / 1000.0)
    assert cmd is not None
    assert cmd["cmd"] == "PRIORITY"
    assert cmd["axis"] == "EW"

    # Check command written to Firebase
    fb_cmd = firebase.get_command("i1")
    assert fb_cmd is not None
    assert fb_cmd["seq"] == cmd["seq"]

    # 3. Step Twin: advance time by 100ms so poll_interval elapses
    current_ms += 100
    twin.step(now_ms=current_ms)
    assert twin.fsm.mode.value == "PRIORITY"
    # Transitioned immediately to yellow because phase_elapsed (6000ms) >= min_green_ms (5000ms)
    assert twin.fsm.phase == Phase.NS_YELLOW

    # Advance through yellow (3000ms)
    current_ms += 3000
    twin.step(now_ms=current_ms)
    assert twin.fsm.phase == Phase.ALL_RED_TO_EW

    # Advance through all-red (2000ms) -> EW_GREEN active and held!
    current_ms += 2000
    twin.step(now_ms=current_ms)
    assert twin.fsm.phase == Phase.EW_GREEN
    assert twin.fsm.hold_green_active is True
    assert twin.fsm.lights["E"] == "G"

    # State in Firebase must reflect priority
    twin_state = firebase.get_state("i1")
    assert twin_state["phase"] == "EW_GREEN"
    assert twin_state["mode"] == "PRIORITY"

    # 4. Advance time past release_after_s (2.0s) without further detections
    sim_time_s = (current_ms + 2500) / 1000.0
    current_ms += 2500
    engine_actions = engine.tick(now_s=sim_time_s)
    assert len(engine_actions) == 1
    assert engine_actions[0]["cmd"] == "CLEAR"

    # 5. Twin observes CLEAR command and safely returns to normal cycle
    twin.step(now_ms=current_ms)
    assert twin.fsm.hold_green_active is False

    # After normal green_ms on EW satisfies (10s), it transitions to EW_YELLOW -> ALL_RED -> NS_GREEN
    current_ms += 10000
    firebase.increment_heartbeat("i1")
    twin.step(now_ms=current_ms)
    assert twin.fsm.phase in (Phase.EW_YELLOW, Phase.ALL_RED_TO_NS, Phase.NS_GREEN)
