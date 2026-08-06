"""Silnik parquet musi być ZADEKLAROWANY, nie przypadkiem obecny.

`pandas.read_parquet` nie ma wbudowanego czytnika — potrzebuje `pyarrow` albo
`fastparquet`. Ani jedno, ani drugie nie było w zależnościach FootStats, a mimo
to wszystko działało lokalnie, bo pyarrow wchodzi do środowiska deweloperskiego
przy okazji innych pakietów.

W obrazach produkcyjnych (Dockerfile.api, Dockerfile.jobs) nie wchodziło.
Efekt sprawdzony 2026-08-07 na realnych obrazach:

    ImportError: Unable to find a usable engine; tried using: 'pyarrow', 'fastparquet'

czyli `load_cached()` wywalało się w każdym kontenerze, a `quick_picks`
łapie to pod `except` i cicho degraduje z Poissona-DC do Bzzoiro-ML.
`full_dataset.parquet` był kopiowany do obu obrazów i nigdy nie dał się odczytać.

Ta sama klasa błędu co brakujące `beautifulsoup4` i `scikit-learn` — import pod
try/except, więc produkcja nie krzyczy, tylko po cichu robi coś innego.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "footstats"

# pandas potrafi czytać/pisać parquet tylko przez jeden z tych silników.
SILNIKI_PARQUET = ("pyarrow", "fastparquet")

# Wywołania, które bez silnika rzucają ImportError w runtime.
WYWOLANIA_PARQUET = ("read_parquet", "to_parquet")


def _moduly_uzywajace_parquet() -> list[Path]:
    return [
        p for p in SRC.rglob("*.py")
        if any(w in p.read_text(encoding="utf-8") for w in WYWOLANIA_PARQUET)
    ]


def _zaleznosci_bazowe() -> list[str]:
    dane = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return dane["project"]["dependencies"]


def _nazwa_pakietu(wpis: str) -> str:
    """"pyarrow>=15.0" → "pyarrow"; "python-jose[cryptography]>=3.3" → "python-jose"."""
    for separator in (">=", "==", "<=", "~=", ">", "<", "["):
        wpis = wpis.split(separator)[0]
    return wpis.strip().lower()


def test_silnik_parquet_zadeklarowany_gdy_kod_go_uzywa() -> None:
    uzywajace = _moduly_uzywajace_parquet()
    assert uzywajace, "test stracil sens — nikt juz nie czyta parquetu"

    pakiety = {_nazwa_pakietu(d) for d in _zaleznosci_bazowe()}
    brakuje = not (pakiety & set(SILNIKI_PARQUET))
    assert not brakuje, (
        "pandas nie odczyta parquetu bez pyarrow/fastparquet, a uzywaja go: "
        + ", ".join(str(p.relative_to(ROOT)) for p in uzywajace)
    )


def test_silnik_parquet_w_zaleznosciach_bazowych_nie_opcjonalnych() -> None:
    """Dockerfile.jobs instaluje `.[api,ai,scraper]`, Dockerfile.api `.[api]`.

    Silnik w innym extra niż część bazowa oznacza obraz, który dostaje plik
    parquet i nie umie go otworzyć — dokładnie stan sprzed tej poprawki.
    """
    dane = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    bazowe = {_nazwa_pakietu(d) for d in dane["project"]["dependencies"]}
    assert bazowe & set(SILNIKI_PARQUET), "silnik parquet musi byc w [project.dependencies]"


def test_requirements_nadaza_za_pyproject() -> None:
    """`requirements.txt` służy pip-auditowi w CI — bez wpisu skan omija silnik."""
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert any(s in req for s in SILNIKI_PARQUET), "brak silnika parquet w requirements.txt"


def test_silnik_parquet_realnie_importowalny() -> None:
    """Deklaracja bez instalacji nic nie daje — sprawdź, że import przechodzi."""
    import importlib.util

    dostepne = [s for s in SILNIKI_PARQUET if importlib.util.find_spec(s) is not None]
    assert dostepne, "zaden silnik parquet nie jest zainstalowany w tym srodowisku"
