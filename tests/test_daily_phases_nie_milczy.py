"""J1 — `core/daily_phases.py`: cztery handlery milczały o utracie całych podsystemów.

Kształt był identyczny w trzech miejscach:

    try:
        from footstats.core.<podsystem> import ...
    except ImportError:
        return          # <- funkcja znika na CAŁY przebieg, bez śladu w logu

To nie jest hipotetyczne. Ten sam wzorzec kosztował już dwa udokumentowane
przebiegi: brak `pyarrow` w obrazie (`load_cached()` pod `except` → cichy zjazd
z Poissona-DC na Bzzoiro-ML, patrz komentarz przy zależności w `pyproject.toml`)
oraz `quick_picks.py` z 28.08, gdzie padnięcie systemów λ zostawiało PUSTE
`factors` w całym przebiegu i nikt tego nie widział.

Te testy nie sprawdzają, że kod „obsługuje brak importu" — to robił już wcześniej.
Sprawdzają, że **mówi o tym głośno i konkretnie**: co padło i co z tego wynika.
"""
from __future__ import annotations

import builtins

import pytest

from footstats.core import daily_phases


def _bez_modulu(monkeypatch, zabroniony: str) -> None:
    """Sprawia, że import `zabroniony` (i jego podmodułów) rzuca ImportError."""
    prawdziwy = builtins.__import__

    def _import(nazwa, *a, **k):
        if nazwa == zabroniony or nazwa.startswith(zabroniony + "."):
            raise ImportError(f"brak {zabroniony} w tym obrazie")
        return prawdziwy(nazwa, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _import)


@pytest.mark.parametrize(
    ("funkcja", "zabroniony", "slad"),
    [
        ("_apply_national_lambda", "footstats.core.national_lambda", "reprezentacj"),
        ("_oblicz_roznica_modeli", "footstats.core.ensemble", "roznica_modeli"),
        ("_wzbogac_o_betbuilder", "footstats.core.bet_builder", "BetBuilder"),
    ],
)
def test_utrata_podsystemu_jest_glosna(monkeypatch, caplog, funkcja, zabroniony, slad):
    """Brak podsystemu w obrazie ma zostawić WARNING nazywający skutek,
    a nie tylko po cichu wrócić."""
    _bez_modulu(monkeypatch, zabroniony)
    wyniki = [{"gosp": "A", "gosc": "B", "liga": "Testowa"}]

    with caplog.at_level("WARNING"):
        getattr(daily_phases, funkcja)(wyniki)

    assert slad.lower() in caplog.text.lower(), (
        f"{funkcja} po utracie {zabroniony} nie powiedziala nic o skutku;"
        f" log: {caplog.text!r}"
    )


@pytest.mark.parametrize(
    ("funkcja", "zabroniony"),
    [
        ("_apply_national_lambda", "footstats.core.national_lambda"),
        ("_oblicz_roznica_modeli", "footstats.core.ensemble"),
        ("_wzbogac_o_betbuilder", "footstats.core.bet_builder"),
    ],
)
def test_utrata_podsystemu_nie_wywraca_przebiegu(monkeypatch, funkcja, zabroniony):
    """Kontrola do testu wyżej. Głośno ≠ fatalnie: przebieg ma jechać dalej
    bez tego podsystemu, inaczej zamienilibyśmy cichą degradację na awarię."""
    _bez_modulu(monkeypatch, zabroniony)
    wyniki = [{"gosp": "A", "gosc": "B", "liga": "Testowa"}]

    getattr(daily_phases, funkcja)(wyniki)  # brak wyjątku = zaliczone


def test_cisza_w_petli_formatow_dat_ZOSTAJE(tmp_path):
    """Kontrapunkt: nie każdy milczący handler jest błędem. `_zapisz_next_final_txt`
    próbuje formaty daty po kolei; nietrafiony format to stan NORMALNY, a log przy
    każdym meczu zabiłby sygnał w reszcie pliku. Ten test broni tej ciszy przed
    „poprawieniem" przy następnym przejściu po J1 — brak DOWOLNEGO dopasowania
    kończy się jawnym fallbackiem 13:30, więc informacja nie ginie."""
    daily_phases._zapisz_next_final_txt([{"data": "2026-06-26"}], katalog=tmp_path)

    assert (tmp_path / "next_final.txt").read_text(encoding="utf-8").strip() == "13:30"
