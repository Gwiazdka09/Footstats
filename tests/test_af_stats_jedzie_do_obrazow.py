"""`af_stats.parquet` musi dojechać do obrazów — inaczej prod cicho jedzie na golach.

Ten plik jest jedynym śladem po kilku tysiącach requestów wydanych ze wspólnego
z produkcją limitu 7500/dobę. Jeśli nie wejdzie do build-contextu albo do repo,
`load_cached()` scali PUSTY zbiór i model w tych ligach wróci do samych goli —
bez jednego wyjątku, bo `form.py` tak ma działać, gdy strzałów nie ma.

To jest dokładnie kształt „zielone testy, martwa produkcja": lokalnie wszystko
liczy się poprawnie, bo plik leży na dysku, a kontener widzi pustkę.

Cztery bramki, każda potrafi zjeść plik osobno:
  * `.gitignore` — `/data/*` wycina katalog, `git add` odmawia bez negacji;
  * `.dockerignore` — plik spoza kontekstu nie istnieje w obrazie;
  * `.gcloudignore` — to on decyduje, co jedzie do Cloud Build;
  * `COPY` w obu Dockerfile'ach — bez niego plik zostaje w kontekście, ale nie
    w obrazie (a `COPY` na nieistniejący plik wywala build, więc kolejność
    dodawania ma znaczenie).
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WZGLEDNA = "data/hist_cache/af_stats.parquet"


def _tresc(nazwa: str) -> str:
    return (ROOT / nazwa).read_text(encoding="utf-8")


@pytest.mark.parametrize("dockerfile", ["Dockerfile.api", "Dockerfile.jobs"])
def test_obraz_kopiuje_statystyki(dockerfile: str) -> None:
    tresc = _tresc(dockerfile)
    assert f"COPY {WZGLEDNA}" in tresc, (
        f"{dockerfile} nie kopiuje {WZGLEDNA} — kontener scali pusty zbior"
    )


def test_dockerignore_odslania_plik() -> None:
    assert f"!{WZGLEDNA}" in _tresc(".dockerignore")


def test_gcloudignore_odslania_plik() -> None:
    """To `.gcloudignore` decyduje, co trafia do Cloud Build, nie `.dockerignore`."""
    assert f"!/{WZGLEDNA}" in _tresc(".gcloudignore")


def test_gitignore_odslania_plik() -> None:
    """`/data/*` blokuje `git add` bez jawnej negacji katalogu I pliku."""
    tresc = _tresc(".gitignore")
    assert "!/data/hist_cache/" in tresc
    assert f"!/{WZGLEDNA}" in tresc


def test_plik_jest_sledzony_przez_gita() -> None:
    """Negacja w `.gitignore` nic nie da, jeśli nikt pliku nie dodał.

    Ten test lapie stan, w ktorym wszystkie listy wykluczen sa poprawne, a plik
    zyje wylacznie na dysku deweloperskim.
    """
    import subprocess

    wynik = subprocess.run(
        ["git", "ls-files", "--error-unmatch", WZGLEDNA],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert wynik.returncode == 0, (
        f"{WZGLEDNA} nie jest sledzony przez gita — `git add -f {WZGLEDNA}`"
    )


def test_dataset_i_statystyki_sa_odslaniane_tak_samo() -> None:
    """Jeden plik danych obok drugiego: reguły muszą je traktować identycznie.

    `full_dataset.parquet` przeszedł tę drogę wcześniej i każda z czterech bramek
    wymagała osobnego wpisu. Rozjazd między nimi byłby cichy — build przeszedłby,
    a w obrazie leżałby tylko jeden z dwóch plików.
    """
    for nazwa, przedrostek in ((".dockerignore", ""), (".gcloudignore", "/")):
        tresc = _tresc(nazwa)
        assert f"!{przedrostek}data/hist_cache/full_dataset.parquet" in tresc
        assert f"!{przedrostek}{WZGLEDNA}" in tresc
