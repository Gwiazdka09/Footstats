"""Lock musi opisywać to, co naprawdę jedzie na produkcję.

DLACZEGO LOCK W OGÓLE: do 23.08 obrazy instalowały `.[api,ai,scraper]`, czyli
zakresy `>=` z `pyproject.toml`. Dwa buildy tego samego commita mogły dostać różne
wersje zależności, a nowa wersja z góry wchodziła na produkcję po cichu. To ta sama
rodzina awarii co wycofany model Groqa (16-22.08): zmiana po stronie kogoś innego,
niewidoczna u nas aż do skutku.

DLACZEGO TEN TEST: lock żyje obok `pyproject.toml`, więc zdryfuje przy pierwszej
dodanej zależności — i wtedy build zainstaluje starą listę bez nowego pakietu albo
padnie na imporcie. Dokładnie tak zdryfował kiedyś `requirements.txt` (brakowało
w nim m.in. `beautifulsoup4` i `psycopg2-binary`, więc skaner CVE ich nie widział);
`tests/test_dependencies_declared.py` powstał po tamtej lekcji, ten robi to samo
dla locków.

Sprawdzamy zgodność NAZW, nie wersji: wersje w locku są z definicji konkretniejsze
niż zakresy w `pyproject`. Chodzi o to, żeby żadna zadeklarowana zależność nie
wypadła z locka.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]
LOCKI = {
    "requirements-jobs.lock": ["api", "ai", "scraper"],
    "requirements-api.lock": ["api"],
}


def _nazwa(spec: str) -> str:
    """`python-jose[cryptography]>=3.3` → `python-jose`. Normalizuje myślnik/podkreślnik."""
    rdzen = re.split(r"[<>=!~\[;]", spec, maxsplit=1)[0].strip()
    return rdzen.lower().replace("_", "-")


def _z_pyproject(extras: list[str]) -> set[str]:
    dane = tomllib.loads((KORZEN / "pyproject.toml").read_text(encoding="utf-8"))
    projekt = dane["project"]
    paczki = list(projekt.get("dependencies", []))
    for extra in extras:
        paczki += projekt.get("optional-dependencies", {}).get(extra, [])
    return {_nazwa(p) for p in paczki if p.strip()}


def _z_locka(plik: str) -> set[str]:
    tekst = (KORZEN / plik).read_text(encoding="utf-8")
    nazwy = set()
    for linia in tekst.splitlines():
        linia = linia.strip()
        if not linia or linia.startswith("#") or linia.startswith("--"):
            continue
        if "==" in linia:
            nazwy.add(_nazwa(linia))
    return nazwy


@pytest.mark.parametrize("plik,extras", LOCKI.items())
def test_lock_zawiera_wszystko_z_pyproject(plik, extras):
    """Zależność dodana do `pyproject` bez przegenerowania locka = build bez niej."""
    brakuje = _z_pyproject(extras) - _z_locka(plik)

    assert not brakuje, (
        f"{plik} nie zawiera: {sorted(brakuje)}. "
        f"Przegeneruj: uv pip compile pyproject.toml "
        f"{' '.join('--extra ' + e for e in extras)} "
        f"--python-platform linux --python-version 3.12 -o {plik}"
    )


@pytest.mark.parametrize("plik,extras", LOCKI.items())
def test_lock_ma_same_przypiete_wersje(plik, extras):
    """Zakres `>=` w locku znaczy, że lock niczego nie gwarantuje."""
    tekst = (KORZEN / plik).read_text(encoding="utf-8")
    luzne = [
        linia.strip() for linia in tekst.splitlines()
        if linia.strip() and not linia.strip().startswith(("#", "--"))
        and "==" not in linia and not linia.startswith(" ")
    ]

    assert luzne == [], f"{plik} ma nieprzypiete pozycje: {luzne}"


@pytest.mark.parametrize("plik,extras", LOCKI.items())
def test_lock_zbudowany_dla_linuxa_nie_dla_hosta(plik, extras):
    """Lock generowany na Windowsie opisywałby inne zależności niż kontener.

    Nagłówek `uv` zapisuje użytą komendę — to jedyny ślad, po którym da się to
    sprawdzić bez odpalania buildu.
    """
    naglowek = (KORZEN / plik).read_text(encoding="utf-8")[:600]

    assert "--python-platform linux" in naglowek, (
        f"{plik} nie deklaruje platformy linux — lock z hosta moze nie pasowac "
        "do obrazu (inne kola, inne zaleznosci warunkowe)."
    )


def test_obrazy_instaluja_z_locka():
    """Lock, z którego nikt nie instaluje, to plik dekoracyjny."""
    for dockerfile, plik in [("Dockerfile.jobs", "requirements-jobs.lock"),
                             ("Dockerfile.api", "requirements-api.lock")]:
        tresc = (KORZEN / dockerfile).read_text(encoding="utf-8")
        assert f"-r {plik}" in tresc, f"{dockerfile} nie instaluje z {plik}"
        assert f"COPY {plik}" in tresc, f"{dockerfile} nie kopiuje {plik}"
