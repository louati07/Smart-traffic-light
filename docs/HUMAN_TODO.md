# HUMAN_TODO.md — Manual Tasks & Human Credentials Tracker

> According to **Rule 1** in `PLAN.md`: Never invent URLs, dataset links, API keys, or package names. If a download or credential is needed, write a `TODO(HUMAN): ...` entry here, then continue with mocks.

## Completed Setup Tasks

- [x] **Firebase Realtime Database:** Project `emergency-traffic-controller` configured and tested with read/write operations verified.
- [x] **Roboflow Configuration:** API key configured; public datasets (`emergency-vehicle-ff3rh`, `emergency-rg2sy`, `emergency-vehcile-detection`) verified.
- [x] **Colab Training Pipeline:** Notebook [`train_colab.ipynb`](file:///c:/poly/SecondYearEng/S1/IOT/project/vision/train/train_colab.ipynb) generated with automatic multi-dataset download, remapping, and YOLO11n training.

## Active Human Tasks

- [ ] **TODO(HUMAN):** Open [`train_colab.ipynb`](file:///c:/poly/SecondYearEng/S1/IOT/project/vision/train/train_colab.ipynb) in Google Colab (with free T4 GPU), run all cells, and place the resulting `best.pt` in `vision/weights/best.pt`.
- [ ] **TODO(HUMAN):** Create a Wokwi project at [wokwi.com](https://wokwi.com); paste [`sketch.ino`](file:///c:/poly/SecondYearEng/S1/IOT/project/firmware/sketch.ino) and [`diagram.json`](file:///c:/poly/SecondYearEng/S1/IOT/project/firmware/diagram.json); add libraries from [`libraries.txt`](file:///c:/poly/SecondYearEng/S1/IOT/project/firmware/libraries.txt).
- [ ] **TODO(HUMAN):** Add 4–6 demo video clips (Section 7.2) to `data/videos/` and fill [`data/videos/README.md`](file:///c:/poly/SecondYearEng/S1/IOT/project/data/videos/README.md).
- [ ] **TODO(HUMAN):** Run `python vision/tools/augment_video.py` once demo clips are downloaded to generate night/noisy variants.
- [ ] **TODO(HUMAN):** Record the backup demo video.
