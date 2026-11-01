"""FastAPI Application Entry Point.

Contract (PLAN.md Section 5.2):
- Prefix /api/v1
- Background tasks:
  1. Heartbeat generator (counter +1 every 2s in Firebase)
  2. Priority engine ticker (ticks every 0.5s)
  3. Embedded MockESP32Twin (if ESP32_MODE=mock)
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.app.clients.firebase import get_firebase_client
from server.app.clients.mongo import get_mongo_client
from server.app.config import settings
from server.app.core.priority_engine import PriorityEngine
from server.app.mock_esp32 import MockESP32Twin
from server.app.routers import (
    auth,
    detections,
    events,
    health,
    intersections,
    kpi,
    sim,
    ws,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

heartbeat_task: asyncio.Task | None = None
engine_tick_task: asyncio.Task | None = None
mock_esp32_instance: MockESP32Twin | None = None


async def heartbeat_loop(intersection_id: str):
    """Increment heartbeat counter in Firebase every 2 seconds."""
    firebase = get_firebase_client(
        mode=settings.firebase_mode,
        db_url=settings.firebase_db_url,
        db_secret=settings.firebase_db_secret,
    )
    while True:
        try:
            val = firebase.increment_heartbeat(intersection_id)
            logger.debug("Heartbeat counter incremented to %d", val)
        except Exception as e:
            logger.error("Heartbeat error: %s", e)
        await asyncio.sleep(2.0)


async def engine_ticker(engine: PriorityEngine):
    """Tick priority engine every 0.5s to handle release timeouts and conflict queues."""
    while True:
        try:
            await asyncio.to_thread(engine.tick)
        except Exception as e:
            logger.error("Engine tick error: %s", e)
        await asyncio.sleep(0.5)


def init_priority_engine() -> PriorityEngine:
    """Initialize and wire the global PriorityEngine instance."""
    firebase = get_firebase_client(
        mode=settings.firebase_mode,
        db_url=settings.firebase_db_url,
        db_secret=settings.firebase_db_secret,
    )
    mongo = get_mongo_client(
        mode=settings.mongo_mode,
        uri=settings.mongo_uri,
        db_name=settings.mongo_db,
    )

    engine_cfg = settings.engine_config
    timings = settings.timings
    engine = PriorityEngine(
        firebase_client=firebase,
        mongo_client=mongo,
        intersection_id=settings.intersection_id,
        release_after_s=float(settings.vision_config.get("release_after_s", 3.0)),
        cooldown_s=float(engine_cfg.get("priority_cooldown_s", 2.0)),
        conflict_max_wait_s=float(engine_cfg.get("priority_conflict_max_wait_s", 15.0)),
        command_ttl_s=int(timings.get("command_ttl_s", 15)),
        hmac_secret=settings.hmac_secret,
        hmac_enforce=settings.hmac_enforce,
    )

    detections.set_priority_engine(engine)
    intersections.set_priority_engine(engine)
    return engine


# Eagerly initialize so routers and tests always have an active engine
global_priority_engine = init_priority_engine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global heartbeat_task, engine_tick_task, mock_esp32_instance

    engine = global_priority_engine

    # Launch background tasks
    heartbeat_task = asyncio.create_task(heartbeat_loop(settings.intersection_id))
    engine_tick_task = asyncio.create_task(engine_ticker(engine))

    # Launch Mock ESP32 if configured
    if settings.esp32_mode.lower() == "mock":
        fb = get_firebase_client(
            mode=settings.firebase_mode,
            db_url=settings.firebase_db_url,
            db_secret=settings.firebase_db_secret,
        )
        mock_esp32_instance = MockESP32Twin(
            firebase_client=fb,
            intersection_id=settings.intersection_id,
            poll_interval_s=float(settings.timings.get("poll_ms", 1000)) / 1000.0,
            hmac_secret=settings.hmac_secret,
            hmac_enforce=settings.hmac_enforce,
        )
        mock_esp32_instance.start()
        logger.info("Auto-launched Mock ESP32 Twin for offline mode")

    logger.info("Smart Intersection API Server initialized successfully")

    yield

    # Teardown
    if heartbeat_task:
        heartbeat_task.cancel()
    if engine_tick_task:
        engine_tick_task.cancel()
    if mock_esp32_instance:
        mock_esp32_instance.stop()
    logger.info("Smart Intersection API Server shut down cleanly")


app = FastAPI(
    title="Smart Intersection Digital Twin API",
    version="1.0.0",
    description="Emergency Vehicle Priority Orchestration & Deterministic A/B Digital Twin",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 Router Registration
API_V1_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_V1_PREFIX)
app.include_router(auth.router, prefix=API_V1_PREFIX)
app.include_router(detections.router, prefix=API_V1_PREFIX)
app.include_router(intersections.router, prefix=API_V1_PREFIX)
app.include_router(events.router, prefix=API_V1_PREFIX)
app.include_router(sim.router, prefix=API_V1_PREFIX)
app.include_router(kpi.router, prefix=API_V1_PREFIX)
app.include_router(ws.router, prefix=API_V1_PREFIX)

# Also expose health directly at /health for docker-compose and load balancer health checks
app.include_router(health.router)


@app.get("/")
def root():
    return {
        "title": "Smart Intersection Digital Twin API",
        "docs_url": "/docs",
        "health_url": "/api/v1/health",
    }
