"""Deterministic Detection Replay Driver.

Contract (PLAN.md Section 7.3 & Section 8 P4):
Replays precomputed detection JSON traces to the API endpoint with realistic timings.
Zero ML/GPU dependencies required for live demo.
"""

import argparse
import json
import logging
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("replay")


def run_replay(
    file_path: Path,
    api_url: str = "http://localhost:8000/api/v1",
    speed: float = 1.0,
    camera_user: str = "camera",
    camera_pass: str = "camera123",
) -> None:
    if not file_path.exists():
        raise FileNotFoundError(f"Replay file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        detections = json.load(f)

    logger.info("Loaded %d detection frames from %s", len(detections), file_path)

    # 1. Obtain Camera JWT
    client = httpx.Client(timeout=5.0)
    auth_resp = client.post(
        f"{api_url}/auth/token",
        json={"username": camera_user, "password": camera_pass},
    )
    if auth_resp.status_code != 200:
        logger.error("Authentication failed: %s", auth_resp.text)
        return

    token = auth_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    logger.info("Obtained camera JWT token successfully")

    # 2. Replay frames
    for i, item in enumerate(detections, 1):
        delay = float(item.get("delay_s", 0.5)) / speed
        time.sleep(delay)

        payload = {
            "camera_id": item["camera_id"],
            "approach": item["approach"],
            "class": item["class"],
            "confidence": float(item["confidence"]),
            "bbox_area_ratio": float(item["bbox_area_ratio"]),
            "frame_id": int(item["frame_id"]),
            "source_ts_ms": int(time.time() * 1000),
            "confirmed": bool(item["confirmed"]),
        }

        try:
            resp = client.post(f"{api_url}/detections", json=payload, headers=headers)
            _res_data = resp.json() if resp.status_code == 200 else resp.text
            logger.info(
                "[%d/%d] Frame %d: %s on %s (conf=%.2f, confirmed=%s) -> HTTP %d",
                i,
                len(detections),
                payload["frame_id"],
                payload["class"],
                payload["approach"],
                payload["confidence"],
                payload["confirmed"],
                resp.status_code,
            )
        except Exception as e:
            logger.error("Failed to post detection: %s", e)

    logger.info("Replay sequence finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic detection replayer")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("data/replay/demo_ambulance_north.json"),
        help="Path to replay JSON file",
    )
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()

    run_replay(args.file, args.api_url, args.speed)
