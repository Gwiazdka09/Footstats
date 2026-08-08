"""Porównanie skuteczności modeli — statystyka, która nie kłamie na małej próbie.

PO CO: od 2026-08-07 `predictions.model_source` i `model_log.model_source`
rozdzielają Poissona-DC od Bzzoiro-ML. Pytanie „czy nasz model jest lepszy"
sprowadza się do porównania dwóch odsetków — ale przy kilkunastu rozliczonych
meczach różnica 20 punktów procentowych potrafi być czystym szumem.

Dlatego przedział Wilsona (nie „normalny", który przy małym n i odsetkach
blisko 0 lub 1 wychodzi poza [0,1]) i jawny werdykt: rozstrzygnięte tylko
wtedy, gdy przedziały się NIE nakładają i obie próby przekraczają minimum.
Inaczej wprost „za mało danych" — bo wniosek z 17 meczów przebrany za pewnik
jest gorszy niż brak wniosku.
"""
from __future__ import annotations

import pytest

from scripts.porownaj_modele import (
    MIN_ROZLICZONYCH,
    przedzial_wilsona,
    werdykt,
)


# ── przedzial ufnosci ──────────────────────────────────────────────────────

def test_brak_prob_daje_pusty_przedzial() -> None:
    assert przedzial_wilsona(0, 0) == (0.0, 1.0)


def test_przedzial_zawiera_obserwowany_odsetek() -> None:
    dol, gora = przedzial_wilsona(50, 100)
    assert dol < 0.5 < gora


def test_wieksza_proba_zaweza_przedzial() -> None:
    waski = przedzial_wilsona(500, 1000)
    szeroki = przedzial_wilsona(5, 10)
    assert (waski[1] - waski[0]) < (szeroki[1] - szeroki[0])


def test_przedzial_nie_wychodzi_poza_zakres() -> None:
    """Przy skrajnych odsetkach zwykły przedział normalny dawałby ujemny dół."""
    dol, gora = przedzial_wilsona(0, 8)
    assert dol >= 0.0 and gora <= 1.0
    dol, gora = przedzial_wilsona(8, 8)
    assert dol >= 0.0 and gora <= 1.0


def test_komplet_trafien_nie_daje_pewnosci_stu_procent() -> None:
    """8 z 8 to nie jest dowód na 100% — dolna granica musi być wyraźnie niżej."""
    dol, _ = przedzial_wilsona(8, 8)
    assert dol < 0.75


# ── werdykt ────────────────────────────────────────────────────────────────

def test_brak_danych_jednej_strony() -> None:
    w = werdykt(trafienia_a=60, n_a=100, trafienia_b=0, n_b=0)
    assert w["rozstrzygniete"] is False
    assert "za malo" in w["powod"].lower()


def test_za_mala_proba_nie_rozstrzyga() -> None:
    """Nawet ogromna różnica odsetków przy n=10 to jeszcze nic."""
    w = werdykt(trafienia_a=1, n_a=10, trafienia_b=9, n_b=10)
    assert w["rozstrzygniete"] is False


def test_nakladajace_sie_przedzialy_nie_rozstrzygaja() -> None:
    w = werdykt(trafienia_a=52, n_a=100, trafienia_b=48, n_b=100)
    assert w["rozstrzygniete"] is False
    assert "nakla" in w["powod"].lower() or "roznica" in w["powod"].lower()


def test_wyrazna_przewaga_rozstrzyga() -> None:
    w = werdykt(trafienia_a=80, n_a=200, trafienia_b=140, n_b=200)
    assert w["rozstrzygniete"] is True
    assert w["lepszy"] == "b"


def test_wskazuje_wlasciwa_strone() -> None:
    w = werdykt(trafienia_a=150, n_a=200, trafienia_b=70, n_b=200)
    assert w["rozstrzygniete"] is True and w["lepszy"] == "a"


def test_werdykt_podaje_ile_brakuje() -> None:
    w = werdykt(trafienia_a=60, n_a=100, trafienia_b=3, n_b=5)
    assert w["brakuje_b"] == MIN_ROZLICZONYCH - 5


def test_brakuje_zero_gdy_proba_wystarczy() -> None:
    w = werdykt(trafienia_a=60, n_a=100, trafienia_b=55, n_b=100)
    assert w["brakuje_a"] == 0 and w["brakuje_b"] == 0


def test_minimum_jest_zachowawcze() -> None:
    """Świadomy wybór — projekt ma już zapis, że na n=6 nie wolno nic flipować."""
    assert MIN_ROZLICZONYCH >= 30


@pytest.mark.parametrize(("n_a", "n_b"), [(0, 0), (0, 50), (50, 0)])
def test_zero_prob_nigdy_nie_rozstrzyga(n_a: int, n_b: int) -> None:
    w = werdykt(trafienia_a=0, n_a=n_a, trafienia_b=0, n_b=n_b)
    assert w["rozstrzygniete"] is False
