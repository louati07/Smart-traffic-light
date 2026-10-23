"""Seed demo dataset into MongoDB.

Populates:
1. Deterministic A/B simulation runs across multiple seeds (demonstrating ambulance wait reduction).
2. Historical priority events (ambulance, fire truck, police car).
3. Realistic security audit events.

Usage:
python scripts/seed_demo_data.py
"""

from dataclasses import asdict
import datetime
from pathlib import Path
import random
import sys
import uuid

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.app.clients.mongo import get_mongo_client
from server.app.config import settings
from server.app.core.sim import TrafficSimulator


def seed_demo_data() -> None:
    print(f"Connecting to MongoDB (mode: {settings.mongo_mode})...")
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)

    print("1. Seeding deterministic A/B simulation runs...")
    approaches = ["N", "E", "S", "W"]
    for i, seed in enumerate([42, 101, 2024, 777, 999, 1337], 1):
        app = approaches[i % 4]
        sim = TrafficSimulator(seed=seed)
        b_res, p_res = sim.run_ab_comparison(
            duration_s=90.0,
            ambulance_approach=app,
            ambulance_arrival_s=18.0 + (seed % 10),
        )

        run_id = f"demo_run_{seed}"
        doc = {
            "run_id": run_id,
            "seed": seed,
            "scenario": f"Ambulance approach {app}",
            "created_at": (
                datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=i * 2)
            ).isoformat(),
            "baseline_kpis": asdict(b_res.kpis),
            "priority_kpis": asdict(p_res.kpis),
            "baseline_trace": [asdict(f) for f in b_res.trace],
            "priority_trace": [asdict(f) for f in p_res.trace],
        }
        mongo.insert_sim_run(doc)
        print(f"   - Seeded {run_id}: Baseline wait={b_res.kpis.ambulance_wait_s}s -> Priority wait={p_res.kpis.ambulance_wait_s}s")

    print("2. Seeding historical priority events...")
    vehicles = [("ambulance", "N", "NS"), ("fire_truck", "E", "EW"), ("police_car", "S", "NS")]
    for j in range(12):
        v_class, app, axis = random.choice(vehicles)
        ev_id = f"ev_hist_{uuid.uuid4().hex[:8]}"
        start_t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=j * 15 + 10)
        mongo.insert_event({
            "event_id": ev_id,
            "approach": app,
            "axis": axis,
            "class": v_class,
            "started_at": start_t.isoformat(),
            "released_at": (start_t + datetime.timedelta(seconds=12)).isoformat(),
            "light_change_latency_ms": random.randint(1200, 2100),
            "outcome": "completed",
        })

    print("3. Seeding sample security events...")
    sample_threats = [
        ("192.168.1.105", "missing_token", "/api/v1/detections", "Unauthenticated client flood"),
        ("10.0.0.42", "invalid_or_expired_token", "/api/v1/intersections/i1/command", "Signature mismatch on forged JWT"),
        ("172.16.0.88", "forbidden_role", "/api/v1/security-events", "Camera role attempted admin access"),
        ("192.168.1.200", "rate_limit_exceeded", "/api/v1/detections", "Exceeded token bucket limit (25 req/s)"),
    ]
    for ip, reason, endpoint, details in sample_threats:
        mongo.insert_security_event({
            "source_ip": ip,
            "reason": reason,
            "endpoint": endpoint,
            "details": details,
            "ts": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=random.randint(5, 120))).isoformat(),
        })

    print("Successfully seeded demo data!")


if __name__ == "__main__":
    seed_demo_data()
