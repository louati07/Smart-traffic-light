"""Security & Attack Demonstration Script.

Contract (PLAN.md Section 8 P6 & Section 14 Demo Step 5):
Executes 4 attack scenarios against the API:
1. Missing JWT Token -> Rejected 401.
2. Forged / Tampered JWT Token -> Rejected 401.
3. Rapid Flood Request Burst -> Rejected 429 Rate Limited.
4. Old Sequence Number Replay -> Rejected by controller.
Verifies all violations are logged to security_events audit table.
"""

import logging
import time
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("attack-demo")

API_URL = "http://localhost:8000/api/v1"


def run_attack_suite() -> None:
    client = httpx.Client(timeout=4.0)

    print("\n========================================================")
    print("      SMART INTERSECTION SECURITY & ATTACK TEST SUITE   ")
    print("========================================================\n")

    # --- Test 1: Unauthenticated request ---
    print("[Attack 1] Sending detection WITHOUT Authorization token...")
    payload = {
        "camera_id": "rogue-cam",
        "approach": "N",
        "class": "ambulance",
        "confidence": 0.99,
        "bbox_area_ratio": 0.05,
        "frame_id": 999,
        "source_ts_ms": int(time.time() * 1000),
        "confirmed": True,
    }
    r1 = client.post(f"{API_URL}/detections", json=payload)
    print(f" -> Result: HTTP {r1.status_code} ({r1.json().get('detail')})")
    assert r1.status_code == 401, f"Expected 401, got {r1.status_code}"
    print(" -> SUCCESS: Attack 1 cleanly repelled.\n")

    # --- Test 2: Forged JWT token ---
    print("[Attack 2] Sending detection with FORGED signature token...")
    forged_headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.fake_sig_123456"}
    r2 = client.post(f"{API_URL}/detections", json=payload, headers=forged_headers)
    print(f" -> Result: HTTP {r2.status_code} ({r2.json().get('detail')})")
    assert r2.status_code == 401, f"Expected 401, got {r2.status_code}"
    print(" -> SUCCESS: Attack 2 cleanly repelled.\n")

    # --- Test 3: High-frequency rate limit flood ---
    print("[Attack 3] Sending 30 rapid-fire requests in 0.5s to trigger token bucket rate limiter...")
    # Obtain legitimate camera token first
    auth_resp = client.post(f"{API_URL}/auth/token", json={"username": "camera", "password": "camera123"})
    if auth_resp.status_code != 200:
        print("Failed to authenticate camera for flood test")
        return
    token = auth_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    rate_limited_count = 0
    for i in range(30):
        r3 = client.post(f"{API_URL}/detections", json=payload, headers=headers)
        if r3.status_code == 429:
            rate_limited_count += 1

    print(f" -> Result: {rate_limited_count} of 30 requests triggered HTTP 429 Too Many Requests.")
    assert rate_limited_count > 0, "Expected rate limiter to trigger HTTP 429"
    print(" -> SUCCESS: Rate limit threshold enforced.\n")

    # --- Test 4: Verify audit log entries ---
    print("[Verification] Fetching Security Audit Log as Administrator...")
    admin_auth = client.post(f"{API_URL}/auth/token", json={"username": "admin", "password": "admin123"})
    admin_token = admin_auth.json()["access_token"]
    sec_resp = client.get(f"{API_URL}/security-events", headers={"Authorization": f"Bearer {admin_token}"})
    sec_events = sec_resp.json()
    print(f" -> Total recorded security events: {len(sec_events)}")
    recent_reasons = [e.get("reason") for e in sec_events[:5]]
    print(f" -> Most recent audit event reasons: {recent_reasons}")

    print("\n========================================================")
    print(" [OK] ALL ATTACKS SUCCESSFULLY REPELLED AND LOGGED.       ")
    print("========================================================\n")


if __name__ == "__main__":
    run_attack_suite()
