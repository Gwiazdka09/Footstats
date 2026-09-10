"""Lista rynkow w formularzu dziennika = dokladnie to, co automat umie rozliczyc.

STAN ZASTANY (2026-09-10). Formularz kuponu recznego przyjmowal DOWOLNY tekst
typu, a `settle_manual_coupons` rozlicza noge przez `oblicz_tip_correct`, ktore
zna konkretne zapisy ("1", "X2", "Over 2.5", "BTTS NO", "1 OVER 0.5"...).
Typ w stylu kuponow z Superbetu ("Powyzej 0.5 & Powyzej 1.5 1.polowa", rzuty
rozne, strzelec) daje None, noga zostaje ACTIVE na zawsze, a jedynym sladem jest
alarm "dziennik czeka na Ciebie". Wszystkie 7 kuponow `manual` w historii
rozliczono RECZNIE — automat nie ma zadnego dowodu na zywo.

Decyzja 10.09: formularz podaje liste rynkow + "inny — rozlicze sam".

Lista MIESZKA W PYTHONIE i front ja pobiera (`GET /coupon/markets`), zamiast
trzymac druga kopie w JSX. Test nizej przepuszcza kazdy wpis przez prawdziwe
`oblicz_tip_correct` — rynek, ktorego rozliczenie nie umie, nie wejdzie na liste
niezauwazenie, a zmiana w rozliczeniu, ktora wytnie rynek z listy, wywali test.
"""
from __future__ import annotations

import pytest

from footstats.core.rynki_dziennika import RYNKI, czy_rozliczalny, lista_rynkow
from footstats.utils.betting import oblicz_tip_correct

# Wyniki z polowka — pokrywaja remis, zero goli, obie strony, wygrana goscia.
_WYNIKI = ["0-0;HT:0-0", "1-0;HT:1-0", "2-2;HT:1-1", "0-3;HT:0-2", "3-1;HT:2-0"]


@pytest.mark.parametrize("wartosc", [r.wartosc for r in RYNKI])
def test_kazdy_rynek_z_listy_automat_rozlicza(wartosc):
    for wynik in _WYNIKI:
        assert oblicz_tip_correct(wartosc, wynik) in (0, 1), (
            f"rynek {wartosc!r} z listy formularza nie rozlicza sie przy wyniku {wynik}")


@pytest.mark.parametrize("wartosc, wynik, trafiony", [
    ("1", "2-1", 1), ("X2", "2-1", 0), ("Over 2.5", "2-1", 1), ("Under 2.5", "2-1", 0),
    ("BTTS", "1-0", 0), ("BTTS NO", "1-0", 1), ("2 OVER 0.5", "0-3", 1),
    ("1 OVER 1.5", "1-0", 0),
])
def test_rynki_znacza_to_co_etykieta(wartosc, wynik, trafiony):
    assert oblicz_tip_correct(wartosc, wynik) == trafiony


def test_wartosci_unikalne_i_etykiety_niepuste():
    wartosci = [r.wartosc for r in RYNKI]
    assert len(wartosci) == len(set(wartosci))
    assert all(r.etykieta.strip() and r.grupa.strip() for r in RYNKI)


@pytest.mark.parametrize("typ", [
    "Powyżej 0.5 & Powyżej 1.5", "rzuty rożne powyżej 3.5", "Matheus Cunha strzeli",
    "", "   ",
])
def test_typy_spoza_listy_nie_sa_rozliczalne(typ):
    assert czy_rozliczalny(typ) is False


@pytest.mark.parametrize("typ", ["1", "x2", " Over 2.5 ", "BTTS NO"])
def test_typy_z_listy_sa_rozliczalne_niezaleznie_od_zapisu(typ):
    assert czy_rozliczalny(typ) is True


def test_lista_dla_frontu_ma_ksztalt_i_kolejnosc():
    lista = lista_rynkow()
    assert lista[0] == {"wartosc": "1", "etykieta": RYNKI[0].etykieta, "grupa": RYNKI[0].grupa}
    assert [x["wartosc"] for x in lista] == [r.wartosc for r in RYNKI]
