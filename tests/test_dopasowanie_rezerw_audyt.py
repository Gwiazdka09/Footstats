"""test_dopasowanie_rezerw_audyt.py — rezerwy w POZOSTAŁYCH miejscach dopasowania.

PO CO: bug "rezerwy uznane za pierwszy zespół" siedział w czterech niezależnych
miejscach, bo każde liczyło podobieństwo nazw po swojemu. Trzy pierwsze
naprawione wcześniej (coupon_settlement, flashscore_results, daily_phases),
ten plik pilnuje dwóch ostatnich — obu dotyczących PIENIĘDZY:

  * `APIFootball.znajdz_fixture_id` — zwraca fixture, z którego pobierane są
    KURSY i statystyki. Zły fixture = kursy z innego meczu.
  * `daily_agent._znajdz_mecz` — dopasowuje mecz z odpowiedzi Groq do indeksu
    Bzzoiro, żeby PODMIENIĆ kurs na rzeczywisty (anty-halucynacja). Złe
    dopasowanie oznacza nogę z kursem z cudzego meczu, która przeszła
    weryfikację.

Poprzedni audyt tego nie wyłapał, bo szukał `SequenceMatcher`/`difflib`, a tutaj
dopasowanie robione było operatorem `in` — inny zapis, ten sam błąd. Stąd ten
plik trzyma oba miejsca razem: to jedna klasa ryzyka, nie dwie osobne.
"""
from __future__ import annotations

import pytest

import footstats.daily_agent as da
from footstats.scrapers.api_football import APIFootball

# Pary: (nazwa w naszych danych, nazwa rezerw u dostawcy)
REZERWY = [
    ("Legia", "Legia II"),
    ("Barcelona", "Barcelona B"),
    ("Chelsea", "Chelsea U21"),
    ("Ajax", "Jong Ajax"),
]


# ── APIFootball.znajdz_fixture_id ───────────────────────────────────────────

def _klient(monkeypatch, fixtures: list) -> APIFootball:
    af = APIFootball("klucz-testowy")
    monkeypatch.setattr(af, "_get", lambda *a, **k: {"response": fixtures})
    return af


def _fx(home: str, away: str, fid: int) -> dict:
    return {"fixture": {"id": fid}, "teams": {"home": {"name": home}, "away": {"name": away}}}


@pytest.mark.parametrize("pierwszy,rezerwy", REZERWY)
def test_fixture_rezerw_nie_zwrocony(monkeypatch, pierwszy, rezerwy):
    """Kursy pobrane z meczu rezerw trafiłyby do kuponu na pierwszy zespół."""
    af = _klient(monkeypatch, [_fx(rezerwy, "Lech Poznan II", 99)])

    assert af.znajdz_fixture_id(pierwszy, "Lech Poznan", "2026-08-02") is None


def test_fixture_pierwszego_zespolu_wygrywa_z_rezerwami(monkeypatch):
    af = _klient(monkeypatch, [_fx("Legia II", "Lech Poznan II", 99),
                               _fx("Legia", "Lech Poznan", 7)])

    assert af.znajdz_fixture_id("Legia", "Lech Poznan", "2026-08-02") == 7


def test_fixture_wariant_nazwy_nadal_trafia(monkeypatch):
    """Poprawka nie może zabić legalnych wariantów nazwy."""
    af = _klient(monkeypatch, [_fx("Legia Warszawa", "Lech Poznan", 11)])

    assert af.znajdz_fixture_id("Legia", "Lech Poznan", "2026-08-02") == 11


def test_fixture_brak_dopasowania_to_none(monkeypatch):
    af = _klient(monkeypatch, [_fx("Arka Gdynia", "Wisla Krakow", 3)])

    assert af.znajdz_fixture_id("Legia", "Lech Poznan", "2026-08-02") is None


def test_fixture_smieciowy_wpis_pomijany(monkeypatch):
    """Pusta nazwa po normalizacji nie może pasować do wszystkiego."""
    af = _klient(monkeypatch, [_fx("", "", 4), _fx("FC", "AC", 5)])

    assert af.znajdz_fixture_id("Legia", "Lech Poznan", "2026-08-02") is None


def test_fixture_pusta_odpowiedz(monkeypatch):
    af = APIFootball("klucz-testowy")
    monkeypatch.setattr(af, "_get", lambda *a, **k: None)

    assert af.znajdz_fixture_id("Legia", "Lech Poznan", "2026-08-02") is None


# ── daily_agent._znajdz_mecz ────────────────────────────────────────────────

def _indeks(pary: list[tuple[str, str]]) -> dict:
    return {(da._norm(g), da._norm(a)): {"gosp": g, "gosc": a} for g, a in pary}


@pytest.mark.parametrize("pierwszy,rezerwy", REZERWY)
def test_mecz_rezerw_nie_podmienia_kursu(pierwszy, rezerwy):
    """Noga dostałaby kurs z meczu rezerw i przeszła weryfikację jako poprawna."""
    indeks = _indeks([(rezerwy, "Lech Poznan II")])

    assert da._znajdz_mecz(f"{pierwszy} vs Lech Poznan", indeks) is None


def test_mecz_pierwszego_zespolu_znaleziony():
    indeks = _indeks([("Legia II", "Lech Poznan II"), ("Legia", "Lech Poznan")])

    wynik = da._znajdz_mecz("Legia vs Lech Poznan", indeks)

    assert wynik is not None and wynik["gosp"] == "Legia"


def test_mecz_wariant_nazwy_nadal_trafia():
    indeks = _indeks([("Legia Warszawa", "Lech Poznan")])

    assert da._znajdz_mecz("Legia vs Lech Poznan", indeks) is not None


def test_mecz_separator_myslnikiem():
    """Groq bywa niekonsekwentny w separatorze — obie formy muszą działać."""
    indeks = _indeks([("Legia", "Lech Poznan")])

    assert da._znajdz_mecz("Legia - Lech Poznan", indeks) is not None


def test_mecz_bez_separatora_to_none():
    assert da._znajdz_mecz("Legia Lech Poznan", _indeks([("Legia", "Lech Poznan")])) is None


def test_mecz_brak_dopasowania_to_none():
    indeks = _indeks([("Arka Gdynia", "Wisla Krakow")])

    assert da._znajdz_mecz("Legia vs Lech Poznan", indeks) is None


def test_mecz_pusty_indeks():
    assert da._znajdz_mecz("Legia vs Lech Poznan", {}) is None
