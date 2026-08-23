"""B9 — skaner CVE ma czytać tę samą listę, którą instaluje obraz.

STAN PRZED: trzy listy zależności. `pyproject.toml` (źródło prawdy), dwa locki
(to, co realnie instalują obrazy) i `requirements.txt` — ręcznie utrzymywane
lustro, istniejące wyłącznie po to, żeby `pip-audit` miał co skanować.

CO ZMIERZONO 23.08, ZANIM COKOLWIEK RUSZONO (uczciwie: hipoteza się NIE potwierdziła):
`pip-audit -r requirements.txt` rozwiązuje zakresy `>=` do najnowszych wydań, więc
podejrzenie było takie, że skanuje wersje inne niż te w obrazie. Porównanie zbiorów
dało **83 pakiety w obu przypadkach, zero różnic w nazwach i zero w wersjach** —
zarówno dla `requirements-jobs.lock`, jak i `requirements-api.lock`. Żadnej dziury
w bezpieczeństwie nie było.

DLACZEGO MIMO TO WARTO: ta zgodność jest własnością ŚWIEŻOŚCI locka, nie projektu.
Locki są przypięte celowo i normalnym ich stanem jest „nie regenerowane od tygodni";
zakresy `>=` rozjeżdżają się wtedy ku nowszym wersjom, a skan zaczyna dotyczyć
pakietów, których nikt nie uruchamia. Do tego lustro było utrzymywane RĘCZNIE
i już raz zdryfowało — wypadły z niego m.in. `beautifulsoup4`, `psycopg2-binary`,
`sentry-sdk`, `langfuse` i `tenacity`, czyli paczki jadące na produkcję bez skanu.
Trzecia lista nie dawała nic, czego nie dają locki, a mogła kłamać.

TEN TEST nie pilnuje nazw plików, tylko NIEZMIENNIKA: zbiór list instalowanych
przez obrazy == zbiór list skanowanych w CI. Przetrwa zmianę nazw i dołożenie
trzeciego obrazu.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]
DOCKERFILE = {
    "Dockerfile.api": KORZEN / "Dockerfile.api",
    "Dockerfile.jobs": KORZEN / "Dockerfile.jobs",
}
CI = KORZEN / ".github" / "workflows" / "ci.yml"


def _instalowane_przez_obraz(sciezka: Path) -> set[str]:
    """Pliki wymagań, które obraz podaje `pip install -r` / `uv pip install -r`."""
    tresc = sciezka.read_text(encoding="utf-8")
    aktywne = "\n".join(
        l for l in tresc.splitlines() if not l.lstrip().startswith("#")
    )
    return set(re.findall(r"-r\s+([\w.\-/]+\.(?:lock|txt))", aktywne))


def _skanowane_w_ci() -> set[str]:
    tresc = CI.read_text(encoding="utf-8")
    aktywne = "\n".join(
        l for l in tresc.splitlines() if not l.lstrip().startswith("#")
    )
    # `pip_audit`/`pip-audit` z jednym lub wieloma `-r`.
    polecenia = re.findall(r"pip[_-]audit[^\n]*", aktywne)
    znalezione: set[str] = set()
    for p in polecenia:
        znalezione |= set(re.findall(r"-r\s+([\w.\-/]+\.(?:lock|txt))", p))
    return znalezione


@pytest.fixture(scope="module")
def instalowane() -> set[str]:
    razem: set[str] = set()
    for nazwa, sciezka in DOCKERFILE.items():
        if not sciezka.exists():
            pytest.skip(f"brak {nazwa}")
        razem |= _instalowane_przez_obraz(sciezka)
    assert razem, "zaden obraz nie instaluje z pliku wymagan — zmienil sie sposob buildu"
    return razem


# ── sedno niezmiennika ──────────────────────────────────────────────────────

def test_kazda_lista_z_obrazu_jest_skanowana(instalowane: set[str]):
    """Paczka jadąca na produkcję bez skanu CVE to dokładnie ta awaria, po której
    powstał `test_dependencies_declared` — tylko że wtedy zauważona po fakcie."""
    nieskanowane = sorted(instalowane - _skanowane_w_ci())

    assert not nieskanowane, (
        f"obrazy instaluja z {nieskanowane}, a CI tego NIE skanuje — "
        "te paczki jada na produkcje bez skanu CVE"
    )


def test_ci_nie_skanuje_listy_ktorej_nikt_nie_instaluje(instalowane: set[str]):
    """Skan pliku, którego żaden obraz nie instaluje, daje zielone CI o czymś,
    czego nie ma na produkcji — gorsze niż brak skanu, bo uspokaja."""
    zbedne = sorted(_skanowane_w_ci() - instalowane)

    assert not zbedne, (
        f"CI skanuje {zbedne}, ale zaden obraz z tego nie instaluje — "
        "zielony wynik dotyczy wtedy czegos, czego nikt nie uruchamia"
    )


def test_skanowane_pliki_istnieja():
    brak = sorted(p for p in _skanowane_w_ci() if not (KORZEN / p).exists())

    assert not brak, f"CI skanuje nieistniejace pliki: {brak}"


# ── trzecia lista ma nie wrócić ─────────────────────────────────────────────

def test_brak_recznego_lustra_zaleznosci():
    """`requirements.txt` był utrzymywany ręcznie i już raz zdryfował od pyproject.
    Locki niosą tę samą informację dokładniej i generują się poleceniem, więc
    trzecia lista to tylko kolejne miejsce do rozjechania się."""
    lustro = KORZEN / "requirements.txt"

    assert not lustro.exists(), (
        "requirements.txt wrocil. Locki (`requirements-api.lock`, "
        "`requirements-jobs.lock`) opisuja to samo dokladniej i sa generowane, "
        "nie przepisywane recznie — patrz tests/test_lockfile_zgodny.py"
    )


def test_oba_locki_sa_skanowane():
    """Wprost, żeby regresja nie schowała się za ogólnym niezmiennikiem."""
    skanowane = _skanowane_w_ci()

    for lock in ("requirements-api.lock", "requirements-jobs.lock"):
        assert lock in skanowane, f"{lock} nie jest skanowany przez pip-audit w CI"
