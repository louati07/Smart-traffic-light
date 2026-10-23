"""Health check endpoint.

GET /api/v1/health (Public)
"""

import time
from typing import Any

from fastapi import APIRouter

from server.app.clients.firebase import get_firebase_client
from server.app.clients.mongo import get_mongo_client
from server.app.config import settings

router = APIRouter(tags=["Health"])

START_TIME = time.time()


@router.get("/health")
def get_health() -> dict[str, Any]:
    """Check connectivity to Mongo, Firebase, and uptime."""
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)
    firebase = get_firebase_client(
        mode=settings.firebase_mode,
        db_url=settings.firebase_db_url,
        db_secret=settings.firebase_db_secret,
    )

    mongo_ok = mongo.health_check()
    firebase_ok = firebase.health_check()
    uptime = time.time() - START_TIME

    overall_status = "ok" if (mongo_ok and firebase_ok) else "degraded"

    return {
        "status": overall_status,
        "mongo": mongo_ok,
        "firebase": firebase_ok,
        "uptime_s": round(uptime, 2),
    }
