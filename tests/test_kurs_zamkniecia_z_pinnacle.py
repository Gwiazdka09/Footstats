"""Kurs zamknięcia do CLV musi pochodzić od USTALONEGO bukmachera, nie od pierwszego.

ZMIERZONE 2026-09-03 na realnym fixture (Aston Villa vs Arsenal, 31.08), rynek
Match Winner, strona gospodarza — dwanaście bukmacherów z API-Football Pro:

    William Hill 5.80   Bet365 6.25   Marathonbet 6.45   Unibet 6.40
    Betfair      6.50   BetVictor 6.00   Pinnacle 6.34   SBO 5.99
    1xBet        6.45   Betano 6.00   Superbet 5.80   Dafabet 6.20

Rozrzut 5.80-6.50, czyli **12% na tym samym zdarzeniu**. `_fetch_closing_odds`
brało `bookmakers[0]` — kogokolwiek dostawca zwrócił pierwszego. Tu wypadł
William Hill, czyli NAJNIŻSZY kurs w stawce.

To nie jest szum, tylko OBCIĄŻENIE. CLV porównuje kurs, który wzięliśmy, z kursem
zamknięcia; jeśli benchmarkiem jest systematycznie gorsza cena, nasza przewaga
wychodzi zawyżona. A ponieważ kolejność bukmacherów zależy od dostawcy, wynik
potrafi się zmienić bez żadnej zmiany po naszej stronie.

Pinnacle jest tu benchmarkiem nieprzypadkowym: to ten sam operator, którego kolumny
closing bierze darmowy fallback `closing_odds.py` (football-data.co.uk), i ten sam,
wobec którego mierzyliśmy edge 28.08. Dwa źródła CLV muszą mierzyć wobec tego
samego, inaczej ich wyniki nie są porównywalne.

Docstring funkcji twierdził „Bet365 id=1 lub pierwszy dostępny" — nieprawda w obu
członach: kod nie szukał Bet365, a Bet365 ma id 8, nie 1.
"""
from __future__ import annotations

from unittest.mock import patch

import footstats.evening_agent as ea


def _odpowiedz(pary: list[tuple[int, str, str]]) -> dict:
    """Payload /odds w kształcie API-Football: [(id, nazwa, kurs_home), ...]."""
    return {
        "response": [{
            "bookmakers": [
                {
                    "id": bid,
                    "name": nazwa,
                    "bets": [{
                        "id": 1,
                        "name": "Match Winner",
                        "values": [
                            {"value": "Home", "odd": kurs},
                            {"value": "Draw", "odd": "4.00"},
                            {"value": "Away", "odd": "1.50"},
                        ],
                    }],
                }
                for bid, nazwa, kurs in pary
            ]
        }]
    }


class _Odp:
    status_code = 200

    def __init__(self, dane):
        self._dane = dane

    def json(self):
        return self._dane


def _wywolaj(pary):
    with patch.object(ea.requests, "get", return_value=_Odp(_odpowiedz(pary))), \
         patch("footstats.scrapers.results_updater._naglowek_af",
               return_value={"x-apisports-key": "test"}):
        return ea._fetch_closing_odds("klucz", 1557377)


def test_bierze_pinnacle_a_nie_pierwszego_z_listy():
    """Realny układ: Pinnacle jest siódmy, William Hill pierwszy."""
    kurs = _wywolaj([
        (7, "William Hill", "5.80"),
        (8, "Bet365", "6.25"),
        (4, "Pinnacle", "6.34"),
        (3, "Betfair", "6.50"),
    ])
    assert kurs == 6.34


def test_kolejnosc_bukmacherow_nie_zmienia_wyniku():
    """Bez tego CLV zmienia się od tego, co dostawca zwróci pierwsze."""
    a = _wywolaj([(4, "Pinnacle", "6.34"), (7, "William Hill", "5.80")])
    b = _wywolaj([(7, "William Hill", "5.80"), (4, "Pinnacle", "6.34")])
    assert a == b == 6.34


def test_bez_pinnacle_bierze_mediane_a_nie_pierwszego():
    """Fallback też musi być deterministyczny i nieobciążony.

    Mediana z całej stawki jest odporna na skrajności; „pierwszy z listy" nie jest
    ani jedno, ani drugie.
    """
    kurs = _wywolaj([
        (7, "William Hill", "5.80"),
        (8, "Bet365", "6.25"),
        (3, "Betfair", "6.50"),
    ])
    assert kurs == 6.25


def test_brak_bukmacherow_daje_none():
    """Fail-closed: brak danych to None, nie zgadywana liczba."""
    assert _wywolaj([]) is None
