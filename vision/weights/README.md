# YOLO Weights Directory

Place your trained YOLO model weight file (`best.pt`) here.

## How to get `best.pt`

1. Open `vision/train/train_colab.ipynb` in Google Colab (free T4 GPU).
2. Follow the notebook steps to merge datasets and train `yolo11n` (or `yolov8n`).
3. Download the resulting `runs/detect/train/weights/best.pt`.
4. Copy it to this directory: `vision/weights/best.pt`.

## Notes

- This directory is **git-ignored** — do not commit model weights.
- If `best.pt` is missing, the vision worker will exit with a clear error message.
- For demo purposes, use `--mode replay` to bypass live inference entirely.
