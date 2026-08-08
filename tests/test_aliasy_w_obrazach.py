"""Plik aliasów musi jechać do repo i do obrazów — inaczej istnieje tylko lokalnie.

PO CO: `data/` jest w `.gitignore` w całości, a `data/team_mappings.json` nie miał
negacji. Efekt zmierzony 09.08.2026: 32 aliasy przejrzane ręcznie (m.in. cała
Bundesliga) siedziały na dysku dewelopera, nie wchodziły do commita, więc do
obrazu też nie. Na produkcji `_zapewnij_plik_mappingow()` widziało brak pliku
i zapisywało `_DEFAULT_MAPPINGS` — czyli kontener startował z GARŚCIĄ domyślnych
aliasów i cichym przekonaniem, że ma komplet.

Ta sama klasa co brakujący `pyarrow` (patrz `test_zaleznosc_parquet_audyt.py`):
lokalnie zielono, w produkcji model dostaje mniej danych i nikt nie krzyczy.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLIK = "data/team_mappings.json"


def test_plik_aliasow_jest_sledzony_przez_git() -> None:
    wynik = subprocess.run(
        ["git", "check-ignore", PLIK],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert wynik.returncode != 0, (
        f"{PLIK} jest ignorowany przez gita — aliasy nie trafia do repo ani do obrazu"
    )


def test_plik_aliasow_kopiowany_do_obu_obrazow() -> None:
    """Oba obrazy dopasowuja nazwy druzyn: API liczy predykcje, joby rozliczaja."""
    for dockerfile in ("Dockerfile.api", "Dockerfile.jobs"):
        tresc = (ROOT / dockerfile).read_text(encoding="utf-8")
        assert PLIK in tresc, f"{dockerfile} nie kopiuje {PLIK}"


def test_dockerignore_nie_wycina_pliku_aliasow() -> None:
    """`COPY` nie pomoze, jesli `.dockerignore` wytnie plik z kontekstu budowania."""
    linie = [
        w.strip() for w in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if w.strip() and not w.startswith("#")
    ]
    wycinajace = [w for w in linie if w in ("data/", "data", "data/*")]
    assert not wycinajace or f"!{PLIK}" in linie, (
        f".dockerignore wycina katalog data ({wycinajace}) bez negacji dla {PLIK}"
    )


def test_gcloudignore_nie_wycina_pliku_aliasow() -> None:
    """Build na Cloud Build ma wlasny filtr — `COPY` wywala sie, gdy plik odpadnie."""
    linie = [
        w.strip() for w in (ROOT / ".gcloudignore").read_text(encoding="utf-8").splitlines()
        if w.strip() and not w.startswith("#")
    ]
    wycinajace = [w for w in linie if w in ("/data/*", "data/*", "/data/", "data/")]
    assert not wycinajace or f"!/{PLIK}" in linie, (
        f".gcloudignore wycina data ({wycinajace}) bez negacji dla {PLIK}"
    )


def test_aliasy_niemieckie_sa_w_zapisanym_pliku() -> None:
    """Sam fakt sledzenia nie wystarcza — plik musi realnie zawierac przeglad.

    Bez tego commit z pustym plikiem przechodzi testy, a produkcja dalej nie zna
    nazw z The Odds API.
    """
    mapa = json.loads((ROOT / PLIK).read_text(encoding="utf-8"))
    wymagane = {
        "borussia dortmund": "dortmund",
        "1 fc koln": "koln",
        "eintracht frankfurt": "ein frankfurt",
        "hamburger": "hamburg",
    }
    brakuje = {k: v for k, v in wymagane.items() if mapa.get(k) != v}
    assert not brakuje, f"brak aliasow Bundesligi w {PLIK}: {brakuje}"
