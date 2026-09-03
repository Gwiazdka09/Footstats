"""Kolumnę kursów wybiera POKRYCIE, nie kolejność na liście.

`_download_fdco_new` brało pierwszą trójkę, której trzy kolumny ISTNIEJĄ:

    for h_col, d_col, a_col in [("B365CH", ...), ("AvgCH", ...), ("MaxCH", ...)]:
        if {h_col, d_col, a_col} <= set(df.columns):
            ...
            break

Kolumna, która istnieje i jest pusta, przechodziła ten warunek tak samo dobrze
jak wypełniona. Zmierzone 2026-09-03 na `new/JPN.csv`: źródło dołożyło kolumny
B365C* wypełnione dopiero od sezonu 2025 (170 z 4563 wierszy = 3.7%), przy
`AvgCH` pełnym w 100%. Skutek odświeżenia datasetu: **JPN-J1 League stracił
kursy w 4353 meczach**, przy czym każda inna liga zyskała — czyli sumaryczne
`odds_h` spadło o 3347 i wyglądało na drobną wahliwość źródła.

Dlaczego to boli bardziej, niż wygląda: `wf_harness.predict_one` devigauje
`odds_h/odds_d/odds_a`, żeby odtworzyć ramię RYNKOWE w walk-forwardzie. Mecz bez
kursów cicho wypada z porównania „model vs rynek" — pomiar nie krzyczy, tylko
robi się węższy.

To czwarte wystąpienie tego samego defektu w projekcie („bierz pierwszy" zamiast
„bierz najlepszy"): `results_updater._znajdz_wynik`, `evening_agent._fetch_closing_odds`
i `api_football.kursy_fixture` miały go wcześniej.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.data import historical_loader as hl


def _csv(naglowek: str, wiersze: list[str]) -> bytes:
    return ("\n".join([naglowek, *wiersze]) + "\n").encode()


# B365 istnieje, ale wypełnione tylko w ostatnim wierszu; Avg pełne wszędzie.
# Dokładnie kształt `new/JPN.csv` po zmianie u źródła.
_NAGLOWEK = ("Country,League,Season,Date,Home,Away,HG,AG,Res,"
             "B365CH,B365CD,B365CA,AvgCH,AvgCD,AvgCA")
_WIERSZE_RZADKIE_B365 = [
    "Japan,J1 League,2024,01/03/2024,Kashima,Urawa,2,1,H,,,,2.10,3.40,3.60",
    "Japan,J1 League,2024,02/03/2024,Gamba,Cerezo,0,0,D,,,,2.55,3.20,2.90",
    "Japan,J1 League,2025,03/03/2025,Kobe,Nagoya,1,3,A,1.95,3.50,3.90,1.90,3.45,4.00",
]


@pytest.fixture()
def bez_sieci(monkeypatch, tmp_path):
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)

    def _fake(url, timeout=30):
        return _csv(_NAGLOWEK, _WIERSZE_RZADKIE_B365)

    monkeypatch.setattr(hl, "_get", _fake)


def test_pusta_kolumna_kursow_nie_wygrywa_z_wypelniona(bez_sieci) -> None:
    df = hl._download_fdco_new("JPN")
    assert df is not None

    braki = int(df["odds_h"].isna().sum())
    assert braki == 0, (
        f"{braki} z {len(df)} meczow bez kursu gospodarza — parser wzial trojke"
        " B365 (pusta w 2 z 3 wierszy) zamiast Avg (pelnej)"
    )


def test_wybrana_trojka_jest_spojna_dla_calego_pliku(bez_sieci) -> None:
    """Wszystkie trzy kursy jednego meczu muszą pochodzić z tego samego dostawcy.

    Devig `1/odds` sumuje trzy wyjścia do marży. Zmieszanie dostawców wewnątrz
    jednego meczu daje marżę, której żaden bukmacher nie wystawił, a błąd jest
    niewidoczny — liczby dalej wyglądają jak kursy.
    """
    df = hl._download_fdco_new("JPN")
    assert df is not None

    # Avg dla pierwszego wiersza: 2.10 / 3.40 / 3.60
    pierwszy = df.iloc[0]
    assert (pierwszy["odds_h"], pierwszy["odds_d"], pierwszy["odds_a"]) == (2.10, 3.40, 3.60)


def test_przy_rownym_pokryciu_zostaje_dotychczasowa_kolejnosc(monkeypatch, tmp_path) -> None:
    """Gdy obie trójki są pełne, wygrywa B365 — tak jak dotąd.

    Bez tego poprawka pokrycia przestawiłaby kursy w 39 ligach, w których nic
    się nie zepsuło. Zmiana preferencji dostawcy to osobna decyzja i osobny pomiar.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    pelne = [
        "Poland,Ekstraklasa,2025/2026,01/08/2025,Lech,Legia,2,1,H,1.80,3.60,4.20,1.85,3.55,4.10",
        "Poland,Ekstraklasa,2025/2026,02/08/2025,Wisla,Cracovia,1,1,D,2.40,3.30,2.95,2.45,3.25,2.90",
    ]
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _csv(_NAGLOWEK, pelne))

    df = hl._download_fdco_new("POL")
    assert df is not None
    assert df.iloc[0]["odds_h"] == 1.80, "przy pelnym pokryciu obu trojek B365 ma zostac pierwszy"


def test_wariant_z_polowicznymi_wierszami_nie_liczy_sie_jako_pokryty(monkeypatch, tmp_path) -> None:
    """Wiersz liczy się dopiero z KOMPLETEM kursów wariantu.

    Devig `1/odds` sumuje trzy wyjścia do marży — dwa z trzech dają liczbę,
    której żaden bukmacher nie wystawił. Wariant z pełną kolumną gospodarza
    i pustymi pozostałymi wyglądałby na najlepiej pokryty, gdyby liczyć
    kolumny osobno zamiast wierszy z kompletem.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    # B365: kurs gospodarza wszędzie, remis i gość nigdzie. Avg: komplet w 2 z 3.
    wiersze = [
        "Japan,J1 League,2025,01/03/2025,A,B,1,0,H,1.90,,,2.10,3.40,3.60",
        "Japan,J1 League,2025,02/03/2025,C,D,0,0,D,2.50,,,2.55,3.20,2.90",
        "Japan,J1 League,2025,03/03/2025,E,F,1,3,A,3.10,,,,,",
    ]
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _csv(_NAGLOWEK, wiersze))

    df = hl._download_fdco_new("JPN")
    assert df is not None
    assert df.iloc[0]["odds_h"] == 2.10, "wygral wariant bez kompletu trzech kursow"
    assert int(df[["odds_h", "odds_d", "odds_a"]].notna().all(axis=1).sum()) == 2


def test_same_puste_warianty_nie_tworza_kolumn_kursow(monkeypatch, tmp_path) -> None:
    """Gdy żaden wariant nie ma danych, kolumny mają zostać puste, nie zerowe.

    Wpisanie pustego wariantu „bo był pierwszy" produkuje kolumnę pełną NaN,
    która wygląda identycznie jak brak danych — ale przesłania fakt, że plik
    W OGÓLE nie miał kursów, i psuje późniejsze porównania pokrycia.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    wiersze = ["Japan,J1 League,2025,01/03/2025,A,B,1,0,H,,,,,,"]
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _csv(_NAGLOWEK, wiersze))

    df = hl._download_fdco_new("JPN")
    assert df is not None and len(df) == 1
    assert "odds_h" not in df.columns, "pusty wariant zostal wpisany jako kolumna NaN"


def test_ten_sam_wybor_obowiazuje_w_plikach_sezonowych(monkeypatch, tmp_path) -> None:
    """`_download_fdco_season` miał ten sam defekt — kursy 1X2 z pustej kolumny.

    Reguła żyła w tym pliku w TRZECH kopiach (new 1X2, season 1X2, season O/U).
    Trzy kopie jednej reguły to trzy okazje, żeby rozjechały się po cichu —
    dokładnie tak, jak stało się z `new/JPN.csv`.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    naglowek = ("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,"
                "B365H,B365D,B365A,AvgH,AvgD,AvgA")
    wiersze = [
        "E0,01/08/2025,Arsenal,Chelsea,2,1,H,,,,1.95,3.50,3.80",
        "E0,02/08/2025,Liverpool,Everton,3,0,H,,,,1.40,4.60,7.50",
    ]
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _csv(naglowek, wiersze))

    df = hl._download_fdco_season("E0", "2526")
    assert df is not None and len(df) == 2
    braki = int(df["odds_h"].isna().sum())
    assert braki == 0, f"{braki} meczow bez kursu — season wzial pusta trojke B365"
    assert df.iloc[0]["odds_h"] == 1.95


def test_ten_sam_wybor_obowiazuje_dla_over_under(monkeypatch, tmp_path) -> None:
    """Kursy Over/Under 2.5 wybierane tą samą regułą co 1X2."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    naglowek = ("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,"
                "B365>2.5,B365<2.5,Avg>2.5,Avg<2.5")
    wiersze = [
        "E0,01/08/2025,Arsenal,Chelsea,2,1,H,,,1.85,1.95",
        "E0,02/08/2025,Liverpool,Everton,3,0,H,,,1.70,2.10",
    ]
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _csv(naglowek, wiersze))

    df = hl._download_fdco_season("E0", "2526")
    assert df is not None and len(df) == 2
    braki = int(df["odds_over25"].isna().sum())
    assert braki == 0, f"{braki} meczow bez kursu Over — wziete z pustej kolumny B365"
    assert df.iloc[0]["odds_over25"] == 1.85


def test_brak_jakichkolwiek_kursow_nie_wywraca_pobierania(monkeypatch, tmp_path) -> None:
    """Plik bez kolumn kursowych ma dać mecze bez kursów, nie wyjątek."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _csv(
        "Country,League,Season,Date,Home,Away,HG,AG,Res",
        ["Ireland,Premier Division,2026,01/08/2026,Shels,Bohemians,1,0,H"],
    ))

    df = hl._download_fdco_new("IRL")
    assert df is not None and len(df) == 1
    assert "odds_h" not in df.columns or pd.isna(df.iloc[0]["odds_h"])
