"""Test: pyproject.toml version matches footstats.config.VERSION."""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_bytes()
    data = tomllib.loads(text.decode("utf-8"))
    return str(data["project"]["version"])


def _config_version() -> str:
    from footstats.config import VERSION
    return str(VERSION)


def _normalize(v: str) -> str:
    """Strip leading 'v', '-stable' / '-rc' / '-beta' suffixes — keep MAJOR.MINOR(.PATCH)."""
    v = v.strip().lstrip("vV")
    m = re.match(r"^(\d+(?:\.\d+){1,2})", v)
    return m.group(1) if m else v


def test_pyproject_and_config_version_match() -> None:
    pp = _normalize(_pyproject_version())
    cfg = _normalize(_config_version())
    assert pp == cfg, (
        f"Version mismatch: pyproject.toml={pp!r}, footstats.config.VERSION={cfg!r}. "
        "Bump both together."
    )


def test_pyproject_version_format() -> None:
    v = _pyproject_version()
    assert re.match(r"^\d+(\.\d+){1,2}([-.]?[A-Za-z0-9.]+)?$", v), (
        f"pyproject.toml version {v!r} not in MAJOR.MINOR[.PATCH][-suffix] form"
    )
