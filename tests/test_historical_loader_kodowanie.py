"""Kodowanie CSV z football-data.co.uk — UTF-8 nie może cicho stać się mojibake.

PO CO: loader czytał wszystko jako `latin-1`, a latin-1 dekoduje KAŻDY bajt bez
błędu. Plik zapisany w UTF-8 nie wywalał wyjątku, tylko wchodził przekręcony:
w datasecie siedziało "PreuÃen MÃ¼nster" zamiast "Preußen Münster" (68 meczów
2. Bundesligi). Nazwa przekręcona = drużyna nie do dopasowania, czyli brak λ
Poissona i brak formy — dokładnie ta klasa cichej awarii, która blokowała model.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.data import historical_loader as hl


def _csv_bajty(kodowanie: str) -> bytes:
    return (
        "Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        "01/08/2025,Preußen Münster,Köln,2,1,H\n"
    ).encode(kodowanie)


@pytest.mark.parametrize("kodowanie", ["utf-8", "cp1252"])
def test_nazwy_z_diakrytykami_czytane_bez_mojibake(monkeypatch, kodowanie):
    """Oba kodowania używane przez źródło dają tę samą, poprawną nazwę."""
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _csv_bajty(kodowanie))

    df = hl._download_fdco_season("D2", "2526")

    assert df is not None
    assert df.iloc[0]["home"] == "Preußen Münster"
    assert df.iloc[0]["away"] == "Köln"


def test_nowy_format_tez_szanuje_utf8(monkeypatch):
    """Ta sama reguła w gałęzi `new/` — kraje spoza głównych lig mają diakrytyki."""
    tresc = (
        "Country,League,Season,Date,Home,Away,HG,AG,Res\n"
        "POLAND,Ekstraklasa,2025,01/08/2025,Wisła Kraków,Górnik Zabrze,1,1,D\n"
    ).encode("utf-8")
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: tresc)

    df = hl._download_fdco_new("POL")

    assert df is not None
    assert df.iloc[0]["home"] == "Wisła Kraków"
    assert df.iloc[0]["away"] == "Górnik Zabrze"


def test_bajty_niebedace_utf8_nadal_wchodza_przez_latin1(monkeypatch):
    """Fallback musi zostać: archiwalne pliki źródła SĄ w cp1252, nie w UTF-8.

    Gdyby fix polegał na samej zamianie kodowania, te sezony przestałyby się
    wczytywać — a to strata danych większa niż jedna przekręcona nazwa.
    """
    monkeypatch.setattr(hl, "_get", lambda url, timeout=30: _csv_bajty("cp1252"))

    df = hl._download_fdco_season("D1", "2425")

    assert df is not None
    assert not df.empty
    assert "Ã" not in df.iloc[0]["home"]


def test_czytaj_csv_zwraca_ramke_dla_obu_kodowan():
    """Sam helper — bez sieci, żeby regresja była widoczna od razu."""
    for kodowanie in ("utf-8", "cp1252"):
        df = hl._czytaj_csv(_csv_bajty(kodowanie))
        assert isinstance(df, pd.DataFrame)
        assert df.iloc[0]["HomeTeam"] == "Preußen Münster"
