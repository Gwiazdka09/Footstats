"""test_normalize_kolizje.py — kluby z tej samej miejscowosci nie moga sie zlewac.

PO CO (2026-07-31): `normalize_team_name` traktowalo `United`/`City`/`Town`/
`Rovers`/`Wanderers` jak szum i obcinalo je z konca nazwy. Efekt:

    Manchester United -> "manchester"  ┐  team_similarity = 1.00
    Manchester City   -> "manchester"  ┘
    Dundee United     -> "dundee"      ┐  team_similarity = 1.00
    Dundee FC         -> "dundee"      ┘

Prog dopasowania w rozliczeniach to 0.6 (`evening_agent.py:87`), wiec wynik
JEDNEGO meczu mogl rozliczyc kupon na DRUGI mecz. Ratowala nas tylko punktacja
parowa (srednia z gospodarza i goscia) — czyli przypadek, nie zabezpieczenie.

To bylo utrwalone w testach (`test_removes_united_suffix` asertowal
"manchester"), dlatego przezylo tak dlugo.

Zasada po naprawie: te same tokeny bazowe + ROZNE czlony odrozniajace
= rozne kluby. Fail-closed: lepiej nie rozliczyc i zauwazyc, niz rozliczyc zle.
"""
from __future__ import annotations

import pytest

from footstats.utils.normalize import normalize_team_name, team_similarity

# Prog uzywany przez warstwe rozliczen (evening_agent.py:87).
PROG_ROZLICZEN = 0.6


# ── nazwy nie moga sie zlewac ───────────────────────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("Manchester United", "Manchester City"),
    ("Dundee United", "Dundee FC"),
    ("Newcastle United", "Newcastle"),
    ("Bolton Wanderers", "Bolton"),
    ("Cardiff City", "Cardiff"),
    ("Ipswich Town", "Ipswich"),
])
def test_rozne_kluby_maja_rozna_normalizacje(a, b):
    assert normalize_team_name(a) != normalize_team_name(b), (
        f"{a!r} i {b!r} normalizuja sie do tego samego"
    )


@pytest.mark.parametrize("a,b", [
    ("Manchester United", "Manchester City"),
    ("Dundee United", "Dundee FC"),
    ("Bolton Wanderers", "Bolton"),
    ("Cardiff City", "Cardiff"),
])
def test_rozne_kluby_ponizej_progu_rozliczen(a, b):
    """Ponizej 0.6 — warstwa rozliczen ich nie pomyli."""
    assert team_similarity(a, b) < PROG_ROZLICZEN, (
        f"{a!r} vs {b!r} = {team_similarity(a, b):.2f} — powyzej progu rozliczen"
    )


def test_dwa_kluby_dundee_w_tej_samej_lidze():
    """Konkretny przypadek z kolejki 31.07-03.08: oba Dundee graja w SPL."""
    assert team_similarity("Dundee United", "Dundee FC") < PROG_ROZLICZEN


# ── legalne warianty tej samej nazwy nadal sie dopasowuja ───────────────────

@pytest.mark.parametrize("a,b", [
    ("Manchester United", "Man United"),
    ("Manchester City", "Man City"),
    ("Dundee United", "Dundee Utd"),
    ("Legia Warszawa", "Legia"),
    ("Jagiellonia Białystok", "Jagiellonia"),
    ("Raków Częstochowa", "Rakow"),
])
def test_warianty_tej_samej_nazwy_dopasowane(a, b):
    assert team_similarity(a, b) >= PROG_ROZLICZEN, (
        f"{a!r} vs {b!r} = {team_similarity(a, b):.2f} — zgubione dopasowanie"
    )


def test_identyczna_nazwa_to_jeden():
    assert team_similarity("Legia Warszawa", "Legia Warszawa") == 1.0


def test_rozne_wielkosci_liter_i_diakrytyki():
    assert team_similarity("RAKÓW CZĘSTOCHOWA", "rakow czestochowa") == 1.0


# ── sufiksy czysto szumowe nadal obcinane ───────────────────────────────────

@pytest.mark.parametrize("nazwa,oczekiwane", [
    ("Arsenal FC", "arsenal"),
    ("Bayern Munchen SV", "bayern munchen"),
    ("Malmo FF", "malmo ff"),          # FF nie jest na liscie — zostaje
])
def test_szumowe_sufiksy_obcinane(nazwa, oczekiwane):
    assert normalize_team_name(nazwa) == oczekiwane


def test_prefiks_fc_nadal_obcinany():
    assert normalize_team_name("FC Barcelona") == "barcelona"


# ── caly zestaw druzyn z danych historycznych ───────────────────────────────

def test_zadne_dwie_rozne_druzyny_z_datasetu_sie_nie_zlewaja():
    """Kontrola na REALNYCH nazwach: 10 lig, ~250 klubow.

    Sprawdza, ze po normalizacji zadne dwie rozne nazwy nie daja tego samego
    wyniku. Bez tego kazde dodanie sufiksu do listy moze cicho skleic kluby.
    """
    from pathlib import Path

    parquet = Path(__file__).resolve().parents[1] / "data" / "hist_cache" / "full_dataset.parquet"
    if not parquet.exists():
        pytest.skip("brak full_dataset.parquet")

    # CI nie instaluje silnika parquet (pyarrow/fastparquet nie sa w [dev,api,ai]).
    # Bez tego guardu test wywalal sie ImportError zamiast uczciwie sie pominac.
    pytest.importorskip("pyarrow", reason="brak silnika parquet (pyarrow)")

    import pandas as pd
    df = pd.read_parquet(parquet, columns=["home", "away"])
    druzyny = sorted(set(df["home"]) | set(df["away"]))

    wg_normy: dict[str, list[str]] = {}
    for d in druzyny:
        wg_normy.setdefault(normalize_team_name(d), []).append(d)

    kolizje = {k: v for k, v in wg_normy.items() if len(v) > 1}
    assert not kolizje, f"rozne kluby o tej samej normalizacji: {kolizje}"


# ── aliasy: plik NIE moze przeslaniac defaults ──────────────────────────────

def test_stary_plik_mapowan_nie_przeslania_nowych_defaults(tmp_path, monkeypatch):
    """REGRESJA (2026-07-31, znaleziona przez CI).

    `_seed_mappings_file` tworzy team_mappings.json TYLKO gdy plik nie istnieje,
    a `_load_mappings` czytal wylacznie ten plik. Skutek: kazdy alias dopisany
    do `_DEFAULT_MAPPINGS` byl MARTWY na maszynie, ktora plik juz miala —
    poprawka w kodzie nie zmieniala niczego po wdrozeniu.

    Do tego plik nie jest w repo ani w obrazie Dockera, wiec kazde srodowisko
    dopasowywalo nazwy inaczej: CI (swiezy seed) rozrozniało Manchester United
    od City, lokalna maszyna ze starym plikiem — nie. Ten sam kod, dwa zachowania.
    """
    import footstats.utils.normalize as N

    stary = tmp_path / "team_mappings.json"
    stary.write_text('{"barca": "barcelona"}', encoding="utf-8")   # 1 wpis, bez manchester
    monkeypatch.setattr(N, "_MAPPINGS_PATH", stary)
    N.reload_mappings()
    try:
        mapowania = N._load_mappings()
        assert "barca" in mapowania, "wpis z pliku zgubiony"
        assert "manchester united" in mapowania, "defaults przeslonięte przez stary plik"
    finally:
        N.reload_mappings()


def test_plik_nadpisuje_defaults_dla_tego_samego_klucza(tmp_path, monkeypatch):
    """Plik sluzy do RECZNYCH nadpisan — dla wspolnego klucza wygrywa on."""
    import footstats.utils.normalize as N

    plik = tmp_path / "team_mappings.json"
    plik.write_text('{"barca": "moja wlasna nazwa"}', encoding="utf-8")
    monkeypatch.setattr(N, "_MAPPINGS_PATH", plik)
    N.reload_mappings()
    try:
        assert N._load_mappings()["barca"] == "moja wlasna nazwa"
    finally:
        N.reload_mappings()


def test_uszkodzony_plik_nie_kasuje_defaults(tmp_path, monkeypatch):
    import footstats.utils.normalize as N

    plik = tmp_path / "team_mappings.json"
    plik.write_text("{niepoprawny", encoding="utf-8")
    monkeypatch.setattr(N, "_MAPPINGS_PATH", plik)
    N.reload_mappings()
    try:
        assert "manchester united" in N._load_mappings()
    finally:
        N.reload_mappings()
