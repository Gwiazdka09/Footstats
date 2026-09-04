"""Jedna cena nie odpowiada na dwa różne pytania.

Dataset niósł dotąd wyłącznie `AvgC*` — ŚREDNIĄ bukmacherów. Tymczasem te same
pliki, które już pobieramy, zawierają dwie inne ceny, i każda odpowiada na inne
pytanie projektu:

    PSC*   Pinnacle closing   „czy w ogóle mamy INFORMACJĘ"
                              Najostrzejsza cena na rynku. Pokonanie średniej
                              książek nie znaczy nic — pokonanie zamknięcia
                              Pinnacle znaczy wszystko.

    MaxC*  najlepszy kurs     „czy da się na tym ZAROBIĆ"
                              Po tej cenie realnie się stawia. EV liczone po
                              średniej odpowiada na pytanie, którego nikt nie
                              zadaje, bo nikt nie obstawia po średniej.

Pomiar z 04.09 (n=120 351, 39 lig na 39 przeciw modelowi) porównywał model ze
średnią. Kierunku wyniku to nie zmienia, ale ZANIŻA deficyt: prawdziwy dystans
do ostrej ceny jest co najmniej taki, prawdopodobnie większy.

CZEGO TU CELOWO NIE MA: mieszania `BbMx*` z `MaxC*` w jednej kolumnie. Betbrain
(do sezonu 1819) to maksimum z nieokreślonego momentu, `MaxC` (od 1920) to
maksimum NA ZAMKNIĘCIU. Jedna kolumna zmieniająca znaczenie w połowie historii
psułaby każdy pomiar dzielony po epoce — i to po cichu, bo liczby dalej
wyglądałyby sensownie. Starsze sezony zostają z NaN i to jest uczciwsze.

Z tego samego powodu `PSC*` nie cofa się do `PS*`: to cena OTWARCIA, inny
moment i inna ostrość.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.data import historical_loader as hl


def _csv(naglowek: str, wiersze: list[str]) -> bytes:
    return ("\n".join([naglowek, *wiersze]) + "\n").encode()


@pytest.fixture()
def bez_sieci(monkeypatch, tmp_path):
    """Podmienia `_get` na treść ustawianą per test."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    stan = {"tresc": b""}

    def _fake(url, timeout=30):
        return stan["tresc"]

    monkeypatch.setattr(hl, "_get", _fake)
    return stan


# ── nowy format (ligi pozaeuropejskie) — tylko 1X2, bez O/U u źródła ────────

_NAG_NEW = ("Country,League,Season,Date,Home,Away,HG,AG,Res,"
            "PSH,PSD,PSA,PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA")
_WIERSZ_NEW = ("Poland,Ekstraklasa,2025,01/03/2025,Legia,Lech,2,1,H,"
               "2.00,3.30,3.70,2.05,3.35,3.75,2.20,3.60,4.10,2.10,3.40,3.60")


def test_nowy_format_wyciaga_pinnacle_closing(bez_sieci):
    bez_sieci["tresc"] = _csv(_NAG_NEW, [_WIERSZ_NEW])
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert df.loc[0, "odds_h_pinn"] == 2.05
    assert df.loc[0, "odds_d_pinn"] == 3.35
    assert df.loc[0, "odds_a_pinn"] == 3.75


def test_nowy_format_wyciaga_najlepszy_kurs(bez_sieci):
    bez_sieci["tresc"] = _csv(_NAG_NEW, [_WIERSZ_NEW])
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert df.loc[0, "odds_h_max"] == 2.20
    assert df.loc[0, "odds_a_max"] == 4.10


def test_kurs_zwykly_zostaje_srednia(bez_sieci):
    """Nowe kolumny są DODATKIEM — `odds_h` nie może się po cichu zmienić.

    Cały pomiar z 04.09 i wszystkie wcześniejsze liczą z `odds_h`. Podmiana
    znaczenia tej kolumny unieważniłaby porównania z przeszłością.
    """
    bez_sieci["tresc"] = _csv(_NAG_NEW, [_WIERSZ_NEW])
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert df.loc[0, "odds_h"] == 2.10


def test_pinnacle_nie_cofa_sie_do_ceny_otwarcia(bez_sieci):
    """Brak `PSC*` ma dać NaN, nie kurs otwarcia `PS*`.

    `PS` i `PSC` to ta sama książka w dwóch różnych momentach. Podstawienie
    otwarcia pod kolumnę „closing" dałoby liczbę, która wygląda dobrze i mierzy
    co innego — a ostrość ceny rośnie właśnie do zamknięcia.
    """
    nag = "Country,League,Season,Date,Home,Away,HG,AG,Res,PSH,PSD,PSA,AvgCH,AvgCD,AvgCA"
    bez_sieci["tresc"] = _csv(nag, [
        "Poland,Ekstraklasa,2025,01/03/2025,Legia,Lech,2,1,H,2.00,3.30,3.70,2.10,3.40,3.60"
    ])
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert pd.isna(df.loc[0, "odds_h_pinn"])
    assert df.loc[0, "odds_h"] == 2.10, "zwykly kurs ma dalej dzialac"


def test_betbrain_nie_podszywa_sie_pod_najlepszy_kurs(bez_sieci):
    """`BbMx*` to maksimum z innego momentu niz `MaxC*` — nie wolno ich zlac."""
    nag = ("Country,League,Season,Date,Home,Away,HG,AG,Res,"
           "BbMxH,BbMxD,BbMxA,AvgCH,AvgCD,AvgCA")
    bez_sieci["tresc"] = _csv(nag, [
        "Poland,Ekstraklasa,2017,01/03/2017,Legia,Lech,2,1,H,2.30,3.70,4.20,2.10,3.40,3.60"
    ])
    df = hl._download_fdco_new("POL")
    assert df is not None
    assert pd.isna(df.loc[0, "odds_h_max"])


# ── format sezonowy (ligi europejskie) — 1X2 ORAZ Over/Under ────────────────

_NAG_SEZ = ("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,"
            "PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA,AvgH,AvgD,AvgA,"
            "PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,Avg>2.5,Avg<2.5")
_WIERSZ_SEZ = ("E0,01/03/2025,Arsenal,Chelsea,2,1,H,"
               "1.85,3.60,4.20,1.95,3.80,4.50,1.88,3.65,4.25,"
               "1.90,1.95,2.00,2.05,1.92,1.96")


def test_format_sezonowy_wyciaga_obie_ceny_1x2(bez_sieci):
    bez_sieci["tresc"] = _csv(_NAG_SEZ, [_WIERSZ_SEZ])
    df = hl._download_fdco_season("E0", "2425")
    assert df is not None
    assert df.loc[0, "odds_h_pinn"] == 1.85
    assert df.loc[0, "odds_h_max"] == 1.95
    assert df.loc[0, "odds_h"] == 1.88, "zwykly kurs dalej ze sredniej"


def test_format_sezonowy_wyciaga_obie_ceny_over_under(bez_sieci):
    """Rynki golowe to 18 z 20 kuponow z 15.08 — tam cena liczy sie najbardziej."""
    bez_sieci["tresc"] = _csv(_NAG_SEZ, [_WIERSZ_SEZ])
    df = hl._download_fdco_season("E0", "2425")
    assert df is not None
    assert df.loc[0, "odds_over25_pinn"] == 1.90
    assert df.loc[0, "odds_under25_pinn"] == 1.95
    assert df.loc[0, "odds_over25_max"] == 2.00
    assert df.loc[0, "odds_under25_max"] == 2.05


def test_stary_sezon_bez_ostrych_cen_nie_wywraca_parsowania(bez_sieci):
    """Sezony do 1819 nie maja ani `MaxC`, ani `PC>2.5` — to normalny stan."""
    nag = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,AvgH,AvgD,AvgA,BbAv>2.5,BbAv<2.5"
    bez_sieci["tresc"] = _csv(nag, [
        "E0,01/03/2017,Arsenal,Chelsea,2,1,H,1.88,3.65,4.25,1.92,1.96"
    ])
    df = hl._download_fdco_season("E0", "1617")
    assert df is not None
    assert len(df) == 1
    for kol in ("odds_h_pinn", "odds_h_max", "odds_over25_pinn", "odds_over25_max"):
        assert pd.isna(df.loc[0, kol]), f"{kol} powinno byc puste"


# ── kolumny musza dojechac do ramki modelu i pod straznika ──────────────────

@pytest.mark.parametrize("kolumna", [
    "odds_h_pinn", "odds_d_pinn", "odds_a_pinn",
    "odds_h_max", "odds_d_max", "odds_a_max",
    "odds_over25_pinn", "odds_under25_pinn",
    "odds_over25_max", "odds_under25_max",
])
def test_nowe_kolumny_sa_opcjonalne_w_schemacie(kolumna):
    """Parquet na dysku jest starszy — bez tego `load_cached` wywalilby sie na
    kazdym odczycie do czasu pelnego ponownego pobrania."""
    assert kolumna in hl.KOLUMNY_OPCJONALNE


def test_straznik_pilnuje_ostrej_ceny():
    """Pinnacle to benchmark KAZDEGO przyszlego pomiaru przewagi.

    Ciche zniknięcie tej kolumny u źródła unieważniłoby porównania, nie dając
    ani jednego objawu — dokładnie jak incydent JPN z 03.09.
    """
    assert "odds_h_pinn" in hl._KOLUMNY_PILNOWANE
