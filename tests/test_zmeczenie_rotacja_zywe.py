"""Heurystyka zmęczenia musi widzieć daty w schemacie, który dostaje na produkcji.

PO CO: `HeurystaZmeczeniaRotacji.__init__` liczyło kolumnę `_dt` WYŁĄCZNIE gdy
ramka miała kolumnę `data_full`. Produkcyjna ścieżka (`quick_picks` →
`adapt_to_prod_schema`) daje `data` i `date` — `data_full` nie ma tam nigdy.
Bez `_dt` metoda `analiza` wychodziła w drugim warunku i zwracała same `False`,
czyli tagi ZMECZENIE i ROTACJA nie zapaliły się ANI RAZU (0 na 400 meczów
zmierzone 09.08.2026), a RAG nie miał z czego budować wzorców.

Sąsiednie systemy (`AnalizaH2H`) budują `_dt` z kolumny `data` — tu była po
prostu inna nazwa kolumny i nikt tego nie zauważył, bo brak tagu wygląda
identycznie jak „ten mecz nie jest zmęczony".
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core.fatigue import HeurystaZmeczeniaRotacji


def _ramka(kolumna_daty: str) -> pd.DataFrame:
    """Dwa mecze tej samej drużyny w odstępie 48 h."""
    return pd.DataFrame({
        kolumna_daty: ["2026-08-01", "2026-08-03"],
        "gospodarz": ["Legia", "Legia"],
        "goscie": ["Wisla", "Lech"],
        "gole_g": [2, 1],
        "gole_a": [0, 1],
    })


@pytest.mark.parametrize("kolumna", ["data", "data_full", "date"])
def test_zmeczenie_wykryte_niezaleznie_od_nazwy_kolumny_daty(kolumna):
    """48 h od poprzedniego meczu to zmęczenie przy domyślnym progu 72 h."""
    heur = HeurystaZmeczeniaRotacji(_ramka(kolumna))

    wynik = heur.analiza("Legia", "2026-08-03")

    assert wynik["zmeczenie"] is True, f"kolumna {kolumna}: zmeczenie nie wykryte"
    assert wynik["mnoznik_obr"] < 1.0


def test_odpoczeta_druzyna_nie_dostaje_tagu():
    """Bez tego testu fix „zapal zawsze" też przechodziłby."""
    heur = HeurystaZmeczeniaRotacji(_ramka("data"))

    wynik = heur.analiza("Legia", "2026-09-15")

    assert wynik["zmeczenie"] is False
    assert wynik["mnoznik_obr"] == 1.0


def test_rotacja_zapala_sie_gdy_jest_kolumna_rozgrywek():
    """Gałąź CL ma działać, gdy dane w ogóle niosą rodzaj rozgrywek."""
    df = pd.DataFrame({
        "data": ["2026-08-01", "2026-08-03"],
        "gospodarz": ["Legia", "Legia"],
        "goscie": ["Wisla", "Lech"],
        "competition": ["CL", "LIGA"],
    })

    wynik = HeurystaZmeczeniaRotacji(df).analiza("Legia", "2026-08-03")

    assert wynik["rotacja"] is True
    assert wynik["mnoznik_atak"] < 1.0


def test_bez_kolumny_rozgrywek_rotacja_milczy():
    """Dataset football-data nie ma pucharów — gałąź ma nie zgadywać."""
    wynik = HeurystaZmeczeniaRotacji(_ramka("data")).analiza("Legia", "2026-08-03")

    assert wynik["rotacja"] is False
    assert wynik["mnoznik_atak"] == 1.0


def test_brak_kolumny_z_data_nie_wywala_analizy():
    """Ramka bez daty ma zwrócić neutralny wynik, nie wyjątek."""
    df = pd.DataFrame({"gospodarz": ["Legia"], "goscie": ["Wisla"]})

    wynik = HeurystaZmeczeniaRotacji(df).analiza("Legia", "2026-08-03")

    assert wynik["zmeczenie"] is False
    assert wynik["rotacja"] is False


def test_dziala_na_ramce_ze_schematu_produkcyjnego():
    """Dokładnie ta ścieżka, którą idzie `quick_picks`: loader → adapter."""
    from footstats.core.wf_harness import adapt_to_prod_schema

    surowe = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-01", "2026-08-03"]),
        "league": ["POL-Ekstraklasa"] * 2,
        "home": ["Legia", "Legia"],
        "away": ["Wisla", "Lech"],
        "hg": [2, 1],
        "ag": [0, 1],
    })

    df = adapt_to_prod_schema(surowe)
    wynik = HeurystaZmeczeniaRotacji(df).analiza("Legia", "2026-08-03")

    assert wynik["zmeczenie"] is True
