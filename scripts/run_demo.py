"""Start the API in a self-contained offline demo configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# Environment variables take precedence over .env in the application settings.
# Keep this process isolated from live Firebase/Wokwi settings on the developer's
# machine while leaving their local .env file untouched.
os.environ["FIREBASE_MODE"] = "memory"
os.environ["ESP32_MODE"] = "mock"
os.environ["MONGO_MODE"] = "memory"

import uvicorn  # noqa: E402


if __name__ == "__main__":
    uvicorn.run(
        "server.app.main:app",
        host=os.environ.get("API_HOST", "0.0.0.0"),
        port=int(os.environ.get("API_PORT", "8000")),
    )
