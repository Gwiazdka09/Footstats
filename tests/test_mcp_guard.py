"""Guard montowania MCP (/mcp) — tylko poza produkcją (audyt 2026-07-27)."""
import os

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("FOOTSTATS_USER", "admin")
import bcrypt as _bcrypt_lib

os.environ.setdefault(
    "FOOTSTATS_PASSWORD_HASH",
    _bcrypt_lib.hashpw(b"testpass", _bcrypt_lib.gensalt()).decode(),
)

from footstats.api.main import _mcp_enabled


def test_mcp_disabled_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    assert _mcp_enabled() is False


def test_mcp_disabled_case_insensitive(monkeypatch):
    monkeypatch.setenv("ENV", "Production")
    assert _mcp_enabled() is False


def test_mcp_enabled_in_dev(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    assert _mcp_enabled() is True


def test_mcp_enabled_when_env_unset(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    assert _mcp_enabled() is True
