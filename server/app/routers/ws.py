"""WebSocket live telemetry stream.

WS /api/v1/ws/state (Token in query parameter)
Pushes intersection state, heartbeat, and active events every <= 1 s.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.app.auth import decode_access_token
from server.app.clients.firebase import get_firebase_client
from server.app.clients.mongo import get_mongo_client
from server.app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/state")
async def websocket_intersection_state(websocket: WebSocket, token: str | None = None):
    # Browser WebSockets cannot set Authorization headers, so use a short-lived
    # query token and enforce the same operator/admin access as state endpoints.
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return
    try:
        claims = decode_access_token(token)
        if claims.get("role") not in {"operator", "admin"}:
            raise ValueError("Insufficient role")
    except Exception:
        await websocket.close(code=4001, reason="Invalid token or role")
        return

    await websocket.accept()

    firebase = get_firebase_client(
        mode=settings.firebase_mode,
        db_url=settings.firebase_db_url,
        db_secret=settings.firebase_db_secret,
    )
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)

    last_known_state = None

    try:
        while True:
            fetched_state = await asyncio.to_thread(firebase.get_state, settings.intersection_id)
            if fetched_state:
                last_known_state = fetched_state
            state_age_s = await asyncio.to_thread(firebase.get_state_age_s, settings.intersection_id)

            heartbeat = await asyncio.to_thread(firebase.get_heartbeat, settings.intersection_id)
            recent_events = await asyncio.to_thread(mongo.get_events, 5)

            payload = {
                "intersection_id": settings.intersection_id,
                "state": last_known_state or {
                    "phase": "NS_GREEN",
                    "mode": "NORMAL",
                    "lights": {"N": "G", "E": "R", "S": "G", "W": "R"},
                    "last_seq": 0,
                    "phase_elapsed_ms": 0,
                    "uptime_ms": 0,
                    "priority_approach": None,
                },
                "state_age_s": state_age_s,
                "state_fresh": state_age_s is not None and state_age_s <= 4.0,
                "heartbeat": heartbeat,
                "recent_events": recent_events,
            }

            await websocket.send_text(json.dumps(payload))
            # Firebase is polled by REST, so a 150ms loop queues redundant
            # reads while upstream latency is higher. Two updates per second
            # are sufficient for the live traffic signal display.
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
        try:
            await websocket.close()
        except Exception:
            pass
