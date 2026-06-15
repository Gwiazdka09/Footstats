"""JWT authentication for FootStats API — DB-backed multi-user."""
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, field_validator

_ALGORITHM = "HS256"
_EXPIRE_HOURS = 24
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_bearer = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Login musi mieć min. 3 znaki")
        return v

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Nieprawidłowy adres e-mail")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Hasło musi mieć min. 8 znaków")
        return v


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


def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch active user from DB by e-mail. Returns dict with id, username, password_hash, is_admin or None."""
    from footstats.utils.db import connect

    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_admin FROM users"
            " WHERE email = ? AND is_active = TRUE",
            (email,),
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
    if not user and "@" in req.username:
        user = get_user_by_email(req.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not bcrypt.checkpw(req.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=_make_token(user["username"], user["id"], bool(user.get("is_admin", False)))
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest) -> TokenResponse:
    import psycopg2
    from footstats.utils.db import connect

    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    try:
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO users (username, email, password_hash, is_admin, is_active)"
                " VALUES (?, ?, ?, FALSE, TRUE)"
                " RETURNING id, username",
                (req.username, req.email, hashed),
            ).fetchone()
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Login lub e-mail jest już zajęty")

    try:
        from footstats.config import AGENT_BANKROLL
        with connect() as conn:
            conn.execute(
                "INSERT INTO bankroll_state (user_id, balance, updated_at)"
                " VALUES (?, ?, ?) ON CONFLICT (user_id) DO NOTHING",
                (row["id"], AGENT_BANKROLL, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
    except psycopg2.Error:
        pass

    return TokenResponse(access_token=_make_token(row["username"], row["id"], False))


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
