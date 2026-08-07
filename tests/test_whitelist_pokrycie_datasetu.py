"""Każda liga z datasetu musi przechodzić whitelistę.

BUG (2026-08-07): dataset zawiera `BEL-First Division A` (2805 meczów) i
`SCO-Premiership` (2231), ale `LIGI_WHITELIST` znała belgijską ligę wyłącznie
jako "Jupiler Pro League", a źródło predykcji nazywa ją "Pro League" — i nie
znała szkockiej w ogóle. Belgijski mecz przeszedł przez produkcyjny przebieg
07.08 i wypadł na samej nazwie, mimo pełnej historii do policzenia λ.

To strata przez literówkę w dwóch zbiorach, nie decyzja o strategii: liga bez
pokrycia w danych może sobie zostać (Poisson po prostu jej nie policzy,
a `model_source` odróżni takie predykcje), ale liga Z pokryciem odrzucona
przez zapis nazwy to czyste marnowanie danych, które już mamy.

Test wiąże oba zbiory na stałe: nowa liga w parquecie bez wpisu w aliasach
kończy się czerwonym testem, a nie cichym odrzucaniem meczów.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from footstats.config import LIGI_DATASET_ALIASY, LIGI_WHITELIST
from footstats.utils.normalize import normalize_team_name

PARQUET = Path(__file__).resolve().parents[1] / "data" / "hist_cache" / "full_dataset.parquet"


def _ligi_datasetu() -> set[str]:
    if not PARQUET.exists():
        pytest.skip("brak full_dataset.parquet — nie ma czego weryfikowac")
    return set(pd.read_parquet(PARQUET, columns=["league"])["league"].unique())


def test_kazda_liga_datasetu_ma_aliasy() -> None:
    brakuje = sorted(_ligi_datasetu() - set(LIGI_DATASET_ALIASY))
    assert not brakuje, (
        "ligi w datasecie bez wpisu w LIGI_DATASET_ALIASY (Poisson ma dla nich "
        f"dane, ale filtr moze je odrzucic): {brakuje}"
    )


def test_aliasy_nie_opisuja_lig_spoza_datasetu() -> None:
    """Alias bez danych obiecuje Poissona, którego nie ma — mylące."""
    zbedne = sorted(set(LIGI_DATASET_ALIASY) - _ligi_datasetu())
    assert not zbedne, f"aliasy dla lig nieobecnych w datasecie: {zbedne}"


def test_wszystkie_aliasy_przechodza_whiteliste() -> None:
    wl = {normalize_team_name(x) for x in LIGI_WHITELIST}
    odrzucone = [
        f"{liga} -> {alias!r}"
        for liga, aliasy in LIGI_DATASET_ALIASY.items()
        for alias in aliasy
        if normalize_team_name(alias) not in wl
    ]
    assert not odrzucone, "aliasy poza whitelista: " + "; ".join(odrzucone)


def test_belgia_pod_nazwa_ze_zrodla() -> None:
    """Dokładnie nazwa, na której produkcja odrzuciła mecz 07.08."""
    wl = {normalize_team_name(x) for x in LIGI_WHITELIST}
    assert normalize_team_name("Pro League") in wl


def test_szkocja_pod_nazwa_ze_zrodla() -> None:
    wl = {normalize_team_name(x) for x in LIGI_WHITELIST}
    assert normalize_team_name("Premiership") in wl


def test_kazda_liga_ma_co_najmniej_jeden_alias() -> None:
    puste = [lg for lg, aliasy in LIGI_DATASET_ALIASY.items() if not aliasy]
    assert not puste, f"ligi z pusta lista aliasow: {puste}"


def test_nazwa_z_datasetu_tez_jest_aliasem() -> None:
    """Predykcja bywa opisana pełną nazwą z datasetu (np. z walk-forwardu)."""
    braki = [
        lg for lg, aliasy in LIGI_DATASET_ALIASY.items()
        if normalize_team_name(lg) not in {normalize_team_name(a) for a in aliasy}
    ]
    assert not braki, f"pelna nazwa datasetu nie jest wsrod aliasow: {braki}"
