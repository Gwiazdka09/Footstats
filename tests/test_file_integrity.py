"""Sprawdza poprawność składni i minimalną długość kluczowych plików."""
import py_compile
import pytest
from pathlib import Path

_ROOT = Path(__file__).parent.parent / "src" / "footstats"

_FILES = [
    ("daily_agent.py",                      300),
    ("ai/client.py",                          60),
    ("core/coupon_settlement.py",             80),
    ("core/probability_calibrator.py",        40),
    ("core/ensemble_optimizer.py",            60),
    ("scrapers/bzzoiro.py",                   80),
    ("scrapers/results_updater.py",          200),
    ("scrapers/enriched.py",                 100),
    ("utils/telegram_notify.py",              30),
    ("db/migrations.py",                      50),
]


@pytest.mark.parametrize("rel_path,min_lines", _FILES, ids=[f[0] for f in _FILES])
def test_syntax_and_length(rel_path: str, min_lines: int) -> None:
    path = _ROOT / rel_path
    assert path.exists(), f"Brak pliku: {path}"
    py_compile.compile(str(path), doraise=True)
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines >= min_lines, f"{rel_path}: {lines} linii < wymagane {min_lines}"
