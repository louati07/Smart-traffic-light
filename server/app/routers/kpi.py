"""KPI aggregated summary endpoint.

GET /api/v1/kpi/summary (Role: operator)
"""

from typing import Any

from fastapi import APIRouter, Depends

from server.app.auth import require_role
from server.app.clients.mongo import get_mongo_client
from server.app.config import settings

router = APIRouter(prefix="/kpi", tags=["KPI"])


@router.get("/summary")
def get_kpi_summary(
    user: dict[str, Any] = Depends(require_role(["operator", "admin"])),
) -> dict[str, Any]:
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)
    runs = mongo.get_all_sim_runs(limit=100)

    if not runs:
        return {
            "total_runs": 0,
            "avg_ambulance_wait_baseline_s": 0.0,
            "avg_ambulance_wait_priority_s": 0.0,
            "avg_time_saved_s": 0.0,
            "avg_extra_delay_others_s": 0.0,
            "avg_recovery_time_s": 0.0,
            "pct_wait_reduction": 0.0,
        }

    total_runs = len(runs)
    sum_b_wait = sum(r.get("baseline_kpis", {}).get("ambulance_wait_s", 0.0) for r in runs)
    sum_p_wait = sum(r.get("priority_kpis", {}).get("ambulance_wait_s", 0.0) for r in runs)
    sum_extra_delay = sum(r.get("priority_kpis", {}).get("extra_delay_others_s", 0.0) for r in runs)
    sum_recovery = sum(r.get("priority_kpis", {}).get("recovery_time_s", 0.0) for r in runs)

    avg_b_wait = round(sum_b_wait / total_runs, 2)
    avg_p_wait = round(sum_p_wait / total_runs, 2)
    avg_saved = round(avg_b_wait - avg_p_wait, 2)
    pct_reduction = round((avg_saved / avg_b_wait * 100.0) if avg_b_wait > 0 else 0.0, 1)

    return {
        "total_runs": total_runs,
        "avg_ambulance_wait_baseline_s": avg_b_wait,
        "avg_ambulance_wait_priority_s": avg_p_wait,
        "avg_time_saved_s": avg_saved,
        "avg_extra_delay_others_s": round(sum_extra_delay / total_runs, 2),
        "avg_recovery_time_s": round(sum_recovery / total_runs, 2),
        "pct_wait_reduction": pct_reduction,
    }
