"""Vision Worker: YOLO Inference, Debounce Filter, and Detections Pipeline.

Contract (PLAN.md Section 8 P4):
- Reads video stream or webcam.
- Processes every `stride` frames (stride 3 by default).
- Runs YOLO detector on CPU.
- Feeds detections through DebounceFilter.
- Posts raw and confirmed detections to /api/v1/detections.
- Supports --mode live and --mode replay.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

# Support both `python -m vision.worker` and `python vision/worker.py` from
# the repository root by making the project package importable in either form.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vision.debounce import DebounceFilter
from vision.replay import run_replay

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vision-worker")

CLASS_MAPPING = {
    0: "ambulance",
    1: "fire_truck",
    2: "police_car",
    3: "vehicle",
}


class VisionWorker:
    """YOLO vision pipeline with debounce filtering."""

    def __init__(
        self,
        weights_path: Path,
        api_url: str = "http://localhost:8000/api/v1",
        approach: str = "N",
        camera_id: str = "cam-N",
        stride: int = 3,
        conf_threshold: float = 0.55,
        imgsz: int = 640,
        camera_user: str = "camera",
        camera_pass: str = "camera123",
        debounce_window_w: int = 8,
        debounce_confirm_k: int = 5,
        bbox_area_ratio_min: float = 0.005,
        release_after_s: float = 3.0,
        class_mapping: dict[int, str] | None = None,
    ) -> None:
        self.weights_path = weights_path
        self.api_url = api_url
        self.approach = approach
        self.camera_id = camera_id
        self.stride = stride
        self.conf_threshold = conf_threshold
        self.imgsz = imgsz
        self.camera_user = camera_user
        self.camera_pass = camera_pass
        self.class_mapping = class_mapping or CLASS_MAPPING

        self.debounce = DebounceFilter(
            window_w=debounce_window_w,
            confirm_k=debounce_confirm_k,
            min_confidence=conf_threshold,
            min_bbox_area_ratio=bbox_area_ratio_min,
            release_after_s=release_after_s,
        )

        self.token: str | None = None
        self.model = None

    def authenticate(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.api_url}/auth/token",
                    json={"username": self.camera_user, "password": self.camera_pass},
                )
                if resp.status_code == 200:
                    self.token = resp.json()["access_token"]
                    logger.info("Vision worker authenticated successfully")
                    return True
                logger.error("Authentication failed: %s", resp.text)
        except Exception as e:
            logger.error("Could not reach API for auth: %s", e)
        return False

    def load_model(self) -> None:
        if not self.weights_path.exists():
            raise FileNotFoundError(
                f"Weights not found at {self.weights_path}.\n"
                f"Please follow the instructions in docs/HUMAN_TODO.md to train on Colab or use --mode replay."
            )
        try:
            from ultralytics import YOLO
            self.model = YOLO(str(self.weights_path))
            logger.info("Loaded YOLO model from %s", self.weights_path)
        except ImportError:
            logger.error("Ultralytics package not installed. Run: pip install ultralytics")
            raise

    def process_video(
        self,
        video_source: str,
        dump_replay_file: Path | None = None,
        max_frames: int = 1000,
    ) -> None:
        try:
            import cv2
        except ImportError:
            logger.error("opencv-python not installed. Run: pip install opencv-python")
            return

        cap = cv2.VideoCapture(int(video_source) if video_source.isdigit() else video_source)
        if not cap.isOpened():
            logger.error("Cannot open video source: %s", video_source)
            return

        frame_idx = 0
        dumped_detections: list[dict[str, Any]] = []

        logger.info("Starting inference stream on approach %s (stride %d)", self.approach, self.stride)

        with httpx.Client(timeout=3.0) as http_client:
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

            while cap.isOpened() and frame_idx < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_idx += 1
                if frame_idx % self.stride != 0:
                    continue

                h, w = frame.shape[:2]
                frame_area = float(h * w)

                # Inference
                results = self.model.predict(
                    source=frame,
                    imgsz=self.imgsz,
                    conf=self.conf_threshold,
                    verbose=False,
                )

                best_cls = "none"
                best_conf = 0.0
                best_area_ratio = 0.0

                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0].item())
                        cls_name = self.class_mapping.get(cls_id, "vehicle")
                        conf = float(box.conf[0].item())
                        xyxy = box.xyxy[0].tolist()
                        box_area = (xyxy[2] - xyxy[0]) * (xyxy[3] - xyxy[1])
                        area_ratio = box_area / frame_area

                        if cls_name in ("ambulance", "fire_truck", "police_car") and conf > best_conf:
                            best_cls = cls_name
                            best_conf = conf
                            best_area_ratio = area_ratio

                # Debounce evaluation
                now_s = time.time()
                debounce_res = self.debounce.update(
                    approach=self.approach,
                    vehicle_class=best_cls,
                    confidence=best_conf,
                    bbox_area_ratio=best_area_ratio,
                    frame_id=frame_idx,
                    timestamp_s=now_s,
                )

                payload = {
                    "camera_id": self.camera_id,
                    "approach": self.approach,
                    "class": debounce_res.dominant_class or best_cls,
                    "confidence": round(debounce_res.confidence or best_conf, 3),
                    "bbox_area_ratio": round(best_area_ratio, 4),
                    "frame_id": frame_idx,
                    "source_ts_ms": int(now_s * 1000),
                    "confirmed": debounce_res.confirmed,
                }

                if dump_replay_file:
                    dumped_detections.append(payload)

                # Post to backend
                if self.token:
                    try:
                        response = http_client.post(
                            f"{self.api_url}/detections",
                            json=payload,
                            headers=headers,
                        )
                        if response.is_success:
                            result = response.json()
                            action = result.get("action")
                            action_name = action.get("cmd") if isinstance(action, dict) else "none"
                            logger.info(
                                "Frame %d: %s on %s (confidence=%.2f, confirmed=%s) -> %s",
                                payload["frame_id"],
                                payload["class"],
                                payload["approach"],
                                payload["confidence"],
                                payload["confirmed"],
                                action_name,
                            )
                        else:
                            logger.warning(
                                "Detection rejected for frame %d: HTTP %d %s",
                                payload["frame_id"],
                                response.status_code,
                                response.text[:300],
                            )
                    except Exception as e:
                        logger.warning("Error posting detection: %s", e)

        cap.release()
        logger.info("Finished processing video stream.")

        if dump_replay_file:
            with open(dump_replay_file, "w", encoding="utf-8") as f:
                json.dump(dumped_detections, f, indent=2)
            logger.info("Saved %d detections to %s", len(dumped_detections), dump_replay_file)


def main():
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config.yaml"
    with config_path.open("r", encoding="utf-8") as config_file:
        vision_config = (yaml.safe_load(config_file) or {}).get("vision", {})

    parser = argparse.ArgumentParser(description="Emergency vehicle vision worker")
    parser.add_argument("--mode", choices=["live", "replay"], default="replay")
    parser.add_argument("--video", default="0", help="Video file or camera index")
    parser.add_argument("--max-frames", type=int, default=1000, help="Maximum frames to inspect for a bounded demo run")
    parser.add_argument("--weights", default=None)
    parser.add_argument("--replay-file", default="data/replay/demo_ambulance_north.json")
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--approach", default="N")
    parser.add_argument("--dump-replay", default=None, help="Save live run detections to JSON")
    parser.add_argument("--imgsz", type=int, default=None)
    parser.add_argument("--stride", type=int, default=None)
    parser.add_argument("--confidence", type=float, default=None)
    args = parser.parse_args()

    if args.mode == "replay":
        run_replay(Path(args.replay_file), api_url=args.api_url)
    else:
        weights_path = Path(args.weights or vision_config.get("model_weights", "vision/weights/best.pt"))
        if not weights_path.is_absolute():
            weights_path = project_root / weights_path
        worker = VisionWorker(
            weights_path=weights_path,
            api_url=args.api_url,
            approach=args.approach,
            stride=args.stride if args.stride is not None else int(vision_config.get("stride", 3)),
            conf_threshold=(
                args.confidence
                if args.confidence is not None
                else float(vision_config.get("conf_threshold", 0.55))
            ),
            imgsz=args.imgsz if args.imgsz is not None else int(vision_config.get("imgsz", 640)),
            debounce_window_w=int(vision_config.get("debounce_window_w", 8)),
            debounce_confirm_k=int(vision_config.get("debounce_confirm_k", 5)),
            bbox_area_ratio_min=float(vision_config.get("bbox_area_ratio_min", 0.005)),
            release_after_s=float(vision_config.get("release_after_s", 3.0)),
            class_mapping={int(k): str(v) for k, v in vision_config.get("classes", {}).items()},
        )
        if worker.authenticate():
            worker.load_model()
            worker.process_video(
                video_source=args.video,
                dump_replay_file=Path(args.dump_replay) if args.dump_replay else None,
                max_frames=args.max_frames,
            )


if __name__ == "__main__":
    main()
