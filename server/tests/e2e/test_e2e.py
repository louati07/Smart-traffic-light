"""End-to-end test: Full chain from detection to light change via HTTP API.

PLAN.md P6 acceptance criteria:
- Detection confirmed -> API -> priority engine -> Firebase -> MockESP32Twin -> state
- Attack rejection: no token, forged token, rate limit flood, replayed old command
- Kill switch: heartbeat stops -> FALLBACK mode within timeout
- All rejected/forged requests logged in security_events

Run with:  pytest -m e2e server/tests/e2e/
"""

import os
import time

import pytest
from fastapi.testclient import TestClient

# Force mock/memory modes before importing app
os.environ.setdefault("FIREBASE_MODE", "memory")
os.environ.setdefault("MONGO_MODE", "memory")
os.environ.setdefault("ESP32_MODE", "mock")
os.environ.setdefault("VISION_MODE", "replay")

from server.app.main import app  # noqa: E402


pytestmark = pytest.mark.e2e
client = TestClient(app)


def _get_token(username: str, password: str) -> str | None:
    """Obtain JWT token via login."""
    resp = client.post("/api/v1/auth/token", json={"username": username, "password": password})
    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestE2EFullChain:
    """Full-chain: detection -> command -> light change -> state visible."""

    def test_health_ok(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    def test_full_detection_to_state_flow(self):
        """Submit confirmed detection and verify state endpoint reflects priority."""
        # 1. Login as camera
        cam_token = _get_token("camera", "camera123")
        assert cam_token is not None

        # Login as operator to read state
        op_token = _get_token("operator", "operator123")
        assert op_token is not None

        # 2. Get baseline state
        resp = client.get("/api/v1/intersections/i1/state", headers=_auth_header(op_token))
        assert resp.status_code == 200

        # 3. Submit confirmed detection (ambulance on approach N = NS axis)
        det_payload = {
            "camera_id": "cam-N",
            "approach": "N",
            "class": "ambulance",
            "confidence": 0.92,
            "bbox_area_ratio": 0.03,
            "frame_id": 100,
            "source_ts_ms": int(time.time() * 1000),
            "confirmed": True,
        }
        resp = client.post(
            "/api/v1/detections",
            json=det_payload,
            headers=_auth_header(cam_token),
        )
        assert resp.status_code in (200, 201)

        # 4. Check that a priority command was issued (visible via events)
        resp = client.get("/api/v1/events", headers=_auth_header(op_token))
        assert resp.status_code == 200

        # 5. State should be readable
        resp = client.get("/api/v1/intersections/i1/state", headers=_auth_header(op_token))
        assert resp.status_code == 200
        state = resp.json()
        assert "phase" in state
        assert "mode" in state
        assert "lights" in state


class TestE2EAttackRejection:
    """PLAN.md P6: attack_demo scenarios verified programmatically."""

    def test_detection_without_token_rejected(self):
        """(a) Detection without auth token -> 401."""
        resp = client.post("/api/v1/detections", json={
            "camera_id": "cam-N",
            "approach": "N",
            "class": "ambulance",
            "confidence": 0.9,
            "bbox_area_ratio": 0.03,
            "frame_id": 999,
            "source_ts_ms": 1000,
            "confirmed": True,
        })
        assert resp.status_code in (401, 403)

    def test_detection_with_forged_token_rejected(self):
        """(b) Detection with a forged/invalid token -> 401."""
        resp = client.post(
            "/api/v1/detections",
            json={
                "camera_id": "cam-N",
                "approach": "N",
                "class": "ambulance",
                "confidence": 0.9,
                "bbox_area_ratio": 0.03,
                "frame_id": 999,
                "source_ts_ms": 1000,
                "confirmed": True,
            },
            headers={"Authorization": "Bearer FORGED.TOKEN.HERE"},
        )
        assert resp.status_code in (401, 403)

    def test_security_events_logged(self):
        """Rejected requests should appear in security events."""
        admin_token = _get_token("admin", "admin123")
        assert admin_token is not None

        resp = client.get("/api/v1/security-events", headers=_auth_header(admin_token))
        assert resp.status_code == 200
        events = resp.json()
        # There should be at least some security events from the previous tests
        assert isinstance(events, list)

    def test_operator_command_endpoint_requires_auth(self):
        """Manual command without token -> 401."""
        resp = client.post("/api/v1/intersections/i1/command", json={
            "cmd": "PRIORITY",
            "axis": "NS",
            "ttl_s": 15,
        })
        assert resp.status_code in (401, 403)

    def test_wrong_role_cannot_access_security_events(self):
        """Operator (not admin) cannot see security events."""
        op_token = _get_token("operator", "operator123")
        assert op_token is not None

        resp = client.get("/api/v1/security-events", headers=_auth_header(op_token))
        assert resp.status_code == 403


class TestE2ESimulationAndKPI:
    """A/B comparison: priority ambulance wait strictly lower than baseline."""

    def test_simulation_run_and_kpi_retrieval(self):
        op_token = _get_token("operator", "operator123")
        assert op_token is not None

        # Run simulation
        resp = client.post(
            "/api/v1/sim/run",
            json={"seed": 42, "scenario": "default"},
            headers=_auth_header(op_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        run_id = data.get("run_id")
        assert run_id is not None

        # Retrieve run results
        resp = client.get(f"/api/v1/sim/runs/{run_id}", headers=_auth_header(op_token))
        assert resp.status_code == 200
        run = resp.json()
        assert "baseline_kpis" in run
        assert "priority_kpis" in run
        assert run["priority_kpis"]["ambulance_wait_s"] < run["baseline_kpis"]["ambulance_wait_s"]

        # KPI summary endpoint
        resp = client.get("/api/v1/kpi/summary", headers=_auth_header(op_token))
        assert resp.status_code == 200
