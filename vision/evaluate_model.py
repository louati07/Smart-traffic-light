"""Run the trained detector on local video and save reviewable evidence.

This is an inference smoke/evidence run, not an accuracy benchmark: unless
ground-truth boxes are supplied separately, precision/recall must not be
calculated from these predictions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * pct)
    return ordered[index]


def default_weights(project_root: Path) -> Path:
    with (project_root / "config.yaml").open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    path = Path(config.get("vision", {}).get("model_weights", "vision/weights/best.pt"))
    return path if path.is_absolute() else project_root / path


def run_evaluation(
    sources: list[Path],
    weights: Path,
    output_dir: Path,
    sample_count: int,
    confidence: float,
    image_size: int,
    save_images: int,
) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parent.parent
    os.environ.setdefault("YOLO_CONFIG_DIR", str(project_root / "runs" / ".ultralytics-config"))

    import cv2
    import numpy as np
    import torch
    from ultralytics import YOLO

    if not weights.is_file():
        raise FileNotFoundError(f"Model weights not found: {weights}")
    if sample_count < 1:
        raise ValueError("sample-count must be at least 1")

    video_paths: list[Path] = []
    for source in sources:
        if source.is_dir():
            video_paths.extend(sorted(source.glob("*.mp4")))
        elif source.is_file():
            video_paths.append(source)
        else:
            raise FileNotFoundError(f"Video source not found: {source}")
    video_paths = list(dict.fromkeys(p.resolve() for p in video_paths))
    if not video_paths:
        raise FileNotFoundError("No video files found. Pass one or more video files/directories.")

    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "annotated_frames"
    image_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(weights))
    names = model.names
    device = "cpu" if not torch.cuda.is_available() else 0
    warmup_started = time.perf_counter()
    model.predict(
        np.zeros((image_size, image_size, 3), dtype=np.uint8),
        imgsz=image_size,
        conf=confidence,
        device=device,
        verbose=False,
    )
    warmup_seconds = time.perf_counter() - warmup_started
    csv_path = output_dir / "predictions.csv"
    rows: list[dict[str, Any]] = []
    video_summaries: list[dict[str, Any]] = []

    for video_path in video_paths:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            video_summaries.append({"video": video_path.name, "error": "Could not open video"})
            continue

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if total_frames > 0:
            frame_indices = sorted({round(i * (total_frames - 1) / max(sample_count - 1, 1)) for i in range(min(sample_count, total_frames))})
        else:
            frame_indices = list(range(sample_count))

        latencies_ms: list[float] = []
        counts: dict[str, int] = {}
        detected_frames = 0
        saved_images = 0

        for frame_index in frame_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                continue

            started = time.perf_counter()
            result = model.predict(
                frame,
                imgsz=image_size,
                conf=confidence,
                device=device,
                verbose=False,
            )[0]
            latency_ms = (time.perf_counter() - started) * 1000.0
            latencies_ms.append(latency_ms)
            boxes = list(result.boxes) if result.boxes is not None else []
            if boxes:
                detected_frames += 1

            timestamp_s = frame_index / fps if fps > 0 else None
            if boxes:
                for box in boxes:
                    class_id = int(box.cls.item())
                    class_name = str(names.get(class_id, class_id))
                    confidence_value = float(box.conf.item())
                    xyxy = [round(float(value), 1) for value in box.xyxy[0].tolist()]
                    counts[class_name] = counts.get(class_name, 0) + 1
                    rows.append({
                        "video": video_path.name,
                        "frame": frame_index,
                        "timestamp_s": round(timestamp_s, 3) if timestamp_s is not None else "",
                        "class": class_name,
                        "confidence": round(confidence_value, 5),
                        "x1": xyxy[0], "y1": xyxy[1], "x2": xyxy[2], "y2": xyxy[3],
                        "inference_ms": round(latency_ms, 2),
                    })
            else:
                rows.append({
                    "video": video_path.name,
                    "frame": frame_index,
                    "timestamp_s": round(timestamp_s, 3) if timestamp_s is not None else "",
                    "class": "no_detection",
                    "confidence": "", "x1": "", "y1": "", "x2": "", "y2": "",
                    "inference_ms": round(latency_ms, 2),
                })

            if saved_images < save_images:
                annotated = result.plot()
                image_path = image_dir / f"{video_path.stem}_frame_{frame_index:06d}.jpg"
                cv2.imwrite(str(image_path), annotated)
                saved_images += 1

        capture.release()
        video_summaries.append({
            "video": video_path.name,
            "resolution": f"{width}x{height}",
            "fps": round(fps, 3),
            "duration_s": round(total_frames / fps, 3) if fps > 0 and total_frames else None,
            "frames_sampled": len(latencies_ms),
            "frames_with_detection": detected_frames,
            "detections_by_class": counts,
            "mean_inference_ms_per_sampled_frame": round(statistics.mean(latencies_ms), 2) if latencies_ms else None,
            "p95_inference_ms_per_sampled_frame": round(percentile(latencies_ms, 0.95), 2) if latencies_ms else None,
            "annotated_frames_saved": saved_images,
        })

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        fields = ["video", "frame", "timestamp_s", "class", "confidence", "x1", "y1", "x2", "y2", "inference_ms"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    checkpoint = getattr(model, "ckpt", None) or {}
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "evaluation_type": "sampled_video_inference; qualitative, no ground-truth accuracy calculated",
        "model": {
            "weights_file": weights.name,
            "sha256": sha256_file(weights),
            "ultralytics_version": checkpoint.get("version"),
            "checkpoint_date": checkpoint.get("date"),
            "checkpoint_epoch": checkpoint.get("epoch"),
            "checkpoint_train_metrics": checkpoint.get("train_metrics"),
            "class_names": names,
        },
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "device_used": "cuda:0" if torch.cuda.is_available() else "cpu",
            "warmup_seconds_excluded_from_frame_timings": round(warmup_seconds, 3),
            "imgsz": image_size,
            "confidence_threshold": confidence,
            "sample_count_per_video": sample_count,
        },
        "videos": video_summaries,
        "artifacts": {"predictions_csv": csv_path.name, "annotated_frames_dir": image_dir.name},
    }
    report_path = output_dir / "summary.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nSaved evidence to: {output_dir.resolve()}")
    return report


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Run the trained emergency-vehicle model on local video and save evidence.")
    parser.add_argument("sources", nargs="*", type=Path, help="Video files/directories (defaults to data/videos)")
    parser.add_argument("--weights", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("runs/ai_model_evaluation"))
    parser.add_argument("--sample-count", type=int, default=8, help="Evenly sampled frames per video")
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--save-images", type=int, default=3, help="Annotated frames to save per video")
    args = parser.parse_args()

    weights = args.weights or default_weights(project_root)
    if not weights.is_absolute():
        weights = project_root / weights
    sources = args.sources or [project_root / "data" / "videos"]
    sources = [source if source.is_absolute() else project_root / source for source in sources]
    output_dir = args.output_dir if args.output_dir.is_absolute() else project_root / args.output_dir
    run_evaluation(sources, weights, output_dir, args.sample_count, args.confidence, args.imgsz, args.save_images)


if __name__ == "__main__":
    main()
