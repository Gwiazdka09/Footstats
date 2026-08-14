"""BTTS dwustronne — model potrafi typować NIE, ale potok tego nie obsługiwał.

USTALONE 15.08 na n=15 460 (walk-forward, próba dzielona po dacie):
  * `p_btts` REALNIE rozróżnia mecze — krzywa monotoniczna w OBU połowach
    (0-40% → BTTS pada w 48.7%/51.2%; 65%+ → 60.7%/64.1%).
  * Gra dwustronna przy marginesie 15pp bije stałą odpowiedź w obu połowach.
  * ALE przeciw rynkowi przegrywa (Brier 0.2508 vs 0.2460), a próg opłacalności
    dla NIE to kurs 2.10 przy rynkowych ~1.6.

Stąd: naprawiamy KSIĘGOWOŚĆ (pewność, kursy, powód odrzucenia), a samo granie
BTTS NIE zostaje za flagą `BTTS_TWO_WAY` domyślnie WYŁĄCZONĄ — tak jak
`SELECTION_MIN_CONF` i `LEAGUE_GATING` czekają na walidację.

Trzy zepsute ogniwa, każde ciche:
  1. `prob_modelu` nie znało "BTTS NO" → pewność zapisywana jako 50 zamiast 100-bt,
     i to akurat dla typów, których model był NAJPEWNIEJSZY.
  2. `_TYP_DO_ODDS_KEY` nie znało tego typu → noga kasowana...
  3. ...i podpisywana jako halucynacja Groqa, choć Groq nie miał z nią nic wspólnego.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from footstats.ai.analyzer_helpers import pewnosc_z_modelu, prob_modelu


# ── 1. pewność typu BTTS NO ────────────────────────────────────────────────

@pytest.mark.parametrize("typ", ["BTTS NO", "btts no", "NO BTTS", "BTTS NIE", "NG"])
def test_prob_modelu_zna_btts_no(typ):
    """Model dający BTTS 30% jest w 70% pewny strony NIE — nie w 50%."""
    assert prob_modelu(typ, {"btts": 30.0}) == pytest.approx(70.0)


def test_prob_modelu_btts_tak_bez_zmian():
    assert prob_modelu("BTTS", {"btts": 30.0}) == pytest.approx(30.0)


def test_pewnosc_btts_no_nie_spada_do_fallbacku():
    """Sedno bugu: pewność 50 zamiast 70 zaniżała najlepsze typy modelu."""
    assert pewnosc_z_modelu("BTTS NO", {"btts": 30.0}) == 70


def test_prob_modelu_btts_no_bez_danych_daje_none():
    """Brak prob modelu → None, żeby zadziałał fallback, a nie fałszywe 100."""
    assert prob_modelu("BTTS NO", {}) is None
    assert prob_modelu("BTTS NO", {"btts": None}) is None


# ── 2. kurs BTTS NIE ze źródeł ─────────────────────────────────────────────

def test_api_football_zbiera_kurs_btts_no():
    """API-Football zwraca obie strony — brano wyłącznie 'Yes', 'No' szło do kosza."""
    from footstats.scrapers.api_football import APIFootball
    odpowiedz = {"response": [{"bookmakers": [{"bets": [{
        "name": "Both Teams Score",
        "values": [{"value": "Yes", "odd": "1.65"}, {"value": "No", "odd": "2.20"}],
    }]}]}]}
    with patch.object(APIFootball, "__init__", lambda self: None), \
         patch.object(APIFootball, "_get", return_value=odpowiedz):
        wynik = APIFootball().kursy_fixture(1)
    assert wynik["btts"] == pytest.approx(1.65)
    assert wynik["btts_no"] == pytest.approx(2.20)


def test_sofascore_zbiera_kurs_btts_no():
    from footstats.scrapers.sofascore_odds import _MARKET_BTTS, _parse_markets
    rynki = {"markets": [{
        "marketName": next(iter(_MARKET_BTTS)),
        "choices": [{"name": "Yes", "fractionalValue": "13/20"},
                    {"name": "No", "fractionalValue": "6/5"}],
    }]}
    wynik = _parse_markets(rynki)
    assert wynik.get("btts") is not None
    assert wynik.get("btts_no") is not None


# ── 3. weryfikacja nogi: uczciwy powód odrzucenia ──────────────────────────

def _indeks(odds):
    return {("legia", "wisla"): {"odds": odds, "gospodarz": "Legia", "goscie": "Wisła",
                                 "liga": "PL", "pred": {}, "data": "2026-08-20"}}


def test_brak_kursu_na_znanym_rynku_nie_jest_halucynacja():
    """Znamy rynek, ale źródło go nie wycenia — to brak danych, nie zmyślony typ.

    Mieszanie tych dwóch przypadków w jednym komunikacie ukrywało, że po prostu
    czegoś nie mamy, i obwiniało Groqa o cudzą winę.
    """
    from footstats.daily_agent import _weryfikuj_noge
    indeks = _indeks({"home": 1.85})            # brak under_2_5
    usuniete = []
    z = {"mecz": "Legia vs Wisła", "typ": "Under 2.5", "kurs": 1.9}
    with patch("footstats.daily_agent._znajdz_mecz", return_value=list(indeks.values())[0]):
        assert _weryfikuj_noge(z, indeks, usuniete) is None
    assert len(usuniete) == 1
    assert "niezweryfikowany" not in usuniete[0]
    assert "nie podaje kursu" in usuniete[0]
    assert "under_2_5" in usuniete[0]


def test_nieznany_typ_dalej_traktowany_jak_halucynacja():
    """Typ, którego w ogóle nie znamy, to nadal wymysł — nie mylmy tych przypadków."""
    from footstats.daily_agent import _weryfikuj_noge
    indeks = _indeks({"home": 1.85})
    usuniete = []
    z = {"mecz": "Legia vs Wisła", "typ": "Zwycięstwo do przerwy i po", "kurs": 3.0}
    with patch("footstats.daily_agent._znajdz_mecz", return_value=list(indeks.values())[0]):
        assert _weryfikuj_noge(z, indeks, usuniete) is None
    assert "niezweryfikowany" in usuniete[0]


# ── 4. flaga BTTS_TWO_WAY (domyślnie OFF) ──────────────────────────────────

def test_btts_no_odrzucane_gdy_flaga_wylaczona(monkeypatch):
    """Kurs jest, ale dowody mówią: NIE wymaga 2.10, rynek daje ~1.6. Nie gramy."""
    from footstats import daily_agent
    monkeypatch.setattr(daily_agent, "BTTS_TWO_WAY", False, raising=False)
    indeks = _indeks({"home": 1.85, "btts_no": 2.20})
    usuniete = []
    z = {"mecz": "Legia vs Wisła", "typ": "BTTS NO", "kurs": 2.2}
    with patch("footstats.daily_agent._znajdz_mecz", return_value=list(indeks.values())[0]):
        assert daily_agent._weryfikuj_noge(z, indeks, usuniete) is None
    assert "dwustronne" in usuniete[0].lower()


def test_btts_no_przechodzi_gdy_flaga_wlaczona(monkeypatch):
    """Po walidacji wystarczy flip flagi — kurs bierzemy rzeczywisty, nie od Groqa."""
    from footstats import daily_agent
    monkeypatch.setattr(daily_agent, "BTTS_TWO_WAY", True, raising=False)
    indeks = _indeks({"home": 1.85, "btts_no": 2.20})
    usuniete = []
    z = {"mecz": "Legia vs Wisła", "typ": "BTTS NO", "kurs": 9.99}
    with patch("footstats.daily_agent._znajdz_mecz", return_value=list(indeks.values())[0]):
        wynik = daily_agent._weryfikuj_noge(z, indeks, usuniete)
    assert wynik is not None
    assert wynik["kurs"] == pytest.approx(2.20)
    assert usuniete == []


def test_btts_tak_dziala_niezaleznie_od_flagi(monkeypatch):
    """Flaga dotyczy WYŁĄCZNIE strony NIE — zwykłe BTTS nie może na tym ucierpieć."""
    from footstats import daily_agent
    monkeypatch.setattr(daily_agent, "BTTS_TWO_WAY", False, raising=False)
    indeks = _indeks({"home": 1.85, "btts": 1.70})
    usuniete = []
    z = {"mecz": "Legia vs Wisła", "typ": "BTTS", "kurs": 5.0}
    with patch("footstats.daily_agent._znajdz_mecz", return_value=list(indeks.values())[0]):
        wynik = daily_agent._weryfikuj_noge(z, indeks, usuniete)
    assert wynik is not None
    assert wynik["kurs"] == pytest.approx(1.70)
