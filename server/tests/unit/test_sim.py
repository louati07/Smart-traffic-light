"""Unit tests for TrafficSimulator."""

import json
from dataclasses import asdict

from server.app.core.sim import TrafficSimulator


def test_simulator_determinism():
    """Verify that identical seeds yield byte-identical simulation results and traces."""
    sim1 = TrafficSimulator(seed=12345)
    sim2 = TrafficSimulator(seed=12345)

    base1, prio1 = sim1.run_ab_comparison(duration_s=60.0)
    base2, prio2 = sim2.run_ab_comparison(duration_s=60.0)

    # Compare serialized outputs
    dump_base1 = json.dumps(asdict(base1), sort_keys=True)
    dump_base2 = json.dumps(asdict(base2), sort_keys=True)
    assert dump_base1 == dump_base2, "Baseline simulations with identical seeds are not byte-identical!"

    dump_prio1 = json.dumps(asdict(prio1), sort_keys=True)
    dump_prio2 = json.dumps(asdict(prio2), sort_keys=True)
    assert dump_prio1 == dump_prio2, "Priority simulations with identical seeds are not byte-identical!"


def test_priority_ambulance_wait_strictly_lower_than_baseline():
    """In default scenario (ambulance arrives on red), priority ambulance_wait_s < baseline."""
    sim = TrafficSimulator(seed=42)
    # Default scenario: Ambulance arrives at 18.0s on approach N (NS axis is red because EW is green)
    base, prio = sim.run_ab_comparison(
        duration_s=60.0,
        ambulance_approach="N",
        ambulance_arrival_s=18.0,
    )

    assert prio.kpis.ambulance_wait_s < base.kpis.ambulance_wait_s, (
        f"Priority wait ({prio.kpis.ambulance_wait_s}s) must be strictly less "
        f"than baseline wait ({base.kpis.ambulance_wait_s}s)"
    )
    assert prio.kpis.ambulance_crossing_time_s < base.kpis.ambulance_crossing_time_s
