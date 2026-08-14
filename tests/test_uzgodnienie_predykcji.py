"""KROK 4b — wynik weryfikacji kursów musi wrócić do `predictions`.

`_weryfikuj_kupony` podmienia kurs na rzeczywisty i wyrzuca nogi bez pokrycia,
ale działa na słowniku w pamięci. Zapis do bazy jest wcześniej (KROK 3), więc bez
tego domknięcia `predictions` opisuje propozycje Groqa, nie zagrane typy.
"""
from __future__ import annotations

import logging
from unittest.mock import patch

from footstats.daily_agent import (
    _uzgodnij_predykcje,
    _weryfikuj_noge,
    _zbierz_ocalale_nogi,
)


def _dane(top3=None, kupon_a=None):
    return {"top3": top3 or [], "kupon_a": {"zdarzenia": kupon_a or []}}


# ── zbieranie nóg ──────────────────────────────────────────────────────────

def test_zbiera_nogi_z_top3_i_kuponow():
    dane = _dane(
        top3=[{"mecz": "Legia vs Wisła", "typ": "1", "kurs": 1.85, "_data": "2026-08-20"}],
        kupon_a=[{"mecz": "Lech vs Pogoń", "typ": "2", "kurs": 2.05, "_data": "2026-08-20"}],
    )
    nogi = _zbierz_ocalale_nogi(dane)
    assert {n["team_home"] for n in nogi} == {"Legia", "Lech"}


def test_ta_sama_noga_w_top3_i_kuponie_liczy_sie_raz():
    """Bez dedupu licznik uzgodnionych zawyża się i przestaje wykrywać rozjazd."""
    noga = {"mecz": "Legia vs Wisła", "typ": "1", "kurs": 1.85, "_data": "2026-08-20"}
    nogi = _zbierz_ocalale_nogi(_dane(top3=[dict(noga)], kupon_a=[dict(noga)]))
    assert len(nogi) == 1


def test_typ_normalizowany_tak_jak_przy_zapisie():
    """`Over` w zapisie jest `Over 2.5` — inaczej UPDATE nie trafi w wiersz."""
    nogi = _zbierz_ocalale_nogi(_dane(
        top3=[{"mecz": "A vs B", "typ": "Over", "kurs": 1.9, "_data": "2026-08-20"}]))
    assert nogi[0]["ai_tip"] == "Over 2.5"


def test_noga_bez_poprawnej_nazwy_meczu_jest_pomijana():
    nogi = _zbierz_ocalale_nogi(_dane(
        top3=[{"mecz": "cos bez separatora", "typ": "1", "kurs": 1.9}]))
    assert nogi == []


def test_kupon_none_nie_wywala_zbierania():
    """Groq potrafi zwrócić kupon=None — to już raz wywaliło produkcję."""
    assert _zbierz_ocalale_nogi({"top3": None, "kupon_a": None}) == []


# ── stempel daty przy weryfikacji ──────────────────────────────────────────

def test_weryfikacja_stempluje_date_z_dopasowanego_meczu():
    """Data musi pochodzić z TEGO meczu, z którego wzięty jest kurs."""
    indeks = {("legia", "wisla"): {
        "odds": {"home": 1.85}, "gospodarz": "Legia", "goscie": "Wisła",
        "liga": "PL", "pred": {}, "data": "2026-08-20"}}
    z = {"mecz": "Legia vs Wisła", "typ": "1", "kurs": 52.58}
    with patch("footstats.daily_agent._znajdz_mecz", return_value=indeks[("legia", "wisla")]):
        wynik = _weryfikuj_noge(z, indeks, [])
    assert wynik is not None
    assert wynik["_data"] == "2026-08-20"
    assert wynik["kurs"] == 1.85


# ── uzgodnienie ────────────────────────────────────────────────────────────

def test_uzgodnienie_wola_baze_z_ocalalymi_nogami():
    dane = _dane(top3=[{"mecz": "Legia vs Wisła", "typ": "1", "kurs": 1.85,
                        "_data": "2026-08-20"}])
    with patch("footstats.core.backtest.oznacz_zweryfikowane", return_value=1) as m:
        assert _uzgodnij_predykcje(dane) == 1
    assert m.call_args[0][0][0]["odds"] == 1.85


def test_brak_nog_nie_wola_bazy():
    with patch("footstats.core.backtest.oznacz_zweryfikowane") as m:
        assert _uzgodnij_predykcje(_dane()) == 0
    m.assert_not_called()


def test_rozjazd_nazw_daje_ostrzezenie(caplog):
    """Cicha zero-aktualizacja znaczyłaby, że baza dalej trzyma kurs Groqa."""
    dane = _dane(top3=[
        {"mecz": "Legia vs Wisła", "typ": "1", "kurs": 1.85, "_data": "2026-08-20"},
        {"mecz": "Lech vs Pogoń", "typ": "2", "kurs": 2.05, "_data": "2026-08-20"},
    ])
    with patch("footstats.core.backtest.oznacz_zweryfikowane", return_value=1):
        with caplog.at_level(logging.WARNING, logger="footstats.daily_agent"):
            _uzgodnij_predykcje(dane)
    assert "1 z 2" in caplog.text


def test_blad_bazy_nie_wywala_przebiegu(caplog):
    """Uzgodnienie to księgowość — nie może przerwać dziennego przebiegu."""
    dane = _dane(top3=[{"mecz": "Legia vs Wisła", "typ": "1", "kurs": 1.85,
                        "_data": "2026-08-20"}])
    with patch("footstats.core.backtest.oznacz_zweryfikowane",
               side_effect=RuntimeError("baza padla")):
        with caplog.at_level(logging.WARNING, logger="footstats.daily_agent"):
            assert _uzgodnij_predykcje(dane) == 0
    assert "nie powiodlo sie" in caplog.text
