"""Authentication, JWT handling, role verification, and rate limiting.

Contract (PLAN.md Section 5.2, Section 5.4 P1):
- Roles: 'camera', 'operator', 'admin'
- HS256 JWT creation and verification
- Dependency helpers: require_role(roles)
- Rate limiting: Token bucket for /detections
- Security event recording on failed authentication
"""

import datetime
import logging
import threading
import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from server.app.clients.mongo import get_mongo_client
from server.app.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_bearer = HTTPBearer(auto_error=False)

# Seeded demo credentials for offline development and testing
DEMO_USERS = {
    "camera": {
        "password_hash": pwd_context.hash("camera123"),
        "role": "camera",
    },
    "operator": {
        "password_hash": pwd_context.hash("operator123"),
        "role": "operator",
    },
    "admin": {
        "password_hash": pwd_context.hash("admin123"),
        "role": "admin",
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any], expires_delta: datetime.timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.now(datetime.UTC) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
            minutes=settings.access_token_expire_minutes
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )


class RateLimiter:
    """In-memory token bucket rate limiter per client IP."""

    def __init__(self, rate_per_sec: float = 10.0, burst: int = 20) -> None:
        self.rate = rate_per_sec
        self.burst = burst
        self.buckets: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            bucket = self.buckets.get(key)
            if bucket is None:
                self.buckets[key] = {"tokens": float(self.burst - 1), "last": now}
                return True

            elapsed = now - bucket["last"]
            bucket["last"] = now
            bucket["tokens"] = min(float(self.burst), bucket["tokens"] + elapsed * self.rate)

            if bucket["tokens"] >= 1.0:
                bucket["tokens"] -= 1.0
                return True
            return False


detection_rate_limiter = RateLimiter(
    rate_per_sec=settings.rate_limit_detections_per_sec,
    burst=settings.rate_limit_burst,
)


def get_current_user_and_role(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
) -> dict[str, Any]:
    """Extract and validate JWT from Authorization header."""
    mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)
    client_ip = request.client.host if request.client else "unknown"

    if not credentials or not credentials.credentials:
        mongo.insert_security_event({
            "source_ip": client_ip,
            "reason": "missing_token",
            "endpoint": request.url.path,
            "details": "Authorization header missing",
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Missing authentication token"}},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        username: str = payload.get("sub", "")
        role: str = payload.get("role", "")
        if not username or not role:
            raise ValueError("Token missing sub or role")
        return {"username": username, "role": role}
    except Exception as e:
        mongo.insert_security_event({
            "source_ip": client_ip,
            "reason": "invalid_or_expired_token",
            "endpoint": request.url.path,
            "details": str(e),
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired token"}},
        )


def require_role(allowed_roles: list[str]):
    """Role-based authorization dependency."""

    def role_checker(
        request: Request,
        user: dict[str, Any] = Depends(get_current_user_and_role),
    ) -> dict[str, Any]:
        user_role = user.get("role")
        if user_role not in allowed_roles:
            mongo = get_mongo_client(mode=settings.mongo_mode, uri=settings.mongo_uri, db_name=settings.mongo_db)
            client_ip = request.client.host if request.client else "unknown"
            mongo.insert_security_event({
                "source_ip": client_ip,
                "reason": "forbidden_role",
                "endpoint": request.url.path,
                "details": f"Role '{user_role}' not permitted; requires one of {allowed_roles}",
            })
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "Insufficient permissions for this resource"}},
            )
        return user

    return role_checker
