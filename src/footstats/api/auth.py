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


def get_user_by_username(username: str) -> Optional[dict]:
    """Fetch active user from DB. Returns dict with id, username, password_hash, is_admin or None."""
    from footstats.utils.db import connect

    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_admin FROM users"
            " WHERE username = ? AND is_active = TRUE",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def _make_token(username: str, user_id: int, is_admin: bool = False) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "uid": user_id, "adm": is_admin, "exp": exp},
        _secret(),
        algorithm=_ALGORITHM,
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    user = get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not bcrypt.checkpw(req.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=_make_token(req.username, user["id"], bool(user.get("is_admin", False)))
    )


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


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> int:
    """Validate JWT and assert is_admin=True. Returns user_id (int)."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = jwt.decode(credentials.credentials, _secret(), algorithms=[_ALGORITHM])
        user_id: int | None = payload.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token — re-login required")
        if not payload.get("adm", False):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/change-password", status_code=status.HTTP_200_OK)
def change_password(req: ChangePasswordRequest, user_id: int = Depends(require_auth)):
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Nowe hasło min. 8 znaków")
    from footstats.utils.db import connect
    with connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ? AND is_active = TRUE", (user_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    if not bcrypt.checkpw(req.current_password.encode(), row["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Nieprawidłowe aktualne hasło")
    new_hash = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt()).decode()
    with connect() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    return {"ok": True, "message": "Hasło zmienione"}
