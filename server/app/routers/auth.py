"""Authentication endpoint.

POST /api/v1/auth/token (Public)
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from server.app.auth import DEMO_USERS, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


@router.post("/token", response_model=TokenResponse)
def login_for_access_token(req: TokenRequest) -> dict[str, Any]:
    user = DEMO_USERS.get(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Incorrect username or password"}},
        )

    role = user["role"]
    access_token = create_access_token({"sub": req.username, "role": role})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": role,
    }
