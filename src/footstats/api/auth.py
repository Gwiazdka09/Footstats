"""JWT authentication for FootStats API — DB-backed multi-user."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

_ALGORITHM = "HS256"
_EXPIRE_HOURS = 24
_bearer = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _secret() -> str:
    s = os.environ.get("JWT_SECRET", "")
    if not s:
        raise RuntimeError("JWT_SECRET env var not set")
    return s


def _make_token(username: str, user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "uid": user_id, "exp": exp},
        _secret(),
        algorithm=_ALGORITHM,
    )


def get_user_by_username(username: str) -> Optional[dict]:
    """Fetch active user from DB. Returns dict with id, username, password_hash or None."""
    from footstats.utils.db import connect

    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users"
            " WHERE username = ? AND is_active = TRUE",
            (username,),
        ).fetchone()
    return dict(row) if row else None


@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    user = get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not bcrypt.checkpw(req.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=_make_token(req.username, user["id"]))


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> int:
    """Validate JWT and return user_id (int)."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = jwt.decode(credentials.credentials, _secret(), algorithms=[_ALGORITHM])
        user_id: int | None = payload.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token — re-login required")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
