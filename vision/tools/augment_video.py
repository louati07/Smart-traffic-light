"""Synthetic Video Augmentation Tool for Robustness Testing.

Generates variants from daytime video clips:
- Night/low-light (reduced brightness and gamma adjustment)
- Blur (Gaussian blur)
- Noise (Gaussian sensor noise)
- Glare / high contrast

Contract (PLAN.md Section 7.2 & Section 10):
Produces clip01_night.mp4, clip01_noisy.mp4, clip01_blur.mp4.
"""

import argparse
from pathlib import Path

import numpy as np


def augment_frame_night(frame: np.ndarray, brightness_factor: float = 0.35) -> np.ndarray:
    """Simulate night-time conditions via brightness and gamma scaling."""
    gamma = 1.6
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
    dark = (frame.astype("float32") * brightness_factor).astype("uint8")
    try:
        import cv2
        return cv2.LUT(dark, table)
    except ImportError:
        return dark


def augment_frame_noise(frame: np.ndarray, sigma: float = 25.0) -> np.ndarray:
    """Add Gaussian sensor noise."""
    noise = np.random.normal(0, sigma, frame.shape)
    noisy = np.clip(frame.astype("float32") + noise, 0, 255).astype("uint8")
    return noisy


def augment_frame_blur(frame: np.ndarray, ksize: int = 15) -> np.ndarray:
    """Add optical or motion blur."""
    try:
        import cv2
        return cv2.GaussianBlur(frame, (ksize, ksize), 0)
    except ImportError:
        return frame


def process_video(input_path: Path, output_dir: Path, variant: str = "night") -> None:
    try:
        import cv2
    except ImportError:
        print("OpenCV not installed. Install with: pip install opencv-python")
        return

    if not input_path.exists():
        print(f"Input video not found: {input_path}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    out_filename = f"{input_path.stem}_{variant}.mp4"
    out_path = output_dir / out_filename

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        print(f"Could not open {input_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

    print(f"Augmenting {input_path} into {out_path} ({variant})...")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if variant == "night":
            aug = augment_frame_night(frame)
        elif variant == "noisy":
            aug = augment_frame_noise(frame)
        elif variant == "blur":
            aug = augment_frame_blur(frame)
        else:
            aug = frame

        writer.write(aug)

    cap.release()
    writer.release()
    print(f"Generated {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("data/videos/augmented"), type=Path)
    parser.add_argument("--variant", choices=["night", "noisy", "blur"], default="night")
    args = parser.parse_args()

    process_video(args.input, args.output_dir, args.variant)
