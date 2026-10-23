# Demo Videos Directory

Place 4-6 short demo clips here (15-30 seconds, 720p or lower).

## Required Clips

| # | Filename            | Description                                   | Source             | License       | Downloaded |
|---|---------------------|-----------------------------------------------|--------------------|--------------:|:----------:|
| 1 | `clip01_day.mp4`    | Day, ambulance approaching intersection       | TODO(HUMAN)        | TODO          | [ ]        |
| 2 | `clip02_day.mp4`    | Day, fire / civil-protection truck             | TODO(HUMAN)        | TODO          | [ ]        |
| 3 | `clip03_day.mp4`    | Day, police car                                | TODO(HUMAN)        | TODO          | [ ]        |
| 4 | `clip04_normal.mp4` | Normal traffic only (no emergency vehicle)     | TODO(HUMAN)        | TODO          | [ ]        |
| 5 | `clip05_night.mp4`  | Night/low-light, emergency vehicle (optional)  | TODO(HUMAN)        | TODO          | [ ]        |
| 6 | `clip06_rain.mp4`   | Rain/glare, emergency vehicle (optional)       | TODO(HUMAN)        | TODO          | [ ]        |

## Where to Find Clips

- **Pexels** (pexels.com) — free stock video, check license text
- **Pixabay** (pixabay.com) — free stock video
- **YouTube** — filter by Creative Commons license
- **Wikimedia Commons** — public domain / CC content
- **Own recordings** — from a safe vantage point

## Synthetic Variants

After downloading day clips, run `vision/tools/augment_video.py` to generate:
- `clip01_night.mp4` — reduced brightness/gamma
- `clip01_noisy.mp4` — Gaussian noise
- `clip01_blur.mp4`  — blur effect

## Notes

- This directory is **git-ignored** — do not commit video files.
- Fill in the source URL and license for each clip before the final report.
