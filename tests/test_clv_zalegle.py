"""Kurs zamkniecia dla nog rozliczonych W POPRZEDNICH dniach.

STAN ZASTANY (2026-09-10). CLV ozylo 07.09, ale tylko na typie "1":

    typ         nog rozliczonych od 06.09   z kursem zamkniecia
    OVER 2.5            45                          0
    UNDER 2.5           23                          0
    1                   10                          5

Przyczyna to CZAS, nie kod dopasowania. `evening_agent` szuka kursu w dniu
meczu o 21:00 UTC, a football-data.co.uk dopisuje mecze do CSV z opoznieniem
kilku dni. Typ "1" dostawal cene wylacznie z fallbacku API-Football — ktory
dla Over/Under nie istnieje. Sprawdzone lokalnie 10.09: Cagliari-Lecce
(07.09) i Getafe-Celta (07.09) MAJA juz w CSV kursy Under 2.5, a w bazie te
nogi stoja z `clv_closing = None`.

Pomiar na 219 rozliczonych kuponach od 01.09: z 214 nog bez CLV (typy
mapowalne) football-data daje kurs TERAZ dla 55 — wobec 5 w dniu meczu.

Noga nie zna swojej daty (klucze: home, away, tip, odds, liga, result...),
wiec probujemy `match_date_first` i dwa kolejne dni. Para druzyn plus DOKLADNA
data z CSV nie dopasuje cudzego meczu — ta sama para nie gra dwa razy w trzy dni.
"""
from __future__ import annotations

from datetime import date

from footstats.core import clv_zalegle as cz


def _kupon(id_, dzien, nogi):
    return {"id": id_, "match_date_first": dzien, "nogi": nogi}


def _noga(typ="Under 2.5", home="Cagliari", away="Lecce", **reszta):
    return {"home": home, "away": away, "tip": typ, "odds": 1.58,
            "result": "1-0;HT:1-0", "leg_won": True, **reszta}


class _Kursy:
    """Atrapa `kursy_zamkniecia`: mecz jest w CSV tylko pod wskazana data."""

    def __init__(self, data_w_csv="2026-09-07", kursy=None):
        self.data_w_csv = data_w_csv
        self.kursy = kursy or {"home": 2.21, "draw": 3.03, "away": 3.55,
                               "over_2_5": 2.30, "under_2_5": 1.59}
        self.zapytania: list[tuple] = []

    def __call__(self, home, away, data):
        self.zapytania.append((home, away, data))
        return self.kursy if data == self.data_w_csv else None


def _uruchom(kupony, kursy):
    zapisane: dict[int, list] = {}
    wynik = cz.uzupelnij_clv_zaleglych(
        date(2026, 9, 10),
        _wczytaj=lambda od: kupony,
        _zapisz=lambda id_, nogi: zapisane.__setitem__(id_, nogi),
        _kursy=kursy,
    )
    return wynik, zapisane


def test_noga_bez_clv_dostaje_kurs_swojego_typu():
    (uzup, spr), zapisane = _uruchom([_kupon(487, "2026-09-07", [_noga()])], _Kursy())
    assert (uzup, spr) == (1, 1)
    assert zapisane[487][0]["clv_closing"] == 1.59


def test_mecz_dopisany_pod_kolejnym_dniem():
    """Kupon z `match_date_first` 07.09, mecz w CSV pod 08.09 (np. po polnocy UTC)."""
    (uzup, _), zapisane = _uruchom([_kupon(1, "2026-09-07", [_noga()])],
                                    _Kursy(data_w_csv="2026-09-08"))
    assert uzup == 1


def test_nie_szuka_dalej_niz_dwa_dni():
    kursy = _Kursy(data_w_csv="2026-09-10")
    (uzup, _), zapisane = _uruchom([_kupon(1, "2026-09-07", [_noga()])], kursy)
    assert uzup == 0 and not zapisane
    assert {d for *_, d in kursy.zapytania} == {"2026-09-07", "2026-09-08", "2026-09-09"}


def test_istniejace_clv_nie_jest_nadpisywane_ani_odpytywane():
    kursy = _Kursy()
    (uzup, spr), zapisane = _uruchom(
        [_kupon(1, "2026-09-07", [_noga(clv_closing=1.61)])], kursy)
    assert (uzup, spr) == (0, 0) and not zapisane and not kursy.zapytania


def test_typ_bez_ceny_w_csv_nie_wychodzi_do_sieci():
    """BTTS czy podwojna szansa nie maja odpowiednika — zero zapytan, zero CLV."""
    kursy = _Kursy()
    (uzup, spr), _ = _uruchom([_kupon(1, "2026-09-07", [_noga(typ="BTTS")])], kursy)
    assert (uzup, spr) == (0, 0) and not kursy.zapytania


def test_noga_nierozliczona_pominieta():
    kursy = _Kursy()
    (uzup, spr), _ = _uruchom([_kupon(1, "2026-09-07", [_noga(result=None)])], kursy)
    assert (uzup, spr) == (0, 0) and not kursy.zapytania


def test_zapis_tylko_gdy_cos_sie_zmienilo_i_z_calym_kuponem():
    """Kupon zapisujemy w CALOSCI — noga bez kursu zostaje, jaka byla."""
    nogi = [_noga(), _noga(home="X", away="Y", typ="Over 2.5")]
    (uzup, spr), zapisane = _uruchom([_kupon(9, "2026-09-07", nogi)], _Kursy())
    assert (uzup, spr) == (2, 2)  # atrapa oddaje kursy dla kazdej pary w tej dacie
    assert [n["clv_closing"] for n in zapisane[9]] == [1.59, 2.30]


def test_wejscie_nie_jest_mutowane():
    noga = _noga()
    _uruchom([_kupon(1, "2026-09-07", [noga])], _Kursy())
    assert "clv_closing" not in noga


def test_evening_naprawde_to_wola():
    """Moduł bez wywołania z potoku to kolejny zielony test na martwym kodzie."""
    from pathlib import Path

    zrodlo = Path("src/footstats/evening_agent.py").read_text(encoding="utf-8")
    kod = "\n".join(l for l in zrodlo.splitlines() if not l.lstrip().startswith("#"))
    assert "uzupelnij_clv_zaleglych(" in kod


def test_blad_zrodla_nie_przerywa_reszty():
    def _kursy(home, away, data):
        if home == "Zly":
            raise OSError("503")
        return {"under_2_5": 1.59, "home": 2.0, "draw": 3.0, "away": 4.0}

    kupony = [_kupon(1, "2026-09-07", [_noga(home="Zly")]),
              _kupon(2, "2026-09-07", [_noga()])]
    (uzup, spr), zapisane = _uruchom(kupony, _kursy)
    assert uzup == 1 and 2 in zapisane and 1 not in zapisane
