# HUMAN_TODO.md — Manual Tasks & Human Credentials Tracker

> According to **Rule 1** in `PLAN.md`: Never invent URLs, dataset links, API keys, or package names. If a download or credential is needed, write a `TODO(HUMAN): ...` entry here, then continue with mocks.

## Completed Setup Tasks

- [ ] **Firebase Realtime Database:** Configure a database URL and credential in the API `.env` and firmware for connected-mode demonstrations. Do not commit credentials.
- [x] **Roboflow Configuration:** API key configured; public datasets (`emergency-vehicle-ff3rh`, `emergency-rg2sy`, `emergency-vehcile-detection`) verified.
- [x] **Colab Training Pipeline:** `vision/train/train_colab.ipynb` contains the dataset merge and YOLO training workflow.

## Active Human Tasks

- [ ] **TODO(HUMAN):** If demonstrating live inference, place the trained `best.pt` in `vision/weights/` (weights are ignored by Git). Replay mode does not require model weights.
- [ ] **TODO(HUMAN):** Create a Wokwi project at [wokwi.com](https://wokwi.com); paste `firmware/sketch.ino` and `firmware/diagram.json`; add libraries from `firmware/libraries.txt`.
- [ ] **TODO(HUMAN):** Add 4–6 demo video clips (Section 7.2) to `data/videos/` and fill `data/videos/README.md`.
- [ ] **TODO(HUMAN):** Run `python vision/tools/augment_video.py` once demo clips are downloaded to generate night/noisy variants.
- [ ] **TODO(HUMAN):** Record the backup demo video.
