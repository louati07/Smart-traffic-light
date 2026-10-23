"""Comprehensive API Integration Tests for REST endpoints and auth."""

from fastapi.testclient import TestClient

from server.app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "mongo" in data
    assert "firebase" in data
    assert "uptime_s" in data


def test_auth_login_success_and_failure():
    # Failure with wrong password
    bad_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "wrongpassword"},
    )
    assert bad_resp.status_code == 401

    # Success with valid credentials
    ok_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "operator123"},
    )
    assert ok_resp.status_code == 200
    data = ok_resp.json()
    assert "access_token" in data
    assert data["role"] == "operator"


def test_detections_endpoint_auth_and_submission():
    # 1. No token -> 401
    det_payload = {
        "camera_id": "cam-N",
        "approach": "N",
        "class": "ambulance",
        "confidence": 0.92,
        "bbox_area_ratio": 0.03,
        "frame_id": 101,
        "source_ts_ms": 1760000000000,
        "confirmed": True,
    }
    unauth_resp = client.post("/api/v1/detections", json=det_payload)
    assert unauth_resp.status_code == 401

    # 2. Get Camera token
    login_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "camera", "password": "camera123"},
    )
    cam_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {cam_token}"}

    # 3. Valid submission
    resp = client.post("/api/v1/detections", json=det_payload, headers=headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "received"
    assert res_data["confirmed"] is True


def test_intersections_state_and_command():
    # Login as operator
    login_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "operator123"},
    )
    op_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {op_token}"}

    # Get state
    state_resp = client.get("/api/v1/intersections/i1/state", headers=headers)
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert "phase" in state
    assert "lights" in state

    # Issue manual override
    cmd_payload = {"cmd": "PRIORITY", "axis": "EW", "ttl_s": 12}
    cmd_resp = client.post(
        "/api/v1/intersections/i1/command",
        json=cmd_payload,
        headers=headers,
    )
    assert cmd_resp.status_code == 200
    res = cmd_resp.json()
    assert res["status"] == "command_issued"
    assert res["command"]["axis"] == "EW"


def test_security_events_role_enforcement():
    # Operator token trying to view security-events -> 403 Forbidden (requires admin)
    op_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "operator123"},
    )
    op_headers = {"Authorization": f"Bearer {op_resp.json()['access_token']}"}
    forbidden_resp = client.get("/api/v1/security-events", headers=op_headers)
    assert forbidden_resp.status_code == 403

    # Admin token -> 200 OK
    admin_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "admin", "password": "admin123"},
    )
    admin_headers = {"Authorization": f"Bearer {admin_resp.json()['access_token']}"}
    ok_resp = client.get("/api/v1/security-events", headers=admin_headers)
    assert ok_resp.status_code == 200
    assert isinstance(ok_resp.json(), list)


def test_simulation_run_and_kpi():
    login_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "operator", "password": "operator123"},
    )
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    # Run simulation
    sim_resp = client.post(
        "/api/v1/sim/run",
        json={"seed": 123, "scenario": "test_scenario", "duration_s": 45.0},
        headers=headers,
    )
    assert sim_resp.status_code == 200
    run_data = sim_resp.json()
    assert "run_id" in run_data
    run_id = run_data["run_id"]
    assert "baseline_kpis" in run_data
    assert "priority_kpis" in run_data

    # Fetch simulation run details
    get_run_resp = client.get(f"/api/v1/sim/runs/{run_id}", headers=headers)
    assert get_run_resp.status_code == 200
    assert "baseline_trace" in get_run_resp.json()

    # Fetch KPI summary
    kpi_resp = client.get("/api/v1/kpi/summary", headers=headers)
    assert kpi_resp.status_code == 200
    summary = kpi_resp.json()
    assert summary["total_runs"] >= 1
    assert "avg_time_saved_s" in summary
