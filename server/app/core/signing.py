"""HMAC-SHA256 Command Signing and Verification.

Contract (PLAN.md Section 5.4 P2):
Approach-specific payload format: "{seq}|{cmd}|{axis}|{approach}|{ttl_s}".
Legacy axis-only payloads omit approach for compatibility.
"""

import hashlib
import hmac


def build_signature_payload(
    seq: int,
    cmd: str,
    axis: str | None,
    ttl_s: int,
    approach: str | None = None,
) -> str:
    """Format string for HMAC verification."""
    clean_axis = (axis or "").upper()
    clean_cmd = cmd.upper()
    if approach:
        return f"{seq}|{clean_cmd}|{clean_axis}|{approach.upper()}|{ttl_s}"
    return f"{seq}|{clean_cmd}|{clean_axis}|{ttl_s}"


def sign_command(
    secret: str,
    seq: int,
    cmd: str,
    axis: str | None,
    ttl_s: int,
    approach: str | None = None,
) -> str:
    """Generate hex-encoded HMAC-SHA256 signature for a command."""
    payload = build_signature_payload(seq, cmd, axis, ttl_s, approach).encode("utf-8")
    secret_bytes = secret.encode("utf-8")
    return hmac.new(secret_bytes, payload, hashlib.sha256).hexdigest()


def verify_command_signature(
    secret: str,
    sig: str | None,
    seq: int,
    cmd: str,
    axis: str | None,
    ttl_s: int,
    approach: str | None = None,
) -> bool:
    """Verify incoming hex HMAC signature against payload."""
    if not sig:
        return False
    expected = sign_command(secret, seq, cmd, axis, ttl_s, approach)
    return hmac.compare_digest(sig.lower().strip(), expected.lower().strip())
