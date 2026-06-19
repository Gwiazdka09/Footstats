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


def test_blend_ensemble_applied_when_df_mecze_provided():
    """Poisson blend ensemble (70/30) zmienia pw/pr/pp/bt/o25 gdy predict_match zwraca dane."""
    bzz = _make_bzzoiro([_BZZ_EVENT])
    df_dummy = pd.DataFrame([{"gospodarz": "A", "goscie": "B", "gole_g": 1, "gole_a": 0, "data": "2026-01-01"}])  # waliduj_df_wyniki: poprawny

    mock_fort = MagicMock()
    mock_fort.analiza.return_value = None
    mock_h2h = MagicMock()
    mock_h2h.analiza.return_value = None
    mock_heur = MagicMock()
    mock_heur.analiza.return_value = None
    mock_klas = MagicMock()
    mock_klas.klasyfikuj.return_value = None

    with patch(
        "footstats.core.quick_picks.calibrate_confidence", side_effect=lambda x: x / 100
    ), patch(
        "footstats.core.poisson.predict_match", return_value=_POISSON_PRED
    ) as mock_pm, patch(
        "footstats.core.fortress.HomeFortress", return_value=mock_fort
    ), patch(
        "footstats.core.h2h.AnalizaH2H", return_value=mock_h2h
    ), patch(
        "footstats.core.fatigue.HeurystaZmeczeniaRotacji", return_value=mock_heur
    ), patch(
        "footstats.core.classifier.KlasyfikatorMeczu", return_value=mock_klas
    ):
        wyniki = szybkie_pewniaczki_2dni(bzz, prog=0.0, df_mecze=df_dummy)

    mock_pm.assert_called_once()
    assert mock_pm.call_args[0][:2] == ("Arsenal", "Chelsea")
    assert len(wyniki) >= 1
    r = wyniki[0]
    assert r["poisson_blend"] is True
    # Ensemble 70/30 (Poisson/Bzzoiro): pw = 0.7*50 + 0.3*60 = 53
    assert r["pw"] == pytest.approx(53.0, abs=1.0)
    # pr = 0.7*30 + 0.3*20 = 27.0
    assert r["pr"] == pytest.approx(27.0, abs=1.0)


def test_blend_skipped_when_predict_match_returns_none():
    """Gdy predict_match zwraca None (za mało danych), poisson_blend=False."""
    bzz = _make_bzzoiro([_BZZ_EVENT])
    df_dummy = pd.DataFrame([{"gospodarz": "A", "goscie": "B", "gole_g": 1, "gole_a": 0, "data": "2026-01-01"}])

    with patch(
        "footstats.core.quick_picks.calibrate_confidence", side_effect=lambda x: x / 100
    ), patch("footstats.core.poisson.predict_match", return_value=None):
        wyniki = szybkie_pewniaczki_2dni(bzz, prog=0.0, df_mecze=df_dummy)

    assert len(wyniki) >= 1
    assert wyniki[0]["poisson_blend"] is False


def test_blend_skipped_on_predict_match_exception():
    """Wyjątek w predict_match → fallback do Bzzoiro, poisson_blend=False."""
    bzz = _make_bzzoiro([_BZZ_EVENT])
    df_dummy = pd.DataFrame([{"gospodarz": "A", "goscie": "B", "gole_g": 1, "gole_a": 0, "data": "2026-01-01"}])

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


def test_wynik_zawiera_pred_dict_z_prob_modelu():
    """
    Bug Cel B #1: wyniki musi zawierać klucz "pred" ze skalibrowanymi prob,
    inaczej warstwa AI (pewnosc_z_modelu) czyta pred={} i wraca do fallback
    Groq (overconfident) zamiast prawdopodobienstwa modelu -> inwersja kalibracji.
    """
    bzz = _make_bzzoiro([_BZZ_EVENT])
    with patch(
        "footstats.core.quick_picks.calibrate_confidence", side_effect=lambda x: x / 100
    ), patch(
        "footstats.data.historical_loader.load_cached",
        side_effect=FileNotFoundError("brak cache"),
    ):
        wyniki = szybkie_pewniaczki_2dni(bzz, prog=0.0)

    assert len(wyniki) >= 1
    r = wyniki[0]
    assert "pred" in r
    pred = r["pred"]
    assert pred["p_wygrana"] == r["pw"]
    assert pred["p_remis"] == r["pr"]
    assert pred["p_przegrana"] == r["pp"]
    assert pred["btts"] == r["bt"]
    assert pred["over25"] == r["o25"]

    # Warstwa AI: pewnosc_z_modelu musi czytac prob modelu (pr), NIE fallback.
    from footstats.ai.analyzer_helpers import pewnosc_z_modelu

    conf = pewnosc_z_modelu("x", r.get("pred") or {}, fallback_pct=90)
    assert conf == int(round(max(1, min(99, r["pr"]))))
    assert conf != 90
