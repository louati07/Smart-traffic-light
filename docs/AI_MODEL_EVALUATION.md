# Emergency-Vehicle Model: Training and Inference Evidence

This note records evidence from the trained detector currently available in the development workspace. It distinguishes checkpoint-reported validation metrics from a separately reproduced accuracy test.

## Model checkpoint

| Item | Checkpoint evidence |
|---|---|
| Architecture | YOLO11n object detector |
| Initialization | Pretrained YOLO11n fine-tuned for this project; `pretrained=true` |
| Classes | `ambulance`, `fire_truck`, `police_car`, `vehicle` |
| Checkpoint metadata date | 2026-10-25 |
| Best-checkpoint epoch index | 18 (training config requested up to 50 epochs) |
| Training data config recorded in checkpoint | `processed_dataset/data.yaml` |
| Ultralytics version recorded in checkpoint | 8.4.189 |
| Weights file | `vision/weights/best.pt` (26,598,691 bytes in the tested workspace; intentionally excluded from Git) |
| SHA-256 of tested weights | `29f8f883cbd8e5c8e202ca69909f3aa45b6ae6b7f3cde0f2be6570085ec2de5d` |

The checkpoint contains actual model weights, class names, training arguments, epoch history, and validation metrics. The raw training dataset and `processed_dataset` are not present in this repository, so the dataset labels and training provenance cannot be independently audited from this checkout alone.

## Metrics recorded in the checkpoint

The checkpoint reports these box-detection metrics:

| Metric | Checkpoint value |
|---|---:|
| Precision | 0.81761 |
| Recall | 0.79297 |
| mAP@0.50 | 0.84886 |
| mAP@0.50:0.95 | 0.59068 |

These are **checkpoint-reported validation metrics**. The checkpoint training arguments identify `split=val`. They are not a newly reproduced independent test-set evaluation, and should not be presented as such. The checkpoint records epoch index 18 while the configured maximum was 50; the saved metadata does not establish why training ended at that point.

## Reproduced sampled-video inference

On 2026-11-01, the exact checkpoint above was loaded with Ultralytics 8.4.189 and run on three local MP4 clips. Eight evenly spaced frames were sampled from each clip at confidence threshold 0.55 and image size 640. The Python environment used PyTorch 2.6.0 CPU-only; the first model warm-up (8.46 seconds) is excluded from per-frame timings.

| Local video | Resolution | Sampled frames with detections | Predicted boxes by class | Mean / p95 processing time per sampled frame |
|---|---:|---:|---|---:|
| `11387588-hd_1920_1080_30fps.mp4` | 1920×1080 | 8/8 | 15 fire-truck boxes | 113 / 160 ms |
| `15285348-uhd_3840_2160_24fps.mp4` | 3840×2160 | 5/8 | 2 police-car, 3 fire-truck boxes | 328 / 1,560 ms |
| `istockphoto-936190804-640_adpp_is.mp4` | 768×432 | 5/8 | 5 ambulance boxes | 91 / 118 ms |

These are real model predictions on video frames, not entries from the replay JSON. The clips are not accompanied by frame-level ground-truth boxes in this repository, so the detection counts above demonstrate inference but do **not** measure accuracy. The 4K CPU timings are particularly variable and are not a real-time service guarantee.

## Reproduce locally

Install the vision dependencies and run the sampled inference report:

```bash
python -m pip install -r vision/requirements.txt
python vision/evaluate_model.py --sample-count 8 --save-images 2
```

The command reads `vision/weights/best.pt` and local `.mp4` files in `data/videos/`, then writes ignored local artifacts to `runs/ai_model_evaluation/`:

- `summary.json`: checkpoint fingerprint, runtime, per-video summary, and predictions by class.
- `predictions.csv`: per-frame class, confidence, box coordinates, and timing.
- `annotated_frames/`: sample video frames with the model's predicted boxes and labels.

For a full detection-to-controller demo, use the live worker against the offline mock API (the Wokwi/Firebase API should not be the target for this isolated test):

```bash
# Terminal 1: isolated in-memory API and mock ESP32
python scripts/run_demo.py

# Terminal 2: run the actual model on a local clip; 100 frames keeps the demo bounded
python vision/worker.py --mode live --video data/videos/istockphoto-936190804-640_adpp_is.mp4 --approach N --max-frames 100 --api-url http://127.0.0.1:8000/api/v1
```

On 2026-11-01, this exact integration run sent 33 sampled frames to an isolated offline API. Negative frames were accepted, the ambulance detections were confirmed by debounce at frame 30 (confidence 0.83), and the priority engine issued `PRIORITY seq=1` for approach N. The mock controller later issued `CLEAR seq=2` after the clip stopped producing detections. A read-back returned `controller_id=mock`, `last_seq=2`, and `state_fresh=true`. No Firebase/Wokwi endpoint received test commands.

The worker prints per-frame predicted class, confidence, debounce confirmation, and API action. This validates the model-to-software pipeline with a local video and mock controller; it is not a roadside-camera or physical-hardware trial. The original local footage source/license records are incomplete, so verify usage rights before redistributing the video or annotated frames.

## What would make this a stronger academic evaluation

1. Preserve the dataset version, class mapping, train/validation/test split, and dataset source/license records.
2. Run the saved checkpoint on a labelled, held-out test set that was not used to select checkpoints or thresholds.
3. Report per-class precision, recall, AP, confusion matrix, and missed/false detections, with the test image count.
4. Use labelled clips from the intended camera viewpoint, lighting, distance, and weather; keep one clip group entirely out of training.
5. Measure steady-state throughput and end-to-end detection-to-command latency on the actual AI host, separately from ESP32/Firebase timing.

Do not describe replay frames as model predictions, checkpoint validation metrics as independent test results, or simulator results as road-deployment performance.
