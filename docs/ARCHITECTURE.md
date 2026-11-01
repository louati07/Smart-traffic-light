# ARCHITECTURE.md — Smart Intersection Digital Twin

## 1. System Overview

The **Smart Intersection Digital Twin** demonstrates emergency-vehicle priority on one 4-approach intersection (`i1`). A priority command identifies one approach; while it is held, that approach alone receives green and the other three remain red. Its Python mock is the offline reference implementation; the Wokwi firmware mirrors its controller timings and communicates through Firebase in connected mode. The A/B simulator is a separate deterministic experiment, not a live measurement of the physical controller.

```
       +-------------------------------------------------------+
       |                  Vision Layer (YOLO)                  |
       |  Video Stream -> Stride/Inference -> Debounce Window   |
       +---------------------------+---------------------------+
                                   | POST /api/v1/detections (confirmed=true)
                                   v
+----------------------------------------------------------------------+
|                     Server Layer (FastAPI Backend)                   |
|                                                                      |
|   +-------------------+       +----------------------------------+   |
|   |   Auth & Security |       |         Priority Engine          |   |
|   | (JWT + RateLimit) |       |  (Debounce -> Command Generator) |   |
|   +-------------------+       +-----------------+----------------+   |
|                                                 |                    |
|   +-------------------+                         | Write /command     |
|   | Deterministic Sim |                         v                    |
|   | (A/B Test Engine) |       +----------------------------------+   |
|   +-------------------+       | Firebase Bridge / In-Memory Mock |   |
|                               +-----------------+----------------+   |
+-------------------------------------------------|--------------------+
                                                  |
                         +------------------------+------------------------+
                         | REST JSON                               | REST JSON
                         v                                         v
       +-----------------------------------+     +-----------------------------------+
       |     Wokwi ESP32 Firmware          |     |    Web Dashboard (React + TS)     |
       |  Local Non-Blocking FSM           |     |  2D SVG Twin + A/B Replay         |
       |  12 LEDs (N, E, S, W) + Buzzer    |     |  WebSocket /ws/state              |
       |  Fallback on Heartbeat Loss       |     |  Security Log & Event Analytics   |
       +-----------------------------------+     +-----------------------------------+
```

## 2. Layers & Responsibilities

1. **IoT Layer (ESP32 DevKit V1 in Wokwi)**
   - Local deterministic Finite State Machine (FSM).
   - Driven purely by non-blocking `millis()`.
   - 12 Traffic Light LEDs (N, E, S, W approaches x R, Y, G) + Status LED + Buzzer.
   - Runs the local signal FSM. Emergency commands identify one approach, and the controller gates the other three signals red during the priority green.
   - In deployment, roadside camera/video feeds connect to the host-side vision worker. The ESP32 receives only the resulting approach-specific command through Firebase; it does not run YOLO or capture video.
   - Reverts to `FALLBACK` mode if server heartbeat fails for >10 s. Firmware does not currently verify HMAC signatures.

2. **Server Layer (FastAPI)**
   - REST API `/api/v1` and authenticated WebSocket `/api/v1/ws/state`.
   - Priority engine carries the requested approach with each command and queues competing approaches.
   - Heartbeat generator (+1 counter every 2 seconds).
   - In-memory fallback support (`FIREBASE_MODE=memory`, `MONGO_MODE=memory`).
   - Deterministic discrete-event simulation engine with seeded Poisson arrivals.

3. **Database Layer**
   - **Firebase Realtime Database (REST API)**: High-speed mailbox for `/command`, `/state`, and `/heartbeat`.
   - **MongoDB 7**: Historical archive for confirmed detections, priority events, A/B simulation runs, and security audit events.

4. **Vision Layer**
   - Lightweight YOLO (YOLOv8n / YOLO11n) running on CPU (stride 3, imgsz 640/480).
   - Sliding-window debounce filter, configured by `config.yaml` (defaults: W=8, K=5, confidence >= 0.55, area ratio >= 0.005).
   - Zero-dependency deterministic replay mode for offline demonstrations.
   - The detector and debounce result are inspectable in the API/events/dashboard; only confirmed emergency detections are allowed to request signal priority.

5. **Interface Layer (React 18 + Vite + TS)**
   - 2D SVG Digital Twin showing live animated vehicle movements and intersection lights.
   - Synchronized A/B Battle comparing baseline fixed-timer against priority engine.
   - Live KPI cards, Security Audit log, and System Health Monitor.

## 3. Safety Invariants (S1–S7)

- **S1**: The two axes (`NS` and `EW`) are never green at the same time.
- **S2**: An axis never transitions `G -> G` or `R -> G` without intermediate `Y` and `ALL_RED` clearance phases.
- **S3**: Normal clearance is `YELLOW_MS` (3000 ms) + `ALL_RED_MS` (2000 ms). The Wokwi demo uses 2000 ms yellow + 1000 ms all-red for emergency preemption, after the 5000 ms minimum green.
- **S4**: A green light is never terminated before `MIN_GREEN_MS` (5000 ms).
- **S5**: Priority hold never exceeds `PRIORITY_MAX_MS` (30000 ms).
- **S6**: Controller rejects malformed or outdated sequence commands and enters fallback on heartbeat loss. HMAC enforcement is available in the Python mock when enabled; firmware verification is not implemented.
- **S7**: Priority release always transitions cleanly via `Y -> ALL_RED -> opposite axis`.

## 4. Performance Targets (not yet benchmark results)

- Inference: >= 8 FPS on standard CPU.
- Detections API latency: p95 < 200 ms.
- End-to-end command-to-light latency: < 2.5 s.
- Idle memory footprint: < 3 GB RAM.
