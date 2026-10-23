# Smart Intersection Digital Twin with AI Emergency-Vehicle Priority

A connected 4-approach intersection system where traffic lights normally cycle via a fixed-timer, but when an emergency vehicle (ambulance, fire truck, police car) is detected by approach cameras, the system safely grants green priority, holds it until passage, and returns cleanly to normal operation.

## Architecture

```
Camera -> YOLO Detector -> Debounce Filter -> Priority Engine
                                                   |
                                                   v
           Web Dashboard (2D SVG) <--- Firebase Realtime DB ---> ESP32 / Wokwi Firmware
```

- **IoT (Wokwi):** ESP32 DevKit V1 with 12 LEDs (N, E, S, W x R/Y/G), buzzer, status LED, non-blocking safety FSM.
- **Backend (Python 3.11/3.12):** FastAPI REST API, WebSocket live feed, priority engine, deterministic A/B simulator.
- **Databases:** Firebase Realtime Database (REST) for live state mailbox; MongoDB for events, KPI records, and security logs.
- **Dashboard (Web):** React 18 + Vite + TypeScript 2D digital twin, A/B battle replay, live telemetry, security audit.
- **DevOps & Offline Strategy:** Complete offline execution mode with in-memory Firebase, mock ESP32 twin, and precomputed detection replays.

## Quickstart (Under 10 Commands)

```bash
# 1. Clone repository and navigate to folder
cd project

# 2. Configure environment
cp .env.example .env

# 3. Install backend dependencies
pip install -r server/requirements.txt

# 4. Install frontend dependencies
cd web && npm install && cd ..

# 5. Run tests (FSM safety invariants, golden scenarios, unit tests)
pytest server/tests

# 6. Launch offline demo mode
python scripts/seed_demo_data.py
python server/app/mock_esp32.py &
uvicorn server.app.main:app --reload --port 8000
```

Access the web dashboard at `http://localhost:5173` and API docs at `http://localhost:8000/docs`.

## Safety Invariants (S1–S7)

1. **S1**: The two axes are never green at the same time.
2. **S2**: Direct `G -> G` or `R -> G` without intermediate `Y` and `ALL_RED` is mathematically impossible.
3. **S3**: `YELLOW_MS` (3s) and `ALL_RED_MS` (2s) are never shortened by any command.
4. **S4**: Green lights are never cut before `MIN_GREEN_MS` (5s).
5. **S5**: Priority hold watchdog never exceeds `PRIORITY_MAX_MS` (30s).
6. **S6**: Unsigned, expired, invalid, or outdated commands are ignored; fallback to normal cycle.
7. **S7**: Priority release safely clears through yellow and all-red phases to opposite axis.

## License & Third-Party Notice

- Ultralytics YOLO is licensed under the AGPL-3.0 license, suitable for academic research and educational evaluation.
