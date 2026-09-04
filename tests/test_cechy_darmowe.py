"""Cechy darmowe — czy liczą TO, co deklarują, i czy nie widzą przyszłości.

Cechy powstają z gimnastyki na `groupby().rolling()` i dwóch merge'ach, czyli
dokładnie tam, gdzie błąd jest cichy: liczba dalej wygląda sensownie, a mierzy
nie to. Każda z pięciu ma tu przypadek policzalny ręcznie.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from cechy_darmowe import zbuduj_cechy  # noqa: E402


def _mecz(data: str, dom: str, wyj: str, liga: str = "L1", sezon: str = "2024") -> dict:
    return {"date": pd.Timestamp(data), "league": liga, "season": sezon,
            "home": dom, "away": wyj}


def _ramka(wiersze: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(wiersze)


def test_odpoczynek_to_dni_od_poprzedniego_meczu_kazdej_druzyny():
    """A gra 01→08→11 (3 dni przerwy), B gra 05→11 (6 dni). Różnica = 3-6 = -3."""
    df = _ramka([
        _mecz("2024-01-01", "A", "X"),
        _mecz("2024-01-05", "B", "Y"),
        _mecz("2024-01-08", "A", "Z"),
        _mecz("2024-01-11", "A", "B"),
    ])
    c = zbuduj_cechy(df)
    ostatni = c.iloc[3]
    assert ostatni["home"] == "A" and ostatni["away"] == "B"
    assert ostatni["roznica_odpoczynku"] == pytest.approx(3.0 - 6.0)
    assert ostatni["min_odpoczynek"] == pytest.approx(3.0)


def test_pierwszy_mecz_druzyny_nie_ma_odpoczynku():
    """Brak poprzednika to NaN, nie zero. Zero znaczyłoby 'grał wczoraj'."""
    df = _ramka([_mecz("2024-01-01", "A", "B")])
    c = zbuduj_cechy(df)
    assert pd.isna(c.iloc[0]["roznica_odpoczynku"])
    assert pd.isna(c.iloc[0]["min_odpoczynek"])


def test_zageszczenie_nie_liczy_meczu_biezacego():
    """A ma 3 mecze w oknie 14 dni licząc bieżący → zagęszczenie 2, nie 3."""
    df = _ramka([
        _mecz("2024-01-01", "A", "X"),
        _mecz("2024-01-08", "A", "Y"),
        _mecz("2024-01-11", "A", "B"),
    ])
    c = zbuduj_cechy(df)
    # B gra pierwszy raz: 0 wczesniejszych. A ma dwa. Roznica = 2.
    assert c.iloc[2]["roznica_zageszczenia"] == pytest.approx(2.0)


def test_zageszczenie_zapomina_mecze_starsze_niz_14_dni():
    df = _ramka([
        _mecz("2024-01-01", "A", "X"),
        _mecz("2024-02-01", "A", "B"),      # 31 dni pozniej — okno puste
    ])
    c = zbuduj_cechy(df)
    assert c.iloc[1]["roznica_zageszczenia"] == pytest.approx(0.0)


def test_zageszczenie_liczy_mecze_wyjazdowe_tak_samo():
    """Mecz obciąża nogi niezależnie od tego, czy u siebie czy na wyjeździe."""
    df = _ramka([
        _mecz("2024-01-02", "X", "A"),      # A na wyjezdzie
        _mecz("2024-01-05", "Y", "A"),      # A na wyjezdzie
        _mecz("2024-01-08", "A", "B"),
    ])
    c = zbuduj_cechy(df)
    assert c.iloc[2]["roznica_zageszczenia"] == pytest.approx(2.0)


def test_beniaminek_to_druzyna_z_mala_historia_W_TEJ_LIDZE():
    """A ma 6 meczów w L1, B przychodzi z L2 — w L1 jest nowa mimo stażu."""
    wiersze = [_mecz(f"2024-01-{d:02d}", "A", f"X{d}") for d in range(1, 7)]
    wiersze += [_mecz(f"2024-01-{d:02d}", "B", f"Y{d}", liga="L2") for d in range(1, 9)]
    wiersze.append(_mecz("2024-02-01", "A", "B"))
    c = zbuduj_cechy(_ramka(wiersze))
    ostatni = c[(c["home"] == "A") & (c["away"] == "B")].iloc[0]
    # A: 6 meczow w L1 (>=5) -> nie beniaminek. B: 0 w L1 -> beniaminek.
    assert ostatni["roznica_nowosci"] == pytest.approx(0.0 - 1.0)


def test_beniaminek_zapomina_mecze_starsze_niz_rok():
    wiersze = [_mecz(f"2020-01-{d:02d}", "A", f"X{d}", sezon="2020") for d in range(1, 9)]
    wiersze.append(_mecz("2024-06-01", "A", "B"))
    c = zbuduj_cechy(_ramka(wiersze))
    ostatni = c[(c["home"] == "A") & (c["away"] == "B")].iloc[0]
    # 8 meczow A, ale wszystkie sprzed 4 lat -> okno 365D puste -> beniaminek.
    assert ostatni["roznica_nowosci"] == pytest.approx(1.0 - 1.0)


def test_glebokosc_sezonu_liczy_mecze_juz_rozegrane_w_tym_sezonie():
    """A ma za sobą 2 mecze sezonu, B zero → średnia 1, po skali /38."""
    df = _ramka([
        _mecz("2024-01-01", "A", "X"),
        _mecz("2024-01-08", "A", "Y"),
        _mecz("2024-01-15", "A", "B"),
    ])
    c = zbuduj_cechy(df)
    assert c.iloc[2]["glebokosc_sezonu"] == pytest.approx((2 + 0) / 2 / 38)


def test_glebokosc_zeruje_sie_na_nowym_sezonie():
    wiersze = [_mecz(f"2023-0{m}-01", "A", f"X{m}", sezon="2023") for m in (1, 2, 3)]
    wiersze.append(_mecz("2024-01-01", "A", "B", sezon="2024"))
    c = zbuduj_cechy(_ramka(wiersze))
    ostatni = c[(c["home"] == "A") & (c["away"] == "B")].iloc[0]
    assert ostatni["glebokosc_sezonu"] == pytest.approx(0.0)


def test_ZADNA_cecha_nie_widzi_przyszlosci():
    """Najważniejszy test w tym pliku.

    Cechy meczu policzone na pełnej historii MUSZĄ być identyczne co do bitu
    z policzonymi na historii uciętej tuż za tym meczem. Nierówność znaczy
    lookahead, czyli pomiar, który wygląda dobrze i jest bezwartościowy —
    a walk-forward, na którym stoi ten projekt, istnieje właśnie po to.
    """
    wiersze = []
    for i in range(1, 25):
        wiersze.append(_mecz(f"2024-{1 + i // 10}-{1 + i % 10:02d}",
                             f"T{i % 5}", f"T{(i + 2) % 5}"))
    pelne = zbuduj_cechy(_ramka(wiersze))
    ciete = zbuduj_cechy(_ramka(wiersze[:15]))

    kolumny = ["roznica_odpoczynku", "min_odpoczynek", "roznica_zageszczenia",
               "roznica_nowosci", "glebokosc_sezonu"]
    wspolne = pelne.merge(ciete, on=["league", "match_date", "home", "away"],
                          suffixes=("_p", "_c"))
    assert len(wspolne) >= 15
    for kol in kolumny:
        pd.testing.assert_series_equal(
            wspolne[f"{kol}_p"], wspolne[f"{kol}_c"],
            check_names=False, obj=f"cecha {kol} widzi przyszlosc")


def test_gospodarz_i_gosc_nie_zamieniaja_sie_miejscami():
    """Odwrócenie gospodarza z gościem musi odwrócić znak każdej różnicy."""
    baza = [
        _mecz("2024-01-01", "A", "Z"),
        _mecz("2024-01-02", "A", "Z"),
        _mecz("2024-01-09", "B", "Z"),
    ]
    prosto = zbuduj_cechy(_ramka(baza + [_mecz("2024-01-12", "A", "B")]))
    odwrot = zbuduj_cechy(_ramka(baza + [_mecz("2024-01-12", "B", "A")]))
    for kol in ("roznica_odpoczynku", "roznica_zageszczenia", "roznica_nowosci"):
        assert prosto.iloc[3][kol] == pytest.approx(-odwrot.iloc[3][kol]), kol
    # Cechy bezkierunkowe zostaja bez zmiany.
    assert prosto.iloc[3]["min_odpoczynek"] == odwrot.iloc[3]["min_odpoczynek"]
    assert prosto.iloc[3]["glebokosc_sezonu"] == odwrot.iloc[3]["glebokosc_sezonu"]


def test_jeden_wiersz_wyjscia_na_jeden_mecz_wejscia():
    """Merge po (rid, team) potrafi zdublować wiersze — wtedy cały pomiar
    liczyłby część meczów dwa razy, a `sparowana_roznica` dostałaby złe n."""
    wiersze = [_mecz(f"2024-01-{d:02d}", f"T{d % 4}", f"T{(d + 1) % 4}")
               for d in range(1, 20)]
    df = _ramka(wiersze)
    c = zbuduj_cechy(df)
    assert len(c) == len(df)
    assert not c.duplicated(subset=["league", "match_date", "home", "away"]).any()


# ─────────────── waznosc samego pomiaru, nie tylko cech ──────────────────────
#
# Wynik zerowy z zepsutego kodu wyglada identycznie jak wynik zerowy z braku
# sygnalu. Te dwa testy odrozniaja jedno od drugiego: pomiar dostaje dane,
# w ktorych odpowiedz jest znana z konstrukcji.

import numpy as np  # noqa: E402

from cechy_darmowe import zmierz  # noqa: E402

_BAZA = np.array([0.45, 0.27, 0.28])


def _syntetyczne(efekt: float, ziarno: int, n: int = 14000) -> pd.DataFrame:
    """Mecze o znanym rozkładzie. `efekt` = ile cecha naprawdę przesuwa wynik.

    Źródło `model` raportuje ZAWSZE rozkład bazowy, czyli z definicji nie wie
    o cesze. Przy `efekt`>0 informacja w cesze istnieje i pomiar ma ją znaleźć;
    przy `efekt`=0 nie istnieje i pomiar ma jej NIE znaleźć.
    """
    rng = np.random.default_rng(ziarno)
    x = rng.normal(size=n)
    logity = np.log(_BAZA)[None, :] + np.column_stack(
        [efekt * x, np.zeros(n), -efekt * x])
    p = np.exp(logity)
    p /= p.sum(axis=1, keepdims=True)
    y = np.array([rng.choice(3, p=wiersz) for wiersz in p])
    daty = pd.date_range("2020-01-01", periods=n, freq="4h")
    return pd.DataFrame({
        "league": "L1",
        "match_date": daty.astype(str).str[:10],
        "home": "A", "away": "B",
        "actual_res": pd.Series(y).map({0: "H", 1: "D", 2: "A"}),
        "pw": _BAZA[0] * 100, "pr": _BAZA[1] * 100, "pp": _BAZA[2] * 100,
        "cecha": x,
    })


def test_pomiar_znajduje_wszczepiony_sygnal():
    w = zmierz(_syntetyczne(efekt=0.35, ziarno=7), "model", "cecha")
    assert w is not None
    assert w["logloss"]["z"] > 5, f"nie wykryl realnego efektu: z={w['logloss']['z']}"
    assert w["logloss"]["roznica"] > 0
    assert w["brier"]["z"] > 0, "log-loss i Brier wskazuja przeciwne kierunki"


def test_pomiar_nie_znajduje_sygnalu_w_szumie():
    w = zmierz(_syntetyczne(efekt=0.0, ziarno=7), "model", "cecha")
    assert w is not None
    assert abs(w["logloss"]["z"]) < 2.5, f"halas udaje sygnal: z={w['logloss']['z']}"
