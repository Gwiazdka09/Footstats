"""Kurs rynku = MEDIANA wszystkich bukmacherów, nie kurs pierwszego z listy.

ZMIERZONE 2026-09-03 na planie Pro, 20 meczów z lig, w których typujemy
(League One, Championship, Ekstraklasa, Superliga, Eliteserien, Pro League,
Premiership, CSL, USL), rynek Match Winner, strona gospodarza:

    max      vs pierwszy:  +6.99%  (mediana różnic +5.53%)
    mediana  vs pierwszy:  +0.61%  (mediana różnic  0.00%)
    Pinnacle vs pierwszy:  +3.09%

DLACZEGO NIE MAX, choć kusi. Branie najlepszego z dwunastu zawyżyłoby zapisane
kursy o ~7%. Te kursy idą do EV, Kelly'ego, `total_odds` kuponu i ROI — czyli
podniosłyby wynik paper-tradingu o siedem procent bez jednego wygranego zakładu
więcej. To jest dokładnie ten mechanizm, którym backtesty produkują nieistniejący
edge, a ten projekt ma już zmierzone, że przewagi nad rynkiem nie ma.

DLACZEGO MEDIANA, skoro średnio nie zmienia nic. Bo „pierwszy z listy" to nie jest
żaden kurs — to kolejność, w jakiej dostawca zwrócił bukmacherów. Pojedyncze mecze
różnią się do 19% (Melaka/Negeri Sembilan +18.9%, Brommapojkarna +18.4%), a wynik
potrafi się zmienić bez żadnej zmiany po naszej stronie. Mediana z dwunastu jest
stabilniejsza niż którykolwiek pojedynczy operator i nie zależy od kolejności.

DRUGA KORZYŚĆ, ZMIERZONA OSOBNO: rynek zbierany od WSZYSTKICH bukmacherów, a nie
tylko pierwszego, domyka luki. Na 14 meczach z kursami `Goals Over/Under` był
u pierwszego bukmachera w 11, a u któregokolwiek — w 14. Czyli 21% meczów traciło
kurs na Over/Under 2.5, mimo że rynek istniał. `system_paper.najlepszy_typ` pomija
każdy typ bez kursu, więc te mecze po cichu wypadały z typowania.
"""
from __future__ import annotations

from unittest.mock import patch

from footstats.scrapers.api_football import APIFootball


def _bukmacher(bid: int, nazwa: str, rynki: dict[str, list[tuple[str, str]]]) -> dict:
    return {
        "id": bid,
        "name": nazwa,
        "bets": [
            {"name": rynek, "values": [{"value": et, "odd": kurs} for et, kurs in wartosci]}
            for rynek, wartosci in rynki.items()
        ],
    }


def _odpowiedz(bukmacherzy: list[dict]) -> dict:
    return {"response": [{"bookmakers": bukmacherzy}]}


def _kursy(bukmacherzy: list[dict]) -> dict:
    klient = APIFootball(api_key="dummy")
    with patch.object(klient, "_get", return_value=_odpowiedz(bukmacherzy)):
        return klient.kursy_fixture(123)


def test_bierze_mediane_a_nie_pierwszego():
    wynik = _kursy([
        _bukmacher(7, "William Hill", {"Match Winner": [("Home", "2.00")]}),
        _bukmacher(8, "Bet365", {"Match Winner": [("Home", "2.20")]}),
        _bukmacher(4, "Pinnacle", {"Match Winner": [("Home", "2.40")]}),
    ])
    assert wynik["home"] == 2.20


def test_kolejnosc_bukmacherow_nie_zmienia_kursu():
    """Bez tego kurs zależy od tego, co dostawca zwróci pierwsze."""
    a = _kursy([
        _bukmacher(7, "A", {"Match Winner": [("Home", "2.00")]}),
        _bukmacher(8, "B", {"Match Winner": [("Home", "2.20")]}),
        _bukmacher(4, "C", {"Match Winner": [("Home", "2.40")]}),
    ])
    b = _kursy([
        _bukmacher(4, "C", {"Match Winner": [("Home", "2.40")]}),
        _bukmacher(7, "A", {"Match Winner": [("Home", "2.00")]}),
        _bukmacher(8, "B", {"Match Winner": [("Home", "2.20")]}),
    ])
    assert a == b


def test_nie_bierze_najlepszego_kursu():
    """Regresja przed pokusą: max zawyżyłby ROI o ~7% bez jednego zakładu więcej."""
    wynik = _kursy([
        _bukmacher(7, "A", {"Match Winner": [("Home", "2.00")]}),
        _bukmacher(8, "B", {"Match Winner": [("Home", "2.20")]}),
        _bukmacher(4, "C", {"Match Winner": [("Home", "5.00")]}),
    ])
    assert wynik["home"] == 2.20, "wziete maksimum zamiast mediany"


def test_rynek_zbierany_od_kogokolwiek_go_ma():
    """Pierwszy bukmacher nie ma Over/Under — u innych jest. Zmierzone: 3 z 14 meczów."""
    wynik = _kursy([
        _bukmacher(7, "bez OU", {"Match Winner": [("Home", "2.00")]}),
        _bukmacher(8, "z OU", {
            "Match Winner": [("Home", "2.10")],
            "Goals Over/Under": [("Over 2.5", "1.80"), ("Under 2.5", "2.05")],
        }),
    ])
    assert wynik["over_2_5"] == 1.80
    assert wynik["under_2_5"] == 2.05


def test_btts_obie_strony_dalej_dziala():
    """Regresja: `btts_no` doszlo 15.08, bo model potrafi typowac BTTS NIE."""
    wynik = _kursy([
        _bukmacher(7, "A", {"Both Teams Score": [("Yes", "1.70"), ("No", "2.10")]}),
        _bukmacher(8, "B", {"Both Teams Score": [("Yes", "1.80"), ("No", "2.00")]}),
    ])
    assert wynik["btts"] == 1.75
    assert wynik["btts_no"] == 2.05


def test_brak_rynku_nie_wstawia_falszywej_wartosci():
    wynik = _kursy([_bukmacher(7, "A", {"Match Winner": [("Home", "2.00")]})])
    assert "over_2_5" not in wynik
    assert "btts" not in wynik


def test_brak_bukmacherow_daje_pusty_dict():
    assert _kursy([]) == {}


def test_nieparsowalny_kurs_nie_psuje_mediany():
    """Jeden zepsuty wpis nie moze przewrocic wyceny calego rynku."""
    wynik = _kursy([
        _bukmacher(7, "A", {"Match Winner": [("Home", "2.00")]}),
        _bukmacher(8, "B", {"Match Winner": [("Home", "nie-liczba")]}),
        _bukmacher(4, "C", {"Match Winner": [("Home", "2.40")]}),
    ])
    assert wynik["home"] == 2.20
