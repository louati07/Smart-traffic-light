"""Events and Security Events queries.

GET /api/v1/events (Role: operator)
GET /api/v1/security-events (Role: admin)
"""

from typing import Any

from fastapi import APIRouter, Depends, Query

from server.app.auth import require_role
from server.app.clients.mongo import get_mongo_client
from server.app.config import settings

router = APIRouter(tags=["Events"])


@router.get("/events")
def get_priority_events(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(require_role(["operator", "admin"])),
) -> list[dict[str, Any]]:
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)
    return mongo.get_events(limit=limit, skip=skip)


@router.get("/security-events")
def get_security_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(require_role(["admin"])),
) -> list[dict[str, Any]]:
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)
    return mongo.get_security_events(limit=limit, skip=skip)
