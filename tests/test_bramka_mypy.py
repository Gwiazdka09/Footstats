"""Zakres bramki mypy nie może po cichu zmaleć.

Cała reszta długu w tym repo jest zamrożona baselinem, który wolno tylko obniżać
(`test_ciche_except_audit`, `test_silent_swallow_audit`, `test_broad_except_audit`).
Bramka mypy jako jedyna żyła w YAML-u i nikt jej nie pilnował — a zawężenie
`python -m mypy <katalogi>` do jednego katalogu wygląda w diffie jak drobiazg
i przechodzi na zielono, bo mniej sprawdzanego kodu to mniej błędów.

Kontekst z 28.08 (J2): zakres BYŁ wąski przez przypadek, nie z wyboru —
`python_version = "3.11"` przy stubach numpy w składni 3.12 przerywało analizę
przy pierwszym module importującym numpy. Po naprawie bramka objęła 3 katalogi
zamiast 1. Ten test pilnuje, żeby ratchet nie cofnął się w ciszy.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]
CI = KORZEN / ".github" / "workflows" / "ci.yml"

# Katalogi, które PRZESZŁY na zero błędów i od tej pory są bramkowane.
# Dopisujesz tu tylko razem z rozszerzeniem komendy w ci.yml — nigdy odwrotnie.
BRAMKOWANE = (
    "src/footstats/scrapers/sources/",
    "src/footstats/db/",
    "src/footstats/api/",
)


def _komenda_mypy() -> str:
    if not CI.is_file():
        pytest.skip("brak .github/workflows/ci.yml")
    for linia in CI.read_text(encoding="utf-8").splitlines():
        if "mypy" in linia and ("run:" in linia or linia.strip().startswith("python -m mypy")):
            return linia
    pytest.fail("ci.yml nie uruchamia mypy — bramka typow zniknela")


@pytest.mark.parametrize("katalog", BRAMKOWANE)
def test_katalog_zostaje_w_bramce(katalog: str):
    assert katalog in _komenda_mypy(), (
        f"{katalog} wypadl z bramki mypy w ci.yml — dlug typow moze tam rosnac"
        " bez czerwonego builda"
    )


def test_python_version_zgadza_sie_z_reszta_projektu():
    """SEDNO awarii, którą J2 naprawiło. `python_version` niższy niż realny
    wywala mypy na stubach numpy (`Type statement is only supported in Python
    3.12 and greater`) i analiza URYWA SIĘ przy pierwszym module z numpy —
    bramka dalej świeci na zielono, tylko nie sprawdza prawie niczego."""
    pyproject = (KORZEN / "pyproject.toml").read_text(encoding="utf-8")
    dopasowanie = re.search(r'^\s*python_version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert dopasowanie, "brak python_version w [tool.mypy]"
    wersja = dopasowanie.group(1)

    ci = CI.read_text(encoding="utf-8")
    wersje_ci = set(re.findall(r'python-version:\s*"([^"]+)"', ci))
    assert wersje_ci, "ci.yml nie ustawia python-version"
    assert wersja in wersje_ci, (
        f"mypy analizuje jako Python {wersja}, a CI biegnie na {sorted(wersje_ci)} —"
        " rozjazd potrafi UNIERUCHOMIC mypy na stubach zaleznosci, nie tylko"
        " przepuscic blad"
    )


def test_obrazy_produkcyjne_maja_te_sama_wersje():
    """Trzecie miejsce, w którym ta sama liczba musi się zgadzać."""
    pyproject = (KORZEN / "pyproject.toml").read_text(encoding="utf-8")
    wersja = re.search(r'^\s*python_version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE).group(1)

    for nazwa in ("Dockerfile.jobs", "Dockerfile.api"):
        plik = KORZEN / nazwa
        if not plik.is_file():
            continue
        obrazy = re.findall(r"FROM python:([0-9]+\.[0-9]+)", plik.read_text(encoding="utf-8"))
        for obraz in obrazy:
            assert obraz == wersja, (
                f"{nazwa} buduje na Pythonie {obraz}, a mypy analizuje jako {wersja}"
            )
