"""Cotygodniowe odświeżanie datasetu nie może mieć własnej, słabszej kopii strażnika.

`.github/workflows/dataset_refresh.yml` uruchamia `download_all()` w poniedziałki
04:30 UTC na czystym runnerze i otwiera PR z nowym `full_dataset.parquet`. Do
2026-09-03 miał w kroku „Refresh dataset" swój własny warunek:

    if n_przed and n_po < n_przed * 0.98:
        sys.exit(f"BLAD: dataset skurczyl sie {n_przed} -> {n_po}")

czyli patrzył wyłącznie na LICZBĘ WIERSZY. Incydent z tego samego dnia
przeszedłby przez niego bez mrugnięcia: źródło dołożyło w `new/JPN.csv` prawie
puste kolumny B365C*, parser wziął je zamiast pełnych AvgC*, Japonia straciła
kursy w 4353 meczach — a wierszy w całym zbiorze PRZYBYŁO (139 102 → 140 148).
Warunek był spełniony, PR wyglądałby zdrowo, a dataset pojechałby do obrazów
Cloud Run z dziurą, której nikt nie szuka.

Reguła „nowy zbiór nie może być uboższy" ma jedno miejsce: `regresje_datasetu`
wołane wewnątrz `download_all()`, porównujące PER LIGA i także pokrycie kolumn.
Druga kopia w YAML-u to trzecia okazja tego dnia, żeby jedna reguła w kilku
miejscach rozjechała się po cichu.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "dataset_refresh.yml"


def _tresc() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_istnieje() -> None:
    assert WORKFLOW.exists(), (
        "bez tego zadania odswiezenie datasetu zalezy od tego, czy ktos sobie"
        " przypomni — 2026-08-07 dane urywaly sie na 2026-05-24"
    )


def test_workflow_wola_download_all() -> None:
    """Strażnik działa TYLKO wtedy, gdy odświeżenie idzie przez `download_all()`."""
    assert "download_all()" in _tresc()


def test_workflow_nie_ma_wlasnego_progu_na_liczbie_wierszy() -> None:
    """Żadnego `len(po) < len(przed) * x` w YAML-u — to jest praca `download_all`."""
    tresc = _tresc()
    wzorce = [
        r"n_po\s*<\s*n_przed",
        r"len\(po\)\s*<\s*len\(przed\)",
        r"skurczyl\s+sie",
    ]
    znalezione = [w for w in wzorce if re.search(w, tresc)]
    assert not znalezione, (
        f"workflow ma wlasna kopie straznika ({znalezione}). Reguly nie duplikujemy:"
        " wersja na liczbie wierszy PRZEPUSCILA incydent JPN, bo wierszy przybylo."
    )


def test_straznik_pilnuje_pokrycia_kolumn_nie_tylko_wierszy() -> None:
    """Ta właściwość odróżnia obecnego strażnika od tego, który zawiódł."""
    from footstats.data.historical_loader import _KOLUMNY_PILNOWANE

    assert "odds_h" in _KOLUMNY_PILNOWANE, (
        "bez kursow walk-forward traci ramie RYNKOWE (wf_harness.predict_one je"
        " devigauje) i cicho degraduje sie do czystego Poissona"
    )
    assert "hst" in _KOLUMNY_PILNOWANE, (
        "strzaly celne wchodza do lambda przez form.sily_ligowe (WAGA_STRZALOW)"
    )


def test_download_all_odmawia_zapisu_przy_regresji() -> None:
    """Kontrakt, na którym opiera się usunięcie warunku z YAML-a.

    Gdyby `download_all` przestało rzucać, workflow milczkiem wypuściłby uboższy
    dataset — a warunku, który by to złapał, już tam nie ma.
    """
    import inspect

    from footstats.data import historical_loader as hl

    zrodlo = inspect.getsource(hl.download_all)
    assert "regresje_datasetu" in zrodlo
    assert "raise ValueError" in zrodlo
