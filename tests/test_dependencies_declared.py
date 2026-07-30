"""test_dependencies_declared.py — kazdy import z src/ ma pokrycie w pyproject.toml.

PO CO TEN TEST ISTNIEJE (2026-07-30):

`beautifulsoup4` siedzialo wylacznie w extrasie [scraper]. Skutki, wszystkie ciche:
  * job `test` na CI instaluje ".[dev,api,ai]" — bez [scraper] — wiec 3 testy
    understat wywalaly sie WYLACZNIE na CI ("brak bs4 — pomijam tabele ligi"),
    a lokalnie przechodzily, bo bs4 bylo w venv przypadkiem (jako zaleznosc czegos innego);
  * Dockerfile.api instaluje ".[api]" — takze bez bs4 — wiec fallback rozliczen
    przez FlashScore (core/coupon_settlement.py -> scrapers/flashscore_results.py)
    nie dzialal na produkcji, bo import siedzi pod try/except i ustawia BeautifulSoup=None.

Przy okazji wyszlo, ze `scikit-learn` nie byl zadeklarowany NIGDZIE, a
core/probability_calibrator.fit_calibrator() importuje go pod try/except —
czyli refit kalibracji na produkcji zawsze konczyl sie logiem
"sklearn not available — calibrator skipped".

Wspolny mianownik: import pod `try/except ImportError` zamienia brak zaleznosci
w ciche wylaczenie funkcji zamiast w glosny blad. Ten test wymusza, by KAZDY
taki przypadek byl swiadoma decyzja zapisana w `_OPCJONALNE` ponizej.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "footstats"

# Nazwa modulu przy imporcie != nazwa paczki na PyPI.
_ALIAS_PYPI = {
    "bs4": "beautifulsoup4",
    "jose": "python-jose",
    "dotenv": "python-dotenv",
    "psycopg2": "psycopg2-binary",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "PIL": "pillow",
    "dateutil": "python-dateutil",
    "sentry_sdk": "sentry-sdk",
    "fastapi_mcp": "fastapi-mcp",
    "prometheus_client": "prometheus-client",
    "sentence_transformers": "sentence-transformers",
    "pytest_cov": "pytest-cov",
}

# Moduly lokalne / nie-pakietowe, ktore nie sa zaleznoscia zewnetrzna.
_LOKALNE = {"footstats", "src", "tests", "scripts"}

# Importy pod try/except ImportError, ktore SWIADOMIE zostaja niezadeklarowane.
# Klucz = nazwa modulu przy imporcie, wartosc = uzasadnienie (widoczne w bledzie testu).
#
# Dopisanie czegos tutaj to deklaracja: "ta funkcja MOZE byc wylaczona na produkcji
# i to jest OK". Jesli tak nie jest — zamiast wpisu dodaj zaleznosc do pyproject.toml.
_OPCJONALNE = {
    "loguru": "logging_config ma pelny fallback na stdlib logging",
    "tabulate": "core/backtest.py ma wlasna implementacje zastepcza tabulate()",
    "feedparser": "scrapers/enriched.py — wzbogacanie RSS, nieobowiazkowe dla predykcji",
    "soccerdata": "data/historical_loader.py — jednorazowy import historii, uruchamiany recznie",
    "prometheus_client": "metryki /metrics — brak = brak metryk, pipeline dziala",
    "sentence_transformers": "RAG embeddings — ciezki model, swiadomie poza obrazem produkcyjnym",
}


def _importy_zewnetrzne() -> dict[str, dict[str, object]]:
    """Mapa modul -> {"twardy": bool, "miejsca": [str]} dla importow spoza stdlib."""
    stdlib = set(sys.stdlib_module_names)
    znalezione: dict[str, dict[str, object]] = {}

    for plik in sorted(_SRC.rglob("*.py")):
        drzewo = ast.parse(plik.read_text(encoding="utf-8"))

        # Linie importow objetych try/except lapiacym ImportError.
        pod_guardem: set[int] = set()
        for wezel in ast.walk(drzewo):
            if not isinstance(wezel, ast.Try):
                continue
            lapie_import = any(
                h.type is None
                or re.search(r"\b(ImportError|ModuleNotFoundError|Exception)\b",
                             ast.unparse(h.type))
                for h in wezel.handlers
            )
            if lapie_import:
                for galaz in wezel.body:
                    for w in ast.walk(galaz):
                        linia = getattr(w, "lineno", None)
                        if linia is not None:
                            pod_guardem.add(linia)

        for wezel in ast.walk(drzewo):
            if isinstance(wezel, ast.Import):
                moduly = [a.name.split(".")[0] for a in wezel.names]
            elif isinstance(wezel, ast.ImportFrom) and wezel.level == 0 and wezel.module:
                moduly = [wezel.module.split(".")[0]]
            else:
                continue

            for mod in moduly:
                if mod in stdlib or mod in _LOKALNE:
                    continue
                wpis = znalezione.setdefault(mod, {"twardy": False, "miejsca": []})
                if wezel.lineno not in pod_guardem:
                    wpis["twardy"] = True
                wpis["miejsca"].append(  # type: ignore[union-attr]
                    f"{plik.relative_to(_ROOT)}:{wezel.lineno}"
                )

    return znalezione


def _nazwa_paczki(wymog: str) -> str:
    """'python-jose[cryptography]>=3.3' -> 'python-jose'."""
    return re.split(r"[<>=!~\[;\s]", wymog.strip())[0].lower().replace("_", "-")


def _pyproject() -> dict:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def zadeklarowane() -> set[str]:
    """Wszystkie paczki z pyproject — baza + KAZDY extras."""
    pj = _pyproject()
    wymogi = list(pj["project"]["dependencies"])
    for lista in pj["project"].get("optional-dependencies", {}).values():
        wymogi += lista
    return {_nazwa_paczki(w) for w in wymogi}


def test_twarde_importy_sa_zadeklarowane(zadeklarowane):
    """Import bez try/except = crash przy braku paczki. Musi byc w pyproject."""
    braki = []
    for mod, info in sorted(_importy_zewnetrzne().items()):
        if not info["twardy"]:
            continue
        pypi = _ALIAS_PYPI.get(mod, mod.lower().replace("_", "-"))
        if pypi not in zadeklarowane:
            miejsca = ", ".join(sorted(set(info["miejsca"]))[:3])  # type: ignore[index]
            braki.append(f"{mod} (PyPI: {pypi}) — {miejsca}")

    assert not braki, (
        "Twardy import paczki spoza pyproject.toml — na czystym srodowisku "
        "(CI / obraz Docker) modul sie NIE zaimportuje:\n  "
        + "\n  ".join(braki)
        + "\nDodaj zaleznosc do [project].dependencies albo do wlasciwego extras."
    )


def test_opcjonalne_importy_sa_udokumentowane(zadeklarowane):
    """Import pod try/except ImportError = cicha degradacja. Wymaga swiadomej decyzji.

    Albo paczka jest w pyproject (funkcja ma dzialac), albo w `_OPCJONALNE`
    z uzasadnieniem (funkcja moze byc wylaczona). Trzeciej opcji nie ma —
    dokladnie tak przepadly bs4 i scikit-learn.
    """
    nieudokumentowane = []
    for mod, info in sorted(_importy_zewnetrzne().items()):
        if info["twardy"]:
            continue
        pypi = _ALIAS_PYPI.get(mod, mod.lower().replace("_", "-"))
        if pypi in zadeklarowane or mod in _OPCJONALNE:
            continue
        miejsca = ", ".join(sorted(set(info["miejsca"]))[:3])  # type: ignore[index]
        nieudokumentowane.append(f"{mod} (PyPI: {pypi}) — {miejsca}")

    assert not nieudokumentowane, (
        "Import pod try/except ImportError, a paczki nie ma ani w pyproject.toml, "
        "ani w _OPCJONALNE. Brak paczki cicho wylaczy te funkcje na produkcji:\n  "
        + "\n  ".join(nieudokumentowane)
        + "\nDodaj zaleznosc do pyproject ALBO wpis do _OPCJONALNE z uzasadnieniem."
    )


def test_wpisy_opcjonalne_nie_sa_martwe():
    """`_OPCJONALNE` nie moze puchnac o wpisy dla importow, ktorych juz nie ma."""
    obecne = set(_importy_zewnetrzne())
    martwe = sorted(set(_OPCJONALNE) - obecne)
    assert not martwe, (
        f"_OPCJONALNE opisuje importy, ktorych nie ma juz w src/: {martwe}. Usun wpisy."
    )


def test_requirements_odwzorowuje_obraz_produkcyjny():
    """requirements.txt == baza + [api] + [ai] + [scraper] (zestaw Dockerfile.jobs).

    CI robi `pip-audit -r requirements.txt`, wiec kazda rozbieznosc to paczka
    lecaca na produkcje BEZ skanu CVE. Tak wypadly z zakresu m.in. beautifulsoup4,
    psycopg2-binary, sentry-sdk i langfuse.
    """
    pj = _pyproject()
    extras = pj["project"].get("optional-dependencies", {})
    oczekiwane = {_nazwa_paczki(w) for w in pj["project"]["dependencies"]}
    for nazwa in ("api", "ai", "scraper"):
        oczekiwane |= {_nazwa_paczki(w) for w in extras.get(nazwa, [])}

    linie = (_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    faktyczne = {
        _nazwa_paczki(ln) for ln in linie
        if ln.strip() and not ln.lstrip().startswith("#")
    }

    brakuje = sorted(oczekiwane - faktyczne)
    nadmiar = sorted(faktyczne - oczekiwane)
    assert not brakuje and not nadmiar, (
        f"requirements.txt rozjechal sie z pyproject.toml.\n"
        f"  brakuje (leci na prod, nie jest skanowane przez pip-audit): {brakuje}\n"
        f"  nadmiar (nie ma tego w obrazie produkcyjnym):               {nadmiar}"
    )
