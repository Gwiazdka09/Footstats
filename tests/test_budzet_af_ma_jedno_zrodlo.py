"""Limit budżetu API-Football musi mieć JEDNO źródło.

ZNALEZIONE 2026-09-03, w przebiegu rozliczeń na sucho. Log przeczył sam sobie:

    AF req uzyto: 3/7500 | pozostalo ~96

Trzy z siedmiu i pół tysiąca zużyte, a „pozostało 96". Przyczyna: `AF_BUDGET_DAILY`
w `utils/cache.py` zostało podniesione ze 100 na 7500 (plan Pro), ale
`bezpieczny_budget_use` w `utils/logging.py` — funkcja, która ten budżet FAKTYCZNIE
egzekwuje — miała własne domyślne wartości:

    def bezpieczny_budget_use(endpoint, budget_daily=100, block_threshold=5,
                              warn_threshold=20)

a `api_football._get` woła ją z samym `endpoint`. Czyli podniesienie stałej nie
zmieniało niczego na ścieżce zapytań.

SKUTEK, GDYBY TO POSZŁO NA PRODUKCJĘ: po ~95 zapytaniach dziennie `BladBudzetu`
blokuje ruch, a `_get` oddaje WYGASŁE dane z cache. Bez błędu, bez alarmu — potok
wygląda zdrowo, jadąc na wczorajszych składach i kursach. Przy 7500 dostępnych.

To ten sam kształt, który kosztował nas już kilka razy: jedna reguła zapisana
w dwóch miejscach, gdzie poprawka trafia tylko w jedno.
"""
from __future__ import annotations

import inspect

from footstats.utils.cache import (
    AF_BLOCK_THRESHOLD, AF_BUDGET_DAILY, AF_WARN_THRESHOLD,
)
from footstats.utils.logging import bezpieczny_budget_use


def test_domyslne_wartosci_nie_sa_wpisane_na_sztywno():
    """Domyślne argumenty nie mogą duplikować liczb z `cache.py`.

    Wartość wpisana literałem przeżywa zmianę planu i dławi ruch po cichu.
    """
    sygnatura = inspect.signature(bezpieczny_budget_use)
    for nazwa in ("budget_daily", "block_threshold", "warn_threshold"):
        domyslna = sygnatura.parameters[nazwa].default
        assert domyslna is None, (
            f"{nazwa} ma wpisaną wartość {domyslna!r} zamiast brać ją z"
            " `cache.AF_*` — zmiana planu jej nie ruszy"
        )


def test_budzet_liczony_wobec_wartosci_z_cache(monkeypatch, tmp_path):
    """Liczba w logu i w wyjątku ma odpowiadać realnemu limitowi planu."""
    from footstats.utils import logging as log_mod

    monkeypatch.setattr(log_mod, "katalog_cache", lambda _n: tmp_path)
    pozostalo = bezpieczny_budget_use("/fixtures")
    assert pozostalo == AF_BUDGET_DAILY - 1


def test_raport_diagnostyczny_tez_nie_ma_wlasnej_liczby():
    """`raport_diagnostyczny` liczył „pozostalo" jako `100 - uzyto`.

    Trzecia kopia tej samej reguły. Sam raport nie blokuje ruchu, ale pokazuje
    liczbę, na podstawie której człowiek ocenia, czy budżet się kończy — a
    fałszywe „zostało 96" wygląda dokładnie jak prawdziwe.
    """
    from pathlib import Path

    zrodlo = Path(inspect.getsourcefile(bezpieczny_budget_use)).read_text(encoding="utf-8")
    assert "100 - budget.get" not in zrodlo, (
        "raport diagnostyczny liczy pozostały budżet wobec wpisanej setki"
    )


def test_progi_skaluja_sie_z_budzetem():
    """Progi ostrzeżenia i blokady mają być POCHODNE budżetu, nie osobnymi liczbami.

    Przy dwóch niezależnych liczbach zmiana planu poprawia jedną i zostawia drugą:
    „zostało 20 z 7500" to nie ostrzeżenie, tylko zaokrąglenie.
    """
    assert AF_WARN_THRESHOLD > AF_BLOCK_THRESHOLD > 0
    assert AF_WARN_THRESHOLD >= AF_BUDGET_DAILY // 5
    assert AF_BLOCK_THRESHOLD >= AF_BUDGET_DAILY // 20
