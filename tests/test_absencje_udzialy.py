"""Laczenie absencji z FotMoba z udzialami w golach z player_db.

Podzial pracy miedzy zrodlami jest tu cala trescia:
  FotMob      mowi KTO nie zagra   (pewne, aktualne, 147 lig)
  player_db   mowi ILE ZNACZY      (pelny poprzedni sezon, 2775 graczy)

Dlaczego nie odwrotnie: `performance.seasonGoals` FotMoba jest w koncu sierpnia
szumem — Premier League po 2 kolejkach dala 5 goli na dwie kadry, wiec udzial
jednego strzelca wyszedlby 0.4 i model policzylby jego absencje jako utrate
40% ataku.

Dlaczego nie przez `injuries_*` i `injury_lambda_factors`: absencje FotMoba NIE
MAJA pozycji (positionId None albo sentinel 1000), a tamta funkcja klasyfikuje
po pozycji — wiec zwrocilaby (1.0, 1.0) i wpiecie byloby cichym no-opem.
`absence_attack_factor` z availability_edge bierze same udzialy, bez pozycji.
"""
from __future__ import annotations

import logging

from footstats.core.absencje import udzialy_absencji

_UDZIALY = {
    "João Pedro": 0.263,
    "Cole Palmer": 0.175,
    "Enzo Fernández": 0.175,
    "Kylian Mbappe-Lottin": 0.325,
}


def test_dokladne_nazwisko_dostaje_swoj_udzial():
    udzialy, nietrafione = udzialy_absencji(["Cole Palmer"], _UDZIALY)
    assert udzialy == [0.175]
    assert nietrafione == []


def test_diakrytyki_nie_gubia_gracza():
    """FotMob i player_db pisza polskie/portugalskie znaki roznie."""
    udzialy, nietrafione = udzialy_absencji(["Joao Pedro", "Enzo Fernandez"], _UDZIALY)
    assert sorted(udzialy) == [0.175, 0.263]
    assert nietrafione == []


def test_dluzsza_forma_nazwiska_w_bazie_dopasowuje_sie():
    """player_db ma "Kylian Mbappe-Lottin", FotMob "Kylian Mbappe"."""
    udzialy, nietrafione = udzialy_absencji(["Kylian Mbappe"], _UDZIALY)
    assert udzialy == [0.325]
    assert nietrafione == []


def test_samo_nazwisko_NIE_wystarcza():
    """Jeden czlon to za malo — "Pedro" trafiloby w dowolnego Pedro w lidze,
    a przypisanie cudzego udzialu jest gorsze niz brak udzialu.

    Baza ma DOKLADNIE JEDEN wpis zaczynajacy sie od tego czlonu — i to jest
    sedno. Przy dwoch Pedro odrzucalby ich straznik niejednoznacznosci, wiec
    test przechodzilby nie dzieki progowi czlonow (mutacja _MIN_CZLONOW = 1
    przezyla pierwsza wersje). Jedno trafienie to realnie grozny przypadek:
    samo nazwisko cicho przypisuje cudzy udzial."""
    baza = {"Pedro Neto": 0.3}
    udzialy, nietrafione = udzialy_absencji(["Pedro"], baza)
    assert udzialy == []
    assert nietrafione == ["Pedro"]


def test_gracz_spoza_bazy_ladauje_w_nietrafionych_a_nie_w_zerach():
    """Zero znaczyloby "zmierzylem, nie strzela". Brak znaczy "nie wiem" —
    i musi byc policzalny, bo to miara zdrowia calego polaczenia."""
    udzialy, nietrafione = udzialy_absencji(["Nieznany Gracz"], _UDZIALY)
    assert udzialy == []
    assert nietrafione == ["Nieznany Gracz"]


def test_niejednoznaczne_dopasowanie_jest_odrzucane(caplog):
    """Dwa wpisy pasuja prefiksem — przypisanie ktoregokolwiek byloby zgadywaniem."""
    udzialy_bazy = {"Rafael Silva Junior": 0.2, "Rafael Silva Neto": 0.1}
    with caplog.at_level(logging.DEBUG):
        udzialy, nietrafione = udzialy_absencji(["Rafael Silva"], udzialy_bazy)
    assert udzialy == []
    assert nietrafione == ["Rafael Silva"]


def test_pusta_baza_udzialow_nie_wybucha():
    udzialy, nietrafione = udzialy_absencji(["Ktokolwiek Ktos"], {})
    assert udzialy == []
    assert nietrafione == ["Ktokolwiek Ktos"]


def test_brak_absencji_daje_puste_listy():
    assert udzialy_absencji([], _UDZIALY) == ([], [])


def test_smieci_w_nazwiskach_sa_pomijane():
    udzialy, nietrafione = udzialy_absencji(["", "   ", "Cole Palmer"], _UDZIALY)
    assert udzialy == [0.175]
    assert nietrafione == []
