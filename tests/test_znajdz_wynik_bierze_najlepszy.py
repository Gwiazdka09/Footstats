"""`_znajdz_wynik` ma brać NAJLEPSZE dopasowanie, nie pierwsze powyżej progu.

ZNALEZIONE 2026-09-03 przy dopisywaniu aliasu `AGF` -> `Aarhus` (kupon #351).
Alias jest poprawny, ale tworzy sąsiada:

    AGF  vs  Aarhus         = 1.00   <- ten sam klub
    AGF  vs  Aarhus Fremad  = 0.80   <- INNY klub, 2. liga duńska

Oba powyżej progu 0.70. Struktura pary jest identyczna z `Legia` ~ `Legia
Warszawa`, więc żadna reguła ogólna ich nie rozdzieli — ale RÓŻNICA WYNIKÓW jest
duża i jednoznaczna. Skoro tak, o rozliczeniu nie może decydować kolejność
fixture'ów w odpowiedzi dostawcy.

To nie jest przypadek jednego klubu. Ta sama pułapka czeka wszędzie, gdzie klub
ma sąsiada dzielącego pierwszy człon nazwy (Aarhus/Aarhus Fremad,
Legia/Legia II — ten ostatni łapią `ZNACZNIKI_REZERW`, ale tylko dlatego, że
ktoś je wypisał). Wybór najlepszego zamiast pierwszego zdejmuje całą klasę.

Kosztem jest przejście całej listy zamiast wyjścia przy pierwszym trafieniu —
przy jednym zapytaniu na dzień to nic.
"""
from __future__ import annotations

import footstats.scrapers.results_updater as ru


def _fixture(home: str, away: str, gole_h: int, gole_a: int) -> dict:
    return {
        "fixture": {"id": abs(hash((home, away))) % 100000, "status": {"short": "FT"}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": gole_h, "away": gole_a},
        "score": {"halftime": {"home": None, "away": None}},
    }


def test_gorsze_dopasowanie_wczesniej_na_liscie_nie_wygrywa():
    """Realny uklad z 02.09: kupon na AGF, a u dostawcy sa oba kluby z Aarhus."""
    pending = {"team_home": "AGF", "team_away": "FC Midtjylland"}
    fixtures = [
        _fixture("Aarhus Fremad", "FC Midtjylland", 3, 3),   # 0.80 — INNY klub
        _fixture("Aarhus", "FC Midtjylland", 0, 2),          # 1.00 — ten wlasciwy
    ]

    wynik, _ = ru._znajdz_wynik(pending, fixtures, api_key=None)
    assert wynik == "0-2", "wygralo dopasowanie 0.80, bo bylo pierwsze na liscie"


def test_kolejnosc_listy_nie_zmienia_wyniku():
    """Odwrocona lista musi dac to samo — inaczej wynik zalezy od dostawcy."""
    pending = {"team_home": "AGF", "team_away": "FC Midtjylland"}
    lepszy = _fixture("Aarhus", "FC Midtjylland", 0, 2)
    gorszy = _fixture("Aarhus Fremad", "FC Midtjylland", 3, 3)

    a, _ = ru._znajdz_wynik(pending, [gorszy, lepszy], api_key=None)
    b, _ = ru._znajdz_wynik(pending, [lepszy, gorszy], api_key=None)
    assert a == b == "0-2"


def test_ponizej_progu_dalej_nie_dopasowuje():
    """Wybor najlepszego NIE jest obnizeniem progu — to musi zostac jasne.

    Bez tego testu zmiana wygladalaby jak „bierz najlepszy, jaki jest",
    czyli fail-open dla kuponu, ktorego meczu w ogole nie ma w puli.
    """
    pending = {"team_home": "AGF", "team_away": "FC Midtjylland"}
    fixtures = [_fixture("Silkeborg", "Randers", 1, 1)]

    assert ru._znajdz_wynik(pending, fixtures, api_key=None) is None


def test_remis_podobienstwa_nie_wywraca_dopasowania():
    """Dwa rowne dopasowania: bierzemy pierwsze i nie padamy."""
    pending = {"team_home": "AGF", "team_away": "FC Midtjylland"}
    fixtures = [
        _fixture("Aarhus", "FC Midtjylland", 0, 2),
        _fixture("Aarhus", "FC Midtjylland", 0, 2),
    ]

    wynik, _ = ru._znajdz_wynik(pending, fixtures, api_key=None)
    assert wynik == "0-2"
