"""Pliki `new/` bywają wielo-ligowe — nazwa ligi musi iść Z PLIKU, nie z kodu kraju.

`_download_fdco_new` wstawiało jedną nazwę per kod kraju
(`FDCO_NEW_LEAGUES[cc]`). Przy POL i AUT to działało, bo tam jest jedna liga.
Przy rozszerzaniu datasetu (2026-08-07) okazało się, że:

    ARG → 'Liga Profesional', 'Liga Profesional ', 'Copa De La Liga Profesional'
    SWZ → 'Super League', 'Challenge League'

czyli druga i trzecia klasa rozgrywkowa wpadłyby do zbioru pod etykietą
pierwszej. `league` służy do filtrowania i do raportów per liga, więc byłby to
cichy fałsz w danych — nie awaria, tylko złe liczby.

Osobno: źródło zostawia w nazwach końcowe spacje ('Superliga '), przez co ta
sama liga występuje jako dwie różne.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from footstats.data import historical_loader as hl

_CSV_WIELOLIGOWY = (
    "Country,League,Season,Date,Home,Away,HG,AG,Res\n"
    "Switzerland,Super League,2026/2027,01/08/2026,Basel,Young Boys,2,1,H\n"
    "Switzerland,Challenge League,2026/2027,02/08/2026,Aarau,Wil,0,0,D\n"
    "Switzerland,Super League ,2026/2027,03/08/2026,Servette,Lugano,1,3,A\n"
)


@pytest.fixture()
def bez_sieci(monkeypatch):
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _CSV_WIELOLIGOWY.encode())


def test_nazwa_ligi_pochodzi_z_pliku_nie_z_kodu_kraju(bez_sieci, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    df = hl._download_fdco_new("SWZ")
    assert df is not None
    ligi = set(df["league"])
    assert ligi == {"SWZ-Super League", "SWZ-Challenge League"}, (
        f"druga klasa rozgrywkowa zlala sie z pierwsza: {ligi}"
    )


def test_koncowe_spacje_nie_tworza_drugiej_ligi(bez_sieci, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    df = hl._download_fdco_new("SWZ")
    assert df is not None
    assert sum(df["league"] == "SWZ-Super League") == 2


def test_prefiks_kraju_zgodny_z_dotychczasowym_nazewnictwem(tmp_path, monkeypatch) -> None:
    """POL i AUT muszą wyjść dokładnie tak jak dotąd — inaczej rozjadą się z bazą.

    W `predictions` i raportach leżą już nazwy 'POL-Ekstraklasa' i
    'AUT-Bundesliga'; zmiana schematu unieważniłaby porównania historyczne.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    csv = (
        "Country,League,Season,Date,Home,Away,HG,AG,Res\n"
        "Poland,Ekstraklasa,2026/2027,01/08/2026,Lech Poznan,Legia,2,1,H\n"
    )
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: csv.encode())
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert set(df["league"]) == {"POL-Ekstraklasa"}


def test_brak_kolumny_league_nie_wywraca_pobierania(tmp_path, monkeypatch) -> None:
    """Starszy plik bez `League` ma dostać nazwę z mapy — degradacja, nie wyjątek."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    csv = (
        "Country,Season,Date,Home,Away,HG,AG,Res\n"
        "Poland,2026/2027,01/08/2026,Lech Poznan,Legia,2,1,H\n"
    )
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: csv.encode())
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert set(df["league"]) == {"POL-Ekstraklasa"}


def test_puste_nazwy_ligi_nie_daja_samego_prefiksu(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    csv = (
        "Country,League,Season,Date,Home,Away,HG,AG,Res\n"
        "Poland,,2026/2027,01/08/2026,Lech Poznan,Legia,2,1,H\n"
    )
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: csv.encode())
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert set(df["league"]) == {"POL-Ekstraklasa"}, "pusta nazwa dala 'POL-'"


# ── zakres pobierania ──────────────────────────────────────────────────────

def test_wszystkie_ligi_sezonowe_maja_nazwe() -> None:
    puste = [k for k, v in hl.FDCO_LEAGUES.items() if not v]
    assert not puste, f"kody lig bez nazwy: {puste}"


def test_kody_lig_sezonowych_bez_duplikatow_nazw() -> None:
    nazwy = list(hl.FDCO_LEAGUES.values())
    assert len(set(nazwy)) == len(nazwy), "dwie ligi o tej samej nazwie zleja sie w datasecie"


def test_kraje_new_maja_nazwe_zapasowa() -> None:
    """Mapa `FDCO_NEW_LEAGUES` jest już tylko fallbackiem, ale musi być pełna."""
    puste = [k for k, v in hl.FDCO_NEW_LEAGUES.items() if not v]
    assert not puste, f"kody krajow bez nazwy zapasowej: {puste}"


def test_pobieramy_wiecej_niz_dwa_kraje_new() -> None:
    """Regresja: przez rok pobieraliśmy tylko POL i AUT, choć dostępnych jest 16."""
    assert len(hl.FDCO_NEW_LEAGUES) >= 10


def test_pobieramy_wiecej_niz_osiem_lig_sezonowych() -> None:
    assert len(hl.FDCO_LEAGUES) >= 15


def test_kolumna_league_ma_prefiks_kraju_dla_kazdego_wiersza(bez_sieci, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    df = hl._download_fdco_new("SWZ")
    assert df is not None
    assert all(str(x).startswith("SWZ-") for x in df["league"])


def test_normalizacja_nazwy_ligi_jest_deterministyczna() -> None:
    assert hl._nazwa_ligi_new("SWZ", "  Super League  ") == "SWZ-Super League"
    assert hl._nazwa_ligi_new("SWZ", None) == hl.FDCO_NEW_LEAGUES.get("SWZ", "SWZ")
    assert hl._nazwa_ligi_new("SWZ", "") == hl.FDCO_NEW_LEAGUES.get("SWZ", "SWZ")


def test_niepelny_komplet_kursow_nie_wywala_pobierania(tmp_path, monkeypatch) -> None:
    """Część plików ma kurs gospodarza bez kursu gościa.

    Parser sprawdzał obecność tylko pierwszej z trzech kolumn, a sięgał po
    wszystkie → `KeyError: 'B365CA'` przerywał pobieranie CAŁEGO kraju.
    Zderzone z realnym plikiem przy rozszerzaniu datasetu 2026-08-07.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    csv = (
        "Country,League,Season,Date,Home,Away,HG,AG,Res,B365CH,B365CD\n"
        "Poland,Ekstraklasa,2026/2027,01/08/2026,Lech Poznan,Legia,2,1,H,1.8,3.4\n"
    )
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: csv.encode())
    df = hl._download_fdco_new("POL")
    assert df is not None and len(df) == 1
    assert "odds_h" not in df.columns or bool(df["odds_h"].isna().all()), (
        "niepelny komplet kursow zapisany jako kompletny"
    )


def test_komplet_kursow_jest_wczytywany(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    csv = (
        "Country,League,Season,Date,Home,Away,HG,AG,Res,B365CH,B365CD,B365CA\n"
        "Poland,Ekstraklasa,2026/2027,01/08/2026,Lech Poznan,Legia,2,1,H,1.8,3.4,4.2\n"
    )
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: csv.encode())
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert float(df["odds_h"].iloc[0]) == 1.8
    assert float(df["odds_a"].iloc[0]) == 4.2


def test_parsowanie_wielu_lig_z_realnego_ukladu_kolumn(tmp_path, monkeypatch) -> None:
    """Kolejność kolumn u źródła bywa inna — parser nie może polegać na pozycji."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    csv = (
        "Date,Home,League,Away,Season,Country,HG,AG,Res\n"
        "01/08/2026,Basel,Super League,Young Boys,2026/2027,Switzerland,2,1,H\n"
    )
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: csv.encode())
    df = hl._download_fdco_new("SWZ")
    assert df is not None
    assert set(df["league"]) == {"SWZ-Super League"}
    assert len(pd.read_csv(io.StringIO(csv))) == 1
