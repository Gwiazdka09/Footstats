"""Tests for szybkie_pewniaczki_2dni Poisson ensemble blend (11.4)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from footstats.core.quick_picks import szybkie_pewniaczki_2dni

# ── helpers ──────────────────────────────────────────────────────────────────

_NOW = datetime.now()
_SOON = _NOW + timedelta(hours=6)
_DATE = _SOON.strftime("%Y-%m-%d")
_HOUR = _SOON.strftime("%H:%M")

_BZZ_EVENT = {
    "gosp": "Arsenal",
    "gosc": "Chelsea",
    "liga": "Premier League",
    "data": _DATE,
    "godzina": _HOUR,
    "pred_ml": {
        "percent": {"home": "60%", "draw": "20%", "away": "20%"},
        "btts": "50%",
        "over_2_5": "55%",
    },
    "odds": {"home": 1.8, "draw": 3.5, "away": 4.0},
}

_POISSON_PRED = {
    "p_wygrana": 50.0,
    "p_remis": 30.0,
    "p_przegrana": 20.0,
    "btts": 40.0,
    "over25": 45.0,
    "under25": 55.0,
}


def _make_bzzoiro(events: list) -> MagicMock:
    client = MagicMock()
    client._valid = True
    client.predykcje_tygodnia.return_value = events
    return client


# ── tests ─────────────────────────────────────────────────────────────────────


def test_no_blend_when_no_df_mecze_and_no_cache():
    """Gdy load_cached() rzuca FileNotFoundError, wynik pochodzi tylko z Bzzoiro."""
    bzz = _make_bzzoiro([_BZZ_EVENT])
    with patch(
        "footstats.core.quick_picks.calibrate_confidence", side_effect=lambda x: x / 100
    ), patch(
        "footstats.data.historical_loader.load_cached",
        side_effect=FileNotFoundError("brak cache"),
    ):
        wyniki = szybkie_pewniaczki_2dni(bzz, prog=0.0)

    assert len(wyniki) >= 1
    assert wyniki[0]["poisson_blend"] is False


def test_blend_50_50_applied_when_df_mecze_provided():
    """Poisson blend 50/50 zmienia pw/pr/pp/bt/o25 gdy predict_match zwraca dane."""
    bzz = _make_bzzoiro([_BZZ_EVENT])
    df_dummy = pd.DataFrame({"col": [1]})  # niepuste, ale predict_match mockowany

    mock_fort = MagicMock()
    mock_fort.analiza.return_value = None
    mock_h2h = MagicMock()
    mock_h2h.analiza.return_value = None

    with patch(
        "footstats.core.quick_picks.calibrate_confidence", side_effect=lambda x: x / 100
    ), patch(
        "footstats.core.poisson.predict_match", return_value=_POISSON_PRED
    ) as mock_pm, patch(
        "footstats.core.fortress.HomeFortress", return_value=mock_fort
    ), patch(
        "footstats.core.h2h.AnalizaH2H", return_value=mock_h2h
    ):
        wyniki = szybkie_pewniaczki_2dni(bzz, prog=0.0, df_mecze=df_dummy)

    mock_pm.assert_called_once()
    assert mock_pm.call_args[0][:2] == ("Arsenal", "Chelsea")
    assert len(wyniki) >= 1
    r = wyniki[0]
    assert r["poisson_blend"] is True
    # Bzzoiro calibrated (div/100): pw=0.60 → 60%, Poisson: 50% → blend = 55%
    assert r["pw"] == pytest.approx(55.0, abs=1.0)
    assert r["pr"] == pytest.approx(25.0, abs=1.0)


def test_blend_skipped_when_predict_match_returns_none():
    """Gdy predict_match zwraca None (za mało danych), poisson_blend=False."""
    bzz = _make_bzzoiro([_BZZ_EVENT])
    df_dummy = pd.DataFrame({"col": [1]})

    with patch(
        "footstats.core.quick_picks.calibrate_confidence", side_effect=lambda x: x / 100
    ), patch("footstats.core.poisson.predict_match", return_value=None):
        wyniki = szybkie_pewniaczki_2dni(bzz, prog=0.0, df_mecze=df_dummy)

    assert len(wyniki) >= 1
    assert wyniki[0]["poisson_blend"] is False


def test_blend_skipped_on_predict_match_exception():
    """Wyjątek w predict_match → fallback do Bzzoiro, poisson_blend=False."""
    bzz = _make_bzzoiro([_BZZ_EVENT])
    df_dummy = pd.DataFrame({"col": [1]})

    with patch(
        "footstats.core.quick_picks.calibrate_confidence", side_effect=lambda x: x / 100
    ), patch("footstats.core.poisson.predict_match", side_effect=ValueError("test")):
        wyniki = szybkie_pewniaczki_2dni(bzz, prog=0.0, df_mecze=df_dummy)

    assert len(wyniki) >= 1
    assert wyniki[0]["poisson_blend"] is False


def test_invalid_bzzoiro_returns_empty():
    """Gdy bzzoiro._valid=False, zwraca pustą listę."""
    bzz = MagicMock()
    bzz._valid = False
    assert szybkie_pewniaczki_2dni(bzz) == []
