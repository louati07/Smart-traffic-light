"""HMAC-SHA256 Command Signing and Verification.

Contract (PLAN.md Section 5.4 P2):
Signed payload format: "{seq}|{cmd}|{axis}|{ttl_s}"
Shared secret loaded from environment or firmware constant.
"""

import hashlib
import hmac


def build_signature_payload(seq: int, cmd: str, axis: str | None, ttl_s: int) -> str:
    """Format string for HMAC verification."""
    clean_axis = (axis or "").upper()
    clean_cmd = cmd.upper()
    return f"{seq}|{clean_cmd}|{clean_axis}|{ttl_s}"


def sign_command(secret: str, seq: int, cmd: str, axis: str | None, ttl_s: int) -> str:
    """Generate hex-encoded HMAC-SHA256 signature for a command."""
    payload = build_signature_payload(seq, cmd, axis, ttl_s).encode("utf-8")
    secret_bytes = secret.encode("utf-8")
    return hmac.new(secret_bytes, payload, hashlib.sha256).hexdigest()


def verify_command_signature(
    secret: str,
    sig: str | None,
    seq: int,
    cmd: str,
    axis: str | None,
    ttl_s: int,
) -> bool:
    """Verify incoming hex HMAC signature against payload."""
    if not sig:
        return False
    expected = sign_command(secret, seq, cmd, axis, ttl_s)
    return hmac.compare_digest(sig.lower().strip(), expected.lower().strip())
