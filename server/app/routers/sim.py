"""Simulation routes: Deterministic A/B comparison and replay traces.

POST /api/v1/sim/run (Role: operator)
GET /api/v1/sim/runs/{run_id} (Role: operator)
"""

import datetime
import uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from server.app.auth import require_role
from server.app.clients.mongo import get_mongo_client
from server.app.config import settings
from server.app.core.sim import TrafficSimulator

router = APIRouter(prefix="/sim", tags=["Simulation"])


class SimRunRequest(BaseModel):
    seed: int = Field(default=42, example=42)
    scenario: str = Field(default="default", example="default")
    duration_s: float = Field(default=90.0, ge=30.0, le=300.0)
    ambulance_approach: str = Field(default="N", example="N")
    ambulance_arrival_s: float = Field(default=18.0, ge=5.0)


@router.post("/run")
def run_simulation(
    req: SimRunRequest,
    user: dict[str, Any] = Depends(require_role(["operator", "admin"])),
) -> dict[str, Any]:
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)
    sim = TrafficSimulator(seed=req.seed)
    baseline_res, priority_res = sim.run_ab_comparison(
        duration_s=req.duration_s,
        ambulance_approach=req.ambulance_approach,
        ambulance_arrival_s=req.ambulance_arrival_s,
    )

    run_id = f"sim_{uuid.uuid4().hex[:10]}"
    doc = {
        "run_id": run_id,
        "seed": req.seed,
        "scenario": req.scenario,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "baseline_kpis": asdict(baseline_res.kpis),
        "priority_kpis": asdict(priority_res.kpis),
        "baseline_trace": [asdict(f) for f in baseline_res.trace],
        "priority_trace": [asdict(f) for f in priority_res.trace],
    }

    mongo.insert_sim_run(doc)

    return {
        "run_id": run_id,
        "seed": req.seed,
        "scenario": req.scenario,
        "baseline_kpis": doc["baseline_kpis"],
        "priority_kpis": doc["priority_kpis"],
    }


@router.get("/runs/{run_id}")
def get_simulation_run(
    run_id: str,
    user: dict[str, Any] = Depends(require_role(["operator", "admin"])),
) -> dict[str, Any]:
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)
    res = mongo.get_sim_run(run_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": f"Simulation run {run_id} not found"}},
        )
    return res
