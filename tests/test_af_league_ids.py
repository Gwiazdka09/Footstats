"""Mapa lig datasetu na id w API-Football — wybrana ręcznie, pilnowana testem.

Automatyczne dopasowanie po nazwie NIE może tego zrobić i to nie jest ostrożność
teoretyczna. Zmierzone 2026-09-03:

  * dataset mówi `ROU-Superliga`, API mówi `Liga I`;
  * dataset mówi `USA-MLS`, API mówi `Major League Soccer`;
  * `/leagues?country=Netherlands` oddaje obok siebie `Eredivisie` (88),
    `Eerste Divisie` (89) i `Eredivisie Women` (91).

Dwa pierwsze przypadki automat by przegapił, trzeci — źle rozstrzygnął. Skutek
błędu jest CICHY: statystyki z innych rozgrywek wlądowałyby w mecze, których nie
dotyczą, a λ zepsułaby się bez jednego wyjątku.

Test pilnuje trzech niezmienników: mapa jest kompletna wobec lig bez strzałów,
id się nie powtarzają, a każda liga z mapy istnieje w datasecie.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLIK = ROOT / "data" / "af_league_ids.json"

# Poniżej tego pokrycia `hst` uznajemy ligę za „bez strzałów". Nie zero, bo
# ENG-National League ma śladowe 1.1% z pojedynczych kolejek — to nie jest
# pokrycie, na którym da się liczyć rating.
PROG_BEZ_STRZALOW = 0.05


def _surowa() -> dict:
    return json.loads(PLIK.read_text(encoding="utf-8"))


def _mapa() -> dict:
    return {k: v for k, v in _surowa().items() if not k.startswith("_")}


def test_plik_istnieje_i_jest_jsonem() -> None:
    assert PLIK.exists()
    assert isinstance(_surowa(), dict)


def test_kazdy_wpis_ma_komplet_pol() -> None:
    for liga, wpis in _mapa().items():
        assert isinstance(wpis.get("af_league_id"), int), liga
        assert wpis.get("nazwa_af"), liga
        assert wpis.get("kraj"), liga


def test_id_lig_sa_unikalne() -> None:
    """Dwie ligi datasetu na jedno id AF = statystyki z cudzych rozgrywek."""
    ids = [w["af_league_id"] for w in _mapa().values()]
    powtorzone = {i for i in ids if ids.count(i) > 1}
    assert not powtorzone, f"to samo id przypisane wielu ligom: {powtorzone}"


def test_ligi_z_mapy_istnieja_w_datasecie() -> None:
    """Literówka w kluczu dałaby ligę, której backfill nigdy nie znajdzie."""
    from footstats.data.historical_loader import load_cached

    try:
        df = load_cached(z_af=False)
    except FileNotFoundError:
        pytest.skip("brak full_dataset.parquet w tym srodowisku")

    znane = set(df["league"].dropna().unique())
    obce = [liga for liga in _mapa() if liga not in znane]
    assert not obce, f"ligi spoza datasetu: {obce}"


def test_kazda_liga_bez_strzalow_ma_id_albo_jawne_wykluczenie() -> None:
    """Nic nie ma prawa wypaść po cichu.

    Liga bez strzałów, która nie jest ani w mapie, ani na liście wykluczeń, to
    liga, o której po prostu zapomniano — i nikt się o tym nie dowie, bo brak
    statystyk wygląda dokładnie tak samo jak brak backfillu.
    """
    from footstats.data.historical_loader import load_cached

    try:
        df = load_cached(z_af=False)
    except FileNotFoundError:
        pytest.skip("brak full_dataset.parquet w tym srodowisku")

    pokrycie = df.groupby("league")["hst"].apply(lambda s: s.notna().mean())
    bez_strzalow = {liga for liga, p in pokrycie.items() if p < PROG_BEZ_STRZALOW}

    mapa = _mapa()
    wykluczone = set(_surowa().get("_bez_statystyk_w_af", {})) - {"_komentarz"}
    zapomniane = bez_strzalow - set(mapa) - wykluczone

    assert not zapomniane, (
        f"ligi bez strzalow, bez id i bez jawnego wykluczenia: {sorted(zapomniane)}"
    )


def test_wykluczone_ligi_nie_sa_jednoczesnie_w_mapie() -> None:
    """Sprzeczny wpis znaczy, że ktoś dopisał ligę, nie usuwając wykluczenia."""
    wykluczone = set(_surowa().get("_bez_statystyk_w_af", {})) - {"_komentarz"}
    kolizja = wykluczone & set(_mapa())
    assert not kolizja, f"liga jednoczesnie wykluczona i w mapie: {kolizja}"
