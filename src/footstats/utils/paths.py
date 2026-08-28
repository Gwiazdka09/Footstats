"""Jedno miejsce, w którym powstaje ścieżka katalogu cache.

DLACZEGO TO ISTNIEJE. Do 28.08 każdy moduł liczył swój katalog sam, przy
imporcie, jako stałą modułową — `Path("cache/kursy")`, `Path("cache/sts")`,
`Path(__file__).parents[4] / "cache" / "footballdata"` i tak dalej, 18 razy.
Skutek: **żadna zmienna środowiskowa nie mogła ich przekierować**, bo wartość
powstawała zanim cokolwiek zdążyło ją ustawić. Dwa równoległe przebiegi pytest
(np. dwa agenty naraz) pisały i kasowały te same pliki, co dawało czerwone
testy niezależne od logiki produkcyjnej. Ten sam objaw złapała wcześniej
fikstura `clean_checkpoint_dir` w `tests/test_checkpoint.py`, tyle że tam
`CHECKPOINT_DIR` dało się nadpisać, bo czytało `os.getenv` przy wywołaniu.

KONTRAKT:

* bez `FOOTSTATS_CACHE_ROOT` ścieżka jest **dokładnie taka jak przed zmianą** —
  łącznie z modułami kotwiczonymi do `__file__` zamiast do katalogu bieżącego.
  Produkcja tej zmiennej nie ustawia i nie zmienia zachowania;
* z `FOOTSTATS_CACHE_ROOT` wszystkie katalogi lądują pod jednym korzeniem, co
  pozwala `tests/conftest.py` dać każdemu procesowi pytest własny.

Rozjazd domyślnych kotwic (część modułów liczy od CWD, część od pliku) ZOSTAJE
nietknięty świadomie: ujednolicenie przeniosłoby produkcyjny cache w nowe
miejsce, a to osobna decyzja niż izolacja testów.
"""
from __future__ import annotations

import os
from pathlib import Path

ZMIENNA_KORZENIA = "FOOTSTATS_CACHE_ROOT"
_DOMYSLNY_KORZEN = Path("cache")


def korzen_cache(domyslny: Path | None = None) -> Path:
    """Korzeń cache: env, a bez niego `domyslny` albo `cache/` względem CWD.

    Pusty łańcuch traktujemy jak brak wartości — `Path("")` dałoby katalog
    bieżący i cichy rozjazd zamiast błędu.
    """
    korzen = os.getenv(ZMIENNA_KORZENIA)
    if korzen:
        return Path(korzen)
    return Path(domyslny) if domyslny is not None else _DOMYSLNY_KORZEN


def katalog_cache(nazwa: str, domyslny: Path | None = None) -> Path:
    """Katalog cache o nazwie `nazwa`.

    `domyslny` podają moduły, których dotychczasowa ścieżka NIE była
    `cache/<nazwa>` względem CWD (np. kotwiczone do `__file__`). Env wygrywa
    z `domyslny` — inaczej izolacja przebiegu byłaby dziurawa akurat tam.
    """
    korzen = os.getenv(ZMIENNA_KORZENIA)
    if korzen:
        return Path(korzen) / nazwa
    if domyslny is not None:
        return Path(domyslny)
    return _DOMYSLNY_KORZEN / nazwa
