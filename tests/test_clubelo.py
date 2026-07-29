"""test_clubelo.py — ClubElo jako niezależny sygnał siły drużyn (darmowe, bez klucza).

Dwa endpointy, oba CSV:
  - `/<data>` i `/<Klub>` — rankingi Elo. Wiersze mają `From`/`To`, więc historia
    jest datowana → używalna w walk-forward bez lookaheadu.
  - `/Fixtures` — nadchodzące mecze Z ROZKŁADEM DOKŁADNYCH WYNIKÓW (`R:0-0`…`R:6-0`).
    Z tego wyliczamy 1X2 / BTTS / Over 2.5 — niezależny model do porównania z naszym.

Świadomie NIE wpinamy tego w λ. Zmiana modelu jest model-critical i wymaga
walk-forward + zgody usera; na razie to sygnał obok, nie w środku.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import footstats.scrapers.clubelo as ce

_RANKING_CSV = (
    "Rank,Club,Country,Level,Elo,From,To\n"
    "1,Arsenal,ENG,1,2063.75805664,2026-05-31,2026-08-21\n"
    "2,Man City,ENG,1,1970.85388184,2026-07-05,2026-08-23\n"
    "3,Paris SG,FRA,1,1967.87878418,2026-07-05,2026-08-23\n"
)

# Skrócony /Fixtures: dom wygrywa wyraźnie, komplet R: sumuje się do 1.0.
_FIXTURES_CSV = (
    "Date,Country,Home,Away,R:0-0,R:1-0,R:1-1,R:2-1,R:0-1,R:2-2\n"
    "2026-08-21,ENG,Arsenal,Chelsea,0.10,0.30,0.20,0.25,0.05,0.10\n"
)


def _resp(text: str, status: int = 200):
    r = MagicMock(status_code=status)
    r.text = text
    return r


# ── ranking ─────────────────────────────────────────────────────────────────


def test_parsuje_ranking_dnia():
    with patch.object(ce, "_pobierz_csv", return_value=_RANKING_CSV):
        ranking = ce.pobierz_ranking("2026-07-29")

    assert ranking["Arsenal"]["elo"] == pytest.approx(2063.76, abs=0.01)
    assert ranking["Arsenal"]["kraj"] == "ENG"
    assert ranking["Arsenal"]["rank"] == 1
    assert len(ranking) == 3


def test_ranking_pusty_gdy_brak_danych():
    with patch.object(ce, "_pobierz_csv", return_value=None):
        assert ce.pobierz_ranking("2026-07-29") == {}


def test_ranking_pomija_smieciowe_wiersze():
    csv = _RANKING_CSV + "x,,,,nieliczba,,\n"
    with patch.object(ce, "_pobierz_csv", return_value=csv):
        assert len(ce.pobierz_ranking("2026-07-29")) == 3


def test_elo_druzyny_szuka_po_nazwie():
    """Nasze nazwy ('Manchester City') różnią się od ClubElo ('Man City')."""
    with patch.object(ce, "_pobierz_csv", return_value=_RANKING_CSV):
        assert ce.elo_druzyny("Man City", "2026-07-29") == pytest.approx(1970.85, abs=0.01)
        assert ce.elo_druzyny("Nieistniejacy FC", "2026-07-29") is None


# ── rozkład wyników z /Fixtures ─────────────────────────────────────────────


def test_wylicza_1x2_z_rozkladu_wynikow():
    """P(1) = suma wyników gdzie dom > goście, itd."""
    p = ce.prob_z_rozkladu({"R:0-0": 0.10, "R:1-0": 0.30, "R:1-1": 0.20,
                            "R:2-1": 0.25, "R:0-1": 0.05, "R:2-2": 0.10})
    assert p["pw"] == pytest.approx(55.0, abs=0.1)   # 1-0 + 2-1
    assert p["pr"] == pytest.approx(40.0, abs=0.1)   # 0-0 + 1-1 + 2-2
    assert p["pp"] == pytest.approx(5.0, abs=0.1)    # 0-1


def test_wylicza_btts_i_over25():
    p = ce.prob_z_rozkladu({"R:0-0": 0.10, "R:1-0": 0.30, "R:1-1": 0.20,
                            "R:2-1": 0.25, "R:0-1": 0.05, "R:2-2": 0.10})
    # BTTS: 1-1, 2-1, 2-2 = 0.55
    assert p["bt"] == pytest.approx(55.0, abs=0.1)
    # Over 2.5 (suma goli >= 3): 2-1 (3), 2-2 (4) = 0.35
    assert p["o25"] == pytest.approx(35.0, abs=0.1)


def test_normalizuje_niepelny_rozklad():
    """Kolumny R: urywają się na 6 goli — ogon ucieka, więc normalizujemy do 100%."""
    p = ce.prob_z_rozkladu({"R:1-0": 0.30, "R:0-1": 0.30})  # suma 0.6
    assert p["pw"] + p["pr"] + p["pp"] == pytest.approx(100.0, abs=0.1)
    assert p["pw"] == pytest.approx(50.0, abs=0.1)


def test_pusty_rozklad_zwraca_none():
    assert ce.prob_z_rozkladu({}) is None
    assert ce.prob_z_rozkladu({"R:0-0": 0.0}) is None


def test_ignoruje_kolumny_spoza_rozkladu():
    """GD<-5 i podobne nie są wynikami — nie wolno ich wliczać."""
    p = ce.prob_z_rozkladu({"R:1-0": 0.5, "R:0-1": 0.5, "GD=0": 0.9, "Date": "x"})
    assert p["pw"] == pytest.approx(50.0, abs=0.1)


# ── fixtures end-to-end ─────────────────────────────────────────────────────


def test_fixtures_zwraca_mecze_z_prognoza():
    with patch.object(ce, "_pobierz_csv", return_value=_FIXTURES_CSV):
        mecze = ce.pobierz_fixtures()

    assert len(mecze) == 1
    m = mecze[0]
    assert m["gospodarz"] == "Arsenal" and m["goscie"] == "Chelsea"
    assert m["data"] == "2026-08-21"
    assert m["liga"] == "ENG"
    assert m["prob"]["pw"] == pytest.approx(55.0, abs=0.1)


def test_fixtures_pomija_mecz_bez_rozkladu():
    csv = "Date,Country,Home,Away,R:0-0\n2026-08-21,ENG,A,B,0\n"
    with patch.object(ce, "_pobierz_csv", return_value=csv):
        assert ce.pobierz_fixtures() == []


def test_blad_sieci_jest_graceful():
    with patch("footstats.scrapers.clubelo.requests.get", side_effect=OSError("timeout")):
        assert ce._pobierz_csv("http://x") is None
        assert ce.pobierz_ranking("2026-07-29") == {}
        assert ce.pobierz_fixtures() == []


def test_http_blad_jest_graceful():
    with patch("footstats.scrapers.clubelo.requests.get", return_value=_resp("", 503)):
        assert ce._pobierz_csv("http://x") is None
