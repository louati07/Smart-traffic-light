"""Intersections state and manual command overrides.

GET /api/v1/intersections/{id}/state (Role: operator)
POST /api/v1/intersections/{id}/command (Role: operator)
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from server.app.auth import require_role
from server.app.clients.firebase import get_firebase_client
from server.app.config import settings
from server.app.core.priority_engine import PriorityEngine

router = APIRouter(prefix="/intersections", tags=["Intersections"])

priority_engine_instance: PriorityEngine | None = None


def set_priority_engine(engine: PriorityEngine) -> None:
    global priority_engine_instance
    priority_engine_instance = engine


class ManualCommandInput(BaseModel):
    cmd: Literal["PRIORITY", "CLEAR"] = Field(..., example="PRIORITY")
    axis: Literal["NS", "EW"] | None = Field(None, example="NS")
    ttl_s: int = Field(default=15, ge=1, le=60, example=15)


@router.get("/{intersection_id}/state")
def get_intersection_state(
    intersection_id: str,
    user: dict[str, Any] = Depends(require_role(["operator", "admin"])),
) -> dict[str, Any]:
    firebase = get_firebase_client(
        mode=settings.firebase_mode,
        db_url=settings.firebase_db_url,
        db_secret=settings.firebase_db_secret,
    )
    state = firebase.get_state(intersection_id)
    if not state:
        # Return sensible default initial state if none written yet
        return {
            "phase": "NS_GREEN",
            "mode": "NORMAL",
            "lights": {"N": "G", "E": "R", "S": "G", "W": "R"},
            "last_seq": 0,
            "phase_elapsed_ms": 0,
            "uptime_ms": 0,
        }
    return state


@router.post("/{intersection_id}/command")
def issue_manual_command(
    intersection_id: str,
    cmd_body: ManualCommandInput,
    user: dict[str, Any] = Depends(require_role(["operator", "admin"])),
) -> dict[str, Any]:
    if cmd_body.cmd == "PRIORITY" and not cmd_body.axis:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "Field 'axis' is required for PRIORITY command"}},
        )

    if not priority_engine_instance:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "ENGINE_UNAVAILABLE", "message": "Priority engine not initialized"}},
        )

    operator_user = user.get("username", "operator")
    issued = priority_engine_instance.issue_manual_command(
        cmd=cmd_body.cmd,
        axis=cmd_body.axis,
        ttl_s=cmd_body.ttl_s,
        issued_by=f"operator:{operator_user}",
    )

    return {
        "status": "command_issued",
        "command": issued,
    }
