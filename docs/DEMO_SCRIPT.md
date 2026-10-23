# DEMO_SCRIPT.md — 6-7 Minute Live Demonstration Script

## Overview
Target time: **6 to 7 minutes**.
Runs on student laptop (CPU only) in live or replay mode (`make demo`).

---

### Step 1: The Problem (30 seconds)
- **Visual:** Fixed-timer intersection.
- **Narration:** "In conventional smart cities, emergency vehicles get trapped behind red lights and standing queues. Every 60 seconds of delay drops cardiac arrest survival rates by 7-10%."
- **Action:** Show baseline simulation replay on the Compare page where an ambulance waits 20+ seconds at a red light.

### Step 2: The Live Moment (90 seconds)
- **Visual:** Dashboard Live Twin side-by-side with Wokwi ESP32 or terminal stream.
- **Action:** Run the vision worker on an approaching ambulance video clip (or `--mode replay`).
- **Observation:**
  - Detections appear with bounding boxes and debounce confidence score.
  - At confirmation, the priority engine issues `PRIORITY(axis=NS)`.
  - The FSM respects minimum green, transitions through yellow and all-red safely.
  - The ambulance gets green; lights on Wokwi and the 2D SVG Twin switch synchronously.
  - Once the vehicle clears, system holds green until safe transition resumes normal timer.

### Step 3: A/B Battle & System KPIs (60 seconds)
- **Visual:** Compare page (`/sim/runs/{id}`).
- **Action:** Trigger side-by-side synchronized replay between Baseline and Priority mode.
- **Observation:**
  - Emergency vehicle crossing time: marked reduction (e.g., -14 seconds).
  - Delay impact on other approaches: minimal and quantified.
  - Queue recovery time tracked to baseline equilibrium.

### Step 4: Kill-Switch & Resilience (45 seconds)
- **Action:** Execute `scripts/kill_switch_demo.sh` (or terminate heartbeat).
- **Observation:**
  - ESP32 detects heartbeat expiration (>10s).
  - Mode transitions to `FALLBACK`.
  - Buzzer/status LED alerts, lights safely cycle normal fixed timer.
  - Invariants S1-S7 remain completely intact.

### Step 5: Security Attack Demo (60 seconds)
- **Action:** Run `python scripts/attack_demo.py`.
- **Observation:**
  - Test 1: Missing JWT -> 401 Unauthorized.
  - Test 2: Forged token -> 403 Forbidden.
  - Test 3: Detection flood -> Rate limit 429 Too Many Requests.
  - Test 4: Replayed sequence / Bad HMAC signature -> Rejected by controller.
  - Security dashboard displays real-time security events logged to MongoDB.

### Step 6: Numbers & Model Metrics (45 seconds)
- Review YOLO metrics (mAP50, precision, recall), CPU FPS, and end-to-end latency (< 2.5s).

### Step 7: Limits & Future Work (30 seconds)
- Wrap up: Camera occlusion limits, addition of acoustic siren detection, V2X connected vehicle integration.
