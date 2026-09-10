"""Nazwy z Bzzoiro vs nazwy z datasetu — Poisson liczyl 26% ocen modelu.

STAN ZASTANY (2026-09-10). Log jobu: `Poisson policzyl 6 z 36 meczow (16%) —
reszta poszla na fallback Bzzoiro-ML. Powody: predict_match: brak wyniku: 30`.
W `model_log` od 20.08: 219 z 851 ocen (26%) z Poissona-DC. Bundesliga
7/13, Championship 5/33, Ligue 2 4/29.

To nie brak historii, tylko PISOWNIA. Sprawdzone lokalnie na parquecie prod:

    'Bayer 04 Leverkusen' -> 'bayer 04 leverkusen'   dataset: 'Leverkusen'
    'Stoke City'          -> 'stoke city'            dataset: 'Stoke'
    '1. FSV Mainz 05'     -> '1 fsv mainz 05'        dataset: 'Mainz'
    'Real Sociedad'       -> 'real sociedad'         dataset: 'Sociedad'

`_kanoniczne_nazwy` szukalo WYLACZNIE dokladnego klucza. 499 z 887 nazw
z `model_log` (sierpien-wrzesien) nie mialo mapowania.

DLACZEGO NIE W `utils/normalize`. Tamte aliasy dzialaja globalnie: rozliczenia,
dopasowanie meczow u dostawcow, klucze `player_db`. "Stoke City" ma tam zostac
"stoke city", bo czlon `city` odroznia kluby w `team_similarity` (Manchester
United vs City). Precedens w `data/rozszczepienia.py`: problem jest w danych
TRENINGOWYCH, wiec naprawa zostaje po stronie modelu.

REGULY ZAPASOWE, wszystkie deterministyczne, zadnego podobienstwa:
  1. cyfry roku/numeru to szum:     "SC Paderborn 07"     -> "paderborn"
  2. znane slowa-szum:              "Borussia M'gladbach" -> "mgladbach"
  3. czlon tozsamosci, gdy dataset go nie pisze — ta sama regula, ktorej ufaja
     rozliczenia (`team_similarity`), z tym samym wyjatkiem baz wieloznacznych.
Kazde trafienie zapasowe musi miec SWIEZA historie — λ z meczow sprzed lat to
λ innej druzyny.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core.poisson import _kanoniczne_nazwy
from footstats.utils.normalize import normalize_team_name

_SWIEZE = {
    "Stoke": "ENG-Championship", "Norwich": "ENG-Championship",
    "West Brom": "ENG-Championship", "Cambridge": "ENG-League Two",
    "Bristol City": "ENG-Championship", "Bristol Rvs": "ENG-League Two",
    "Leverkusen": "GER-Bundesliga", "Union Berlin": "GER-Bundesliga",
    "Mainz": "GER-Bundesliga", "Paderborn": "GER-2. Bundesliga",
    "M'gladbach": "GER-Bundesliga",
    "Sociedad": "ESP-La Liga", "Sociedad B": "ESP-Segunda Division",
    # Racing Club de Avellaneda. Racing Santander ma w football-data zapis
    # "Santander" — "Real Racing Club" NIE MOZE trafic tutaj.
    "Racing Club": "ARG-Liga Profesional",
    "Independiente": "ARG-Liga Profesional", "FC Tokyo": "JPN-J1 League",
    "Benfica": "POR-Primeira Liga",
}


def _df() -> pd.DataFrame:
    """Kazda druzyna gra raz u siebie; `Oldtown` ma historie sprzed lat."""
    wiersze = [{"gospodarz": n, "goscie": "Rywal", "league": liga,
                "data": pd.Timestamp("2026-08-30")}
               for n, liga in _SWIEZE.items()]
    wiersze.append({"gospodarz": "Oldtown", "goscie": "Rywal", "league": "ENG-League Two",
                    "data": pd.Timestamp("2020-01-01")})
    return pd.DataFrame(wiersze)


def _mapuj(nazwa: str) -> str:
    return _kanoniczne_nazwy(_df(), nazwa, "Rywal")[0]


def test_dokladny_klucz_dalej_wygrywa():
    assert _mapuj("Stoke") == "Stoke"
    assert _mapuj("FC Tokyo") == "FC Tokyo"


@pytest.mark.parametrize("wejscie, oczekiwane", [
    ("Stoke City", "Stoke"),
    ("Norwich City", "Norwich"),
])
def test_czlon_tozsamosci_ktorego_dataset_nie_pisze(wejscie, oczekiwane):
    assert _mapuj(wejscie) == oczekiwane


@pytest.mark.parametrize("wejscie, oczekiwane", [
    ("SC Paderborn 07", "Paderborn"),
    ("1. FC Union Berlin", "Union Berlin"),
    ("Bayer 04 Leverkusen", "Leverkusen"),
])
def test_cyfry_to_szum(wejscie, oczekiwane):
    assert _mapuj(wejscie) == oczekiwane


@pytest.mark.parametrize("wejscie, oczekiwane", [
    ("1. FSV Mainz 05", "Mainz"),
    ("Borussia M'gladbach", "M'gladbach"),
    ("Real Sociedad", "Sociedad"),
])
def test_slowa_szum(wejscie, oczekiwane):
    assert _mapuj(wejscie) == oczekiwane


def test_jawny_alias_historii():
    """Skrot, ktorego zadna regula nie wyprowadzi — `bromwich` to nie szum."""
    assert _mapuj("West Bromwich Albion") == "West Brom"


def test_rezerwy_nie_staja_sie_pierwszym_zespolem():
    assert _mapuj("Real Sociedad") != "Sociedad B"
    assert _mapuj("SL Benfica B U21") == "SL Benfica B U21"


def test_baza_wieloznaczna_zostaje_bez_mapowania():
    """`bristol` nosi w danych dwa kluby — skrot nie mowi ktory."""
    assert _mapuj("Bristol Town") == "Bristol Town"


def test_zadnego_zgadywania_po_podzbiorze_slow():
    """Independiente del Valle (Ekwador) to NIE Independiente (Argentyna)."""
    assert _mapuj("Independiente del Valle") == "Independiente del Valle"
    assert _mapuj("Tokyo Verdy") == "Tokyo Verdy"


def test_slowo_szum_wymaga_kraju_ligi():
    """`real` to hiszpanska konwencja nazw. Zlapane na pomiarze 10.09:
    "Real Racing Club" (Santander) trafial w Racing Club z Argentyny."""
    assert _mapuj("Real Racing Club") == "Real Racing Club"
    assert _mapuj("Real Sociedad") == "Sociedad"


def test_slowo_szum_bez_kolumny_ligi_nie_dziala():
    df = _df().drop(columns=["league"])
    assert _kanoniczne_nazwy(df, "Real Sociedad", "Rywal")[0] == "Real Sociedad"
    # reguly bez slowa-szumu dalej dzialaja
    assert _kanoniczne_nazwy(df, "Stoke City", "Rywal")[0] == "Stoke"


def test_cambridge_to_dwa_kluby_choc_dataset_zna_jeden():
    """Zlapane na pomiarze 10.09: Cambridge City (poza ligami) trafial
    w "Cambridge", czyli Cambridge United. Dataset nie wie o drugim klubie,
    wiec `_BAZY_WIELOZNACZNE` z danych go nie wylapie."""
    assert _mapuj("Cambridge City") == "Cambridge City"
    assert _mapuj("Cambridge United") == "Cambridge"


def test_stara_historia_nie_jest_trafieniem():
    """Klub po zmianie nazwy albo spadku poza zasieg danych — λ bylaby cudza."""
    assert _mapuj("Oldtown City") == "Oldtown City"


def test_bez_kolumny_daty_reguly_zapasowe_nie_dzialaja():
    """Nie da sie sprawdzic swiezosci → fail-closed, dokladny klucz dalej dziala."""
    df = _df().drop(columns=["data"])
    assert _kanoniczne_nazwy(df, "Stoke City", "Stoke")[0] == "Stoke City"
    assert _kanoniczne_nazwy(df, "Stoke City", "Stoke")[1] == "Stoke"


def test_globalna_normalizacja_nietknieta():
    """Rozliczenia i klucze `player_db` zostaja przy starym zachowaniu."""
    assert normalize_team_name("Stoke City") == "stoke city"
    assert normalize_team_name("Real Sociedad") == "real sociedad"
