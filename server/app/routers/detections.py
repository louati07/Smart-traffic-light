"""Detections submission endpoint.

POST /api/v1/detections (Role: camera)
"""

import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from server.app.auth import detection_rate_limiter, require_role
from server.app.clients.mongo import get_mongo_client
from server.app.config import settings
from server.app.core.priority_engine import ConfirmedDetection, PriorityEngine

router = APIRouter(tags=["Detections"])

# Will be set by main.py on startup
priority_engine_instance: PriorityEngine = None  # type: ignore


def set_priority_engine(engine: PriorityEngine) -> None:
    global priority_engine_instance
    priority_engine_instance = engine


class DetectionInput(BaseModel):
    camera_id: str = Field(..., example="cam-N")
    approach: Literal["N", "E", "S", "W"] = Field(..., example="N")
    # `none` is the vision worker's explicit negative-frame sentinel; it must
    # be accepted and stored but can never trigger emergency priority.
    class_name: Literal["ambulance", "fire_truck", "police_car", "vehicle", "none"] = Field(..., alias="class", example="ambulance")
    confidence: float = Field(..., ge=0.0, le=1.0, example=0.87)
    bbox_area_ratio: float = Field(..., ge=0.0, le=1.0, example=0.021)
    frame_id: int = Field(..., example=1234)
    source_ts_ms: int = Field(..., example=1760000000000)
    confirmed: bool = Field(..., example=True)

    model_config = {
        "populate_by_name": True,
    }


@router.post("/detections")
def submit_detection(
    det: DetectionInput,
    request: Request,
    user: dict[str, Any] = Depends(require_role(["camera", "operator", "admin"])),
) -> dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)

    # 1. Rate limiting check
    if not detection_rate_limiter.check(client_ip):
        mongo.insert_security_event({
            "source_ip": client_ip,
            "reason": "rate_limit_exceeded",
            "endpoint": "/detections",
            "details": f"Detection request flood from {client_ip}",
        })
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "RATE_LIMITED", "message": "Detection rate limit exceeded"}},
        )

    # 2. Store in MongoDB detections collection
    det_dict = det.model_dump(by_alias=True)
    mongo.insert_detection(det_dict)

    # 3. If confirmed=True and emergency class, pass to PriorityEngine
    action_taken = None
    if det.confirmed and det.class_name in ("ambulance", "fire_truck", "police_car") and priority_engine_instance:
        conf_det = ConfirmedDetection(
            camera_id=det.camera_id,
            approach=det.approach,
            vehicle_class=det.class_name,
            confidence=det.confidence,
            bbox_area_ratio=det.bbox_area_ratio,
            frame_id=det.frame_id,
            source_ts_ms=det.source_ts_ms,
            received_at_s=time.time(),
        )
        action_taken = priority_engine_instance.handle_detection(conf_det)

    return {
        "status": "received",
        "confirmed": det.confirmed,
        "action": action_taken,
    }
