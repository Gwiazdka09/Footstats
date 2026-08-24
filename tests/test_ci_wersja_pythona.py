"""CI musi sprawdzać tę samą wersję Pythona, którą uruchamia produkcja.

ZNALEZIONE 2026-08-24: `Dockerfile.api` i `Dockerfile.jobs` startują z
`python:3.12-slim`, oba locki są kompilowane `uv pip compile … --python-version 3.12`,
a wszystkie trzy joby w `ci.yml` stały na **3.11**.

Dwa skutki, jeden widoczny i jeden nie:

1. Widoczny: krok `pip-audit (dependency CVE)` padał na KAŻDYM commicie od 23.08,
   odkąd B9 przestawiło skan z ręcznego `requirements.txt` na locki. Lock pisany
   pod 3.12 nie musi się rozwiązać na 3.11. Lokalnie (3.12) ten sam skan kończy się
   `No known vulnerabilities found`, exit 0.

2. Niewidoczny i groźniejszy: job `test` też jechał na 3.11, więc suita potwierdzała
   interpreter, którego nigdzie nie uruchamiamy.

Skutek uboczny pierwszego: CI świeciło czerwono bez przerwy, więc przestało cokolwiek
znaczyć — 24.08 dwa deploye padły i wyszło to dopiero przy ręcznym sprawdzeniu
produkcji. Sygnał palący się zawsze jest równoważny brakowi sygnału.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]
CI = KORZEN / ".github" / "workflows" / "ci.yml"
LOCKI = ["requirements-api.lock", "requirements-jobs.lock"]
OBRAZY = ["Dockerfile.api", "Dockerfile.jobs"]


def _wersje_z_ci() -> list[str]:
    return re.findall(r'python-version:\s*"([\d.]+)"', CI.read_text(encoding="utf-8"))


def _wersja_z_locka(nazwa: str) -> str:
    naglowek = (KORZEN / nazwa).read_text(encoding="utf-8")[:600]
    m = re.search(r"--python-version\s+([\d.]+)", naglowek)
    assert m, f"{nazwa}: brak `--python-version` w naglowku uv"
    return m.group(1)


def _wersja_z_obrazu(nazwa: str) -> str:
    tresc = (KORZEN / nazwa).read_text(encoding="utf-8")
    m = re.search(r"^FROM python:([\d.]+)", tresc, re.MULTILINE)
    assert m, f"{nazwa}: brak `FROM python:` "
    return m.group(1)


def test_ci_deklaruje_jakas_wersje():
    assert _wersje_z_ci(), "ci.yml nie ustawia python-version — wzorzec sie rozjechal"


@pytest.mark.parametrize("obraz", OBRAZY)
def test_wszystkie_joby_ci_na_wersji_produkcyjnej(obraz: str):
    """Suita zielona na 3.11 nic nie mówi o obrazie, który startuje 3.12."""
    prod = _wersja_z_obrazu(obraz)
    rozne = {w for w in _wersje_z_ci() if w != prod}

    assert not rozne, (
        f"{obraz} uruchamia Pythona {prod}, a CI testuje na {sorted(rozne)}"
    )


@pytest.mark.parametrize("lock", LOCKI)
def test_locki_kompilowane_pod_te_sama_wersje_co_ci(lock: str):
    """`pip-audit -r <lock>` rozwiazuje zaleznosci w BIEZACYM interpreterze —
    lock pisany pod inna wersje potrafi sie nie rozwiazac i wywalic krok."""
    lockowa = _wersja_z_locka(lock)
    rozne = {w for w in _wersje_z_ci() if w != lockowa}

    assert not rozne, (
        f"{lock} skompilowany pod {lockowa}, a CI skanuje go na {sorted(rozne)}"
    )


def test_oba_obrazy_na_tej_samej_wersji():
    """Rozjazd miedzy api a jobs oznaczalby, ze jeden z nich nie jest pokryty."""
    assert len({_wersja_z_obrazu(o) for o in OBRAZY}) == 1
