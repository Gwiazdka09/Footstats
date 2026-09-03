"""Odświeżenie datasetu nie może po cichu zabrać danych, które już mieliśmy.

2026-09-03: `download_all()` nadpisuje `full_dataset.parquet` w całości. Zmiana
po stronie football-data.co.uk (dołożone, prawie puste kolumny B365C* w
`new/JPN.csv`) sprawiła, że jedno odświeżenie skasowało kursy w 4353 japońskich
meczach. Plik dalej wyglądał zdrowo: więcej wierszy niż poprzednio, komplet
40 lig, świeższa data ostatniego meczu. Ubytek widać było dopiero po ręcznym
porównaniu pokrycia kolumn z kopią zapasową.

To jest ten sam wzorzec co „zielone testy, martwa produkcja": nic nie krzyczy,
a pomiar robi się węższy. Mecz bez kursów wypada z ramienia RYNKOWEGO
walk-forwardu (`wf_harness.predict_one` je devigauje), więc porównanie
„model vs rynek" liczy się na mniejszej próbie, nie meldując o tym.

Strażnik działa PER LIGA, bo liga jest jednostką, w której źródło zmienia pliki.
Globalna suma ukryła incydent: −4353 w Japonii zmieszało się z drobnymi
przyrostami w 39 pozostałych ligach i wyszło z tego −3347, czyli 3.8% —
wielkość, którą łatwo wziąć za wahliwość źródła.

Świadomie NIE robimy merge'u ze starym plikiem. Merge dopisałby Japonii kursy
z poprzedniej wersji i incydent nigdy by nie wypłynął — dane wyglądałyby dobrze,
a parser dalej brałby pustą kolumnę. Strażnik ma sprawę pokazać, nie zakleić.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.data import historical_loader as hl


def _ramka(wiersze: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(wiersze)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _liga(nazwa: str, n: int, *, z_kursami: int, od: str = "2025-01-01") -> list[dict]:
    daty = pd.date_range(od, periods=n, freq="D")
    return [
        {
            "date": str(d.date()), "league": nazwa, "home": f"{nazwa}-H{i}",
            "away": f"{nazwa}-A{i}", "hg": 1, "ag": 0,
            "odds_h": 2.0 if i < z_kursami else None,
            "odds_d": 3.3 if i < z_kursami else None,
            "odds_a": 3.8 if i < z_kursami else None,
            "hst": 4.0, "ast": 3.0,
        }
        for i, d in enumerate(daty)
    ]


def test_liga_tracaca_kursy_jest_zglaszana() -> None:
    """Dokładny kształt incydentu JPN: więcej wierszy, mniej kursów."""
    stary = _ramka(_liga("JPN-J1 League", 100, z_kursami=100)
                   + _liga("POL-Ekstraklasa", 50, z_kursami=50))
    # Japonia rośnie o 5 meczów, ale traci kursy w 96 ze 105.
    nowy = _ramka(_liga("JPN-J1 League", 105, z_kursami=9)
                  + _liga("POL-Ekstraklasa", 55, z_kursami=55))

    problemy = hl.regresje_datasetu(stary, nowy)

    assert problemy, "utrata kursow w calej lidze przeszla niezauwazona"
    tresc = " | ".join(problemy)
    assert "JPN-J1 League" in tresc, f"nie wskazano winnej ligi: {tresc}"
    assert "odds_h" in tresc, f"nie wskazano kolumny: {tresc}"
    assert "POL" not in tresc, f"zdrowa liga zglaszana jako problem: {tresc}"


def test_znikniecie_calej_ligi_jest_zglaszane() -> None:
    stary = _ramka(_liga("CHN-Super League", 40, z_kursami=40)
                   + _liga("POL-Ekstraklasa", 50, z_kursami=50))
    nowy = _ramka(_liga("POL-Ekstraklasa", 50, z_kursami=50))

    problemy = hl.regresje_datasetu(stary, nowy)
    assert any("CHN-Super League" in p for p in problemy), problemy


def test_normalny_przyrost_nie_alarmuje() -> None:
    """Zdrowe odświeżenie: więcej meczów, pokrycie bez zmian → cisza.

    Strażnik, który krzyczy przy każdym odświeżeniu, zostanie wyłączony
    po tygodniu i nie złapie następnego incydentu.
    """
    stary = _ramka(_liga("POL-Ekstraklasa", 50, z_kursami=50)
                   + _liga("JPN-J1 League", 100, z_kursami=95))
    nowy = _ramka(_liga("POL-Ekstraklasa", 58, z_kursami=58)
                  + _liga("JPN-J1 League", 108, z_kursami=103))

    assert hl.regresje_datasetu(stary, nowy) == []


def test_pojedynczy_poprawiony_mecz_nie_alarmuje() -> None:
    """Źródło koryguje pojedyncze wiersze — to normalne, nie incydent."""
    stary = _ramka(_liga("POL-Ekstraklasa", 300, z_kursami=300))
    nowy = _ramka(_liga("POL-Ekstraklasa", 300, z_kursami=299))

    assert hl.regresje_datasetu(stary, nowy) == []


def test_nowa_liga_nie_jest_regresja() -> None:
    stary = _ramka(_liga("POL-Ekstraklasa", 50, z_kursami=50))
    nowy = _ramka(_liga("POL-Ekstraklasa", 50, z_kursami=50)
                  + _liga("GRE-Super League", 30, z_kursami=30))

    assert hl.regresje_datasetu(stary, nowy) == []


def test_zapis_odmawia_gdy_dataset_zubozal(monkeypatch, tmp_path) -> None:
    """`download_all` ma NIE nadpisać pliku, gdy nowy zbiór jest uboższy.

    Fail-closed: lepiej zostawić stary dataset i zażądać decyzji człowieka
    niż cicho zastąpić go węższym. Odwrotna kolejność (zapisz, zaloguj ostrzeżenie)
    to dokładnie ten tryb, w którym incydent JPN przeżył cały dzień.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    stary = _ramka(_liga("JPN-J1 League", 100, z_kursami=100))
    stary.to_parquet(tmp_path / "full_dataset.parquet", index=False)

    ubozszy = _ramka(_liga("JPN-J1 League", 100, z_kursami=4))
    monkeypatch.setattr(hl, "download_fdco_seasons", lambda **kw: ubozszy)
    monkeypatch.setattr(hl, "download_fdco_new", lambda **kw: pd.DataFrame())

    with pytest.raises(ValueError, match="JPN-J1 League"):
        hl.download_all()

    # Stary plik ma zostać nietknięty.
    zapisany = pd.read_parquet(tmp_path / "full_dataset.parquet")
    assert int(zapisany["odds_h"].notna().sum()) == 100, "stary dataset zostal nadpisany mimo bledu"


def test_swiadome_wymuszenie_przepuszcza_regresje(monkeypatch, tmp_path) -> None:
    """Regresja bywa uzasadniona (źródło usunęło ligę) — musi być droga naprzód."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    _ramka(_liga("JPN-J1 League", 100, z_kursami=100)).to_parquet(
        tmp_path / "full_dataset.parquet", index=False)

    ubozszy = _ramka(_liga("JPN-J1 League", 100, z_kursami=4))
    monkeypatch.setattr(hl, "download_fdco_seasons", lambda **kw: ubozszy)
    monkeypatch.setattr(hl, "download_fdco_new", lambda **kw: pd.DataFrame())

    df = hl.download_all(pozwol_na_regresje=True)
    assert int(df["odds_h"].notna().sum()) == 4


def test_pierwszy_zapis_bez_poprzednika_przechodzi(monkeypatch, tmp_path) -> None:
    """Brak starego pliku to nie regresja — inaczej nie dałoby się zacząć."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(hl, "download_fdco_seasons",
                        lambda **kw: _ramka(_liga("POL-Ekstraklasa", 20, z_kursami=20)))
    monkeypatch.setattr(hl, "download_fdco_new", lambda **kw: pd.DataFrame())

    df = hl.download_all()
    assert len(df) == 20
