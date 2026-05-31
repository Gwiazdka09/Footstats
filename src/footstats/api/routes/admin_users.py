"""Admin-only user management endpoints."""
from __future__ import annotations

import logging
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from footstats.api.auth import require_admin

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username min. 3 znaki")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Hasło min. 8 znaków")
        return v


class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool


@router.get("/users", response_model=list[UserResponse])
def list_users(admin_id: Annotated[int, Depends(require_admin)]) -> list[UserResponse]:
    from footstats.utils.db import connect

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, username, is_admin, is_active FROM users ORDER BY id"
        ).fetchall()
    return [UserResponse(**dict(r)) for r in rows]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    req: CreateUserRequest,
    admin_id: Annotated[int, Depends(require_admin)],
) -> UserResponse:
    from footstats.utils.db import connect

    import psycopg2

    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    try:
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO users (username, password_hash, is_admin, is_active)"
                " VALUES (?, ?, ?, TRUE)"
                " RETURNING id, username, is_admin, is_active",
                (req.username, hashed, req.is_admin),
            ).fetchone()
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"User '{req.username}' już istnieje")
    except psycopg2.Error as e:
        _log.error("DB error przy tworzeniu usera '%s': %s", req.username, e)
        raise HTTPException(status_code=500, detail="Błąd tworzenia użytkownika")
    new_user = UserResponse(**dict(row))
    try:
        from datetime import datetime
        with connect() as conn:
            conn.execute(
                "INSERT INTO bankroll_state (user_id, balance, updated_at)"
                " VALUES (?, 0.0, ?)"
                " ON CONFLICT (user_id) DO NOTHING",
                (new_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
    except Exception as e:
        _log.warning("Nie udało się zainicjować bankrolla dla usera %d: %s", new_user.id, e)
    _log.info("Admin %d utworzył usera '%s' (is_admin=%s)", admin_id, req.username, req.is_admin)
    return new_user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    admin_id: Annotated[int, Depends(require_admin)],
) -> None:
    if user_id == admin_id:
        raise HTTPException(status_code=400, detail="Nie możesz dezaktywować własnego konta")
    from footstats.utils.db import connect

    with connect() as conn:
        cur = conn.execute(
            "UPDATE users SET is_active = FALSE WHERE id = ? AND is_active = TRUE",
            (user_id,),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony lub już nieaktywny")
    _log.info("Admin %d dezaktywował usera id=%d", admin_id, user_id)
