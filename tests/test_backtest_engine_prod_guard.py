"""
Test izolacji backtest_engine od produkcyjnej bazy Neon.

backtest_engine.py (legacy AI-driven backtest) NIE może pisać do prod —
guard musi odmówić zapisu, jeśli brak jawnego opt-in (FOOTSTATS_TEST_DB).
"""

import os

import pytest

from footstats.core.backtest_engine import _ensure_safe_backtest_db


def test_guard_blokuje_prod_postgres_bez_opt_in(monkeypatch):
    """DATABASE_URL wskazujące na Neon/Postgres bez FOOTSTATS_TEST_DB -> wyjątek."""
    monkeypatch.delenv("FOOTSTATS_TEST_DB", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@ep-prod.neon.tech/db")

    with pytest.raises(RuntimeError, match="backtest_engine nie może pisać do prod"):
        _ensure_safe_backtest_db()


def test_guard_przepuszcza_z_opt_in_test_db(monkeypatch):
    """Z ustawionym FOOTSTATS_TEST_DB guard nie rzuca, nawet gdy DATABASE_URL=postgres."""
    monkeypatch.setenv("FOOTSTATS_TEST_DB", "data/backtest_engine_test.db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@ep-prod.neon.tech/db")

    _ensure_safe_backtest_db()  # nie powinno rzucić


def test_guard_przepuszcza_brak_database_url(monkeypatch):
    """Brak DATABASE_URL (np. czyste środowisko testowe) -> guard nie blokuje."""
    monkeypatch.delenv("FOOTSTATS_TEST_DB", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    _ensure_safe_backtest_db()  # nie powinno rzucić
