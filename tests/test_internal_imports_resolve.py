"""test_internal_imports_resolve.py — kazdy import `footstats.*` wskazuje na istniejacy kod.

PO CO (2026-07-30):

`src/footstats/cli.py` mial blok:

    try:
        from ai_analyzer import analizuj_mecz_ai as _analizuj_ai
        from scraper_kursy import szukaj_kursy_meczu as _kursy_ai
        _ai_dostepne = True
    except ImportError:
        pass

`ai_analyzer` i `scraper_kursy` to moduly top-level sprzed przeniesienia kodu do
pakietu `footstats`. Po przeprowadzce przestaly istniec, ale `except ImportError:
pass` zamienil to w ciche `_ai_dostepne = False` — opcje I/J w menu CLI od tamtej
pory zawsze odpowiadaly "Brak modulow AI", mimo ze same funkcje zyly (przeniesione
do footstats.ai.analyzer / footstats.ai.output / footstats.scrapers.kursy).

To ta sama klasa bledu co niezadeklarowane bs4 i scikit-learn
(patrz tests/test_dependencies_declared.py): `try/except ImportError` zamienia
zepsuty import w ciche wylaczenie funkcji. Roznica: tam brakowalo zaleznosci
zewnetrznej, tutaj rozjechala sie sciezka wewnetrzna.

Test rozwiazuje sciezki po PLIKACH, bez importowania modulow — zaden kod
produkcyjny nie jest wykonywany.
"""
from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _ROOT / "src"
_PAKIET = _SRC_ROOT / "footstats"


def _modul_istnieje(sciezka_kropkowa: str) -> bool:
    """'footstats.ai.analyzer' -> czy jest plik .py albo pakiet z __init__.py."""
    czesci = sciezka_kropkowa.split(".")
    baza = _SRC_ROOT.joinpath(*czesci)
    return baza.with_suffix(".py").is_file() or (baza / "__init__.py").is_file()


def _nazwy_najwyzszego_poziomu(sciezka_kropkowa: str) -> set[str] | None:
    """Nazwy definiowane na najwyzszym poziomie modulu (None gdy to pakiet/brak pliku)."""
    plik = _SRC_ROOT.joinpath(*sciezka_kropkowa.split(".")).with_suffix(".py")
    if not plik.is_file():
        return None

    nazwy: set[str] = set()
    for wezel in ast.parse(plik.read_text(encoding="utf-8")).body:
        if isinstance(wezel, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nazwy.add(wezel.name)
        elif isinstance(wezel, ast.Assign):
            for cel in wezel.targets:
                if isinstance(cel, ast.Name):
                    nazwy.add(cel.id)
        elif isinstance(wezel, ast.AnnAssign) and isinstance(wezel.target, ast.Name):
            nazwy.add(wezel.target.id)
        elif isinstance(wezel, (ast.Import, ast.ImportFrom)):
            for alias in wezel.names:
                nazwy.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(wezel, (ast.If, ast.Try)):
            # Definicje warunkowe (np. fallbacki pod try/except) tez sie licza.
            for pod in ast.walk(wezel):
                if isinstance(pod, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    nazwy.add(pod.name)
                elif isinstance(pod, ast.Assign):
                    for cel in pod.targets:
                        if isinstance(cel, ast.Name):
                            nazwy.add(cel.id)
                elif isinstance(pod, (ast.Import, ast.ImportFrom)):
                    for alias in pod.names:
                        nazwy.add(alias.asname or alias.name.split(".")[0])
    return nazwy


def _importy_footstats() -> list[tuple[str, str | None, str]]:
    """[(modul, nazwa_lub_None, 'plik:linia')] dla kazdego importu z pakietu footstats."""
    wynik: list[tuple[str, str | None, str]] = []

    for plik in sorted(_PAKIET.rglob("*.py")):
        drzewo = ast.parse(plik.read_text(encoding="utf-8"))
        gdzie = plik.relative_to(_ROOT)

        for wezel in ast.walk(drzewo):
            if isinstance(wezel, ast.Import):
                for alias in wezel.names:
                    if alias.name.split(".")[0] == "footstats":
                        wynik.append((alias.name, None, f"{gdzie}:{wezel.lineno}"))
            elif isinstance(wezel, ast.ImportFrom):
                if wezel.level != 0 or not wezel.module:
                    continue  # importy wzgledne — rozwiazuje je interpreter
                if wezel.module.split(".")[0] != "footstats":
                    continue
                for alias in wezel.names:
                    if alias.name == "*":
                        wynik.append((wezel.module, None, f"{gdzie}:{wezel.lineno}"))
                    else:
                        wynik.append((wezel.module, alias.name, f"{gdzie}:{wezel.lineno}"))
    return wynik


def test_moduly_footstats_istnieja():
    """`from footstats.X import ...` musi wskazywac na istniejacy modul."""
    braki = [
        f"{modul} — {gdzie}"
        for modul, _, gdzie in _importy_footstats()
        if not _modul_istnieje(modul)
    ]
    assert not braki, (
        "Import modulu `footstats.*`, ktory nie istnieje. Pod try/except ImportError "
        "taki import cicho wylacza funkcje zamiast wywalic blad:\n  "
        + "\n  ".join(sorted(set(braki)))
    )


def test_importowane_nazwy_istnieja():
    """`from footstats.X import Y` — Y musi byc zdefiniowane w X.

    Lapie rename/przeniesienie funkcji: import przezyje (modul jest), ale nazwa
    znika i pod guardem robi sie z tego cicha degradacja.
    """
    braki = []
    for modul, nazwa, gdzie in _importy_footstats():
        if nazwa is None:
            continue
        # `from footstats.core import poisson` — nazwa moze byc podmodulem.
        if _modul_istnieje(f"{modul}.{nazwa}"):
            continue
        dostepne = _nazwy_najwyzszego_poziomu(modul)
        if dostepne is None:  # pakiet (__init__.py) — pomijamy, re-eksporty
            continue
        if nazwa not in dostepne:
            braki.append(f"{modul}.{nazwa} — {gdzie}")

    assert not braki, (
        "Import nazwy, ktorej nie ma w module docelowym:\n  "
        + "\n  ".join(sorted(set(braki)))
    )
