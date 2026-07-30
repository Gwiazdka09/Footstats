"""test_env_documentation.py — `.env.example` musi opisywać KAŻDĄ zmienną, którą czyta kod.

Po co ten test istnieje (incydent 2026-07-29): serwis Cloud Run przez 9 dni nie miał
`BZZOIRO_KEY`, więc `/cron/draft` zwracał `{'ok': False}` przy HTTP 200 i System
paper-trading nie utworzył ani jednego kuponu. Nikt nie wiedział, że ta zmienna jest
wymagana — nie było jej w `.env.example`. Audyt wykazał wtedy **39** takich zmiennych,
w tym wszystkie flagi sterujące modelem (`USE_DIXON_COLES`, `SELECTION_MIN_CONF`,
`QUICK_PICKS_USE_POISSON_CACHE`, `CALIBRATION_ENABLED`).

Test pilnuje obu kierunków:
  * kod czyta zmienną, której nie ma w `.env.example` → nikt jej nie skonfiguruje,
  * `.env.example` obiecuje zmienną, której nikt nie czyta → dokumentacja kłamie
    (tak było z `LOG_LEVEL`, który w kodzie jest zwykłą stałą).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KATALOGI = ("src", "scripts")

# Zmienne dostarczane przez system/platformę — nie konfigurujemy ich w .env.
SYSTEMOWE = {
    "PORT", "PATH", "HOME", "ENV", "PYTHONPATH", "JOB_PHASE", "K_SERVICE", "CI",
    "GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "TERM", "TMPDIR",
    "TEMP", "PYTEST_CURRENT_TEST", "FOOTSTATS_ALLOW_PROD_DB",
}


def _pliki_zrodlowe() -> list[Path]:
    return [p for d in KATALOGI for p in (ROOT / d).rglob("*.py")]


def _stale_env(pliki: list[Path]) -> dict[str, str]:
    """Stałe typu `ENV_BZZOIRO = "BZZOIRO_KEY"` — kod czyta je pośrednio."""
    stale: dict[str, str] = {}
    for p in pliki:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"""^(_?[A-Z][A-Z0-9_]*)\s*=\s*["']([A-Z][A-Z0-9_]{2,})["']""", txt, re.M):
            stale[m.group(1)] = m.group(2)
    return stale


def czytane_przez_kod() -> dict[str, set[str]]:
    """Nazwy zmiennych środowiskowych realnie odczytywanych w src/ i scripts/."""
    pliki = _pliki_zrodlowe()
    stale = _stale_env(pliki)
    czytane: dict[str, set[str]] = {}

    for p in pliki:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        rel = p.relative_to(ROOT).as_posix()

        # os.getenv("X") / os.environ.get("X") / os.environ["X"]
        for wzor in (
            r"""(?:os\.getenv|os\.environ\.get|environ\.get)\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""",
            r"""os\.environ\[\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*\]""",
        ):
            for m in re.finditer(wzor, txt):
                czytane.setdefault(m.group(1), set()).add(rel)

        # odczyt przez stałą: os.getenv(ENV_BZZOIRO)
        for m in re.finditer(r"""(?:os\.getenv|os\.environ\.get)\(\s*(_?[A-Z][A-Z0-9_]{2,})\s*[,)]""", txt):
            if (realna := stale.get(m.group(1))):
                czytane.setdefault(realna, set()).add(rel)

        # dotenv_values(...) -> env.get("X"); ograniczone do plików, które tego używają,
        # żeby nie łapać zwykłych dict.get w całym repo.
        if "dotenv_values" in txt:
            for m in re.finditer(r"""\.get\(\s*["']([A-Z][A-Z0-9_]{2,})["']""", txt):
                czytane.setdefault(m.group(1), set()).add(rel)

        # SiteConfig(login_env="STS_LOGIN", password_env="STS_HASLO")
        for m in re.finditer(r"""(?:login_env|password_env)\s*=\s*["']([A-Z][A-Z0-9_]+)["']""", txt):
            czytane.setdefault(m.group(1), set()).add(rel)

    return {k: v for k, v in czytane.items() if k not in SYSTEMOWE}


def udokumentowane() -> set[str]:
    """
    Nazwy z `.env.example`.

    Liczy też wpisy zakomentowane, ale WYŁĄCZNIE w formie `# NAZWA=` — inaczej
    regex łapałby nagłówki sekcji ("# BAZA DANYCH") i słowa z opisów ("# UWAGA")
    jako nazwy zmiennych. Sekcja „USUNIĘTE" na końcu pliku wymienia nazwy bez `=`,
    więc świadomie NIE liczy się jako dokumentacja żywej zmiennej.
    """
    plik = ROOT / ".env.example"
    tekst = plik.read_text(encoding="utf-8", errors="ignore")
    jawne = set(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)=", tekst, re.M))
    zakomentowane = set(re.findall(r"^#\s*([A-Za-z_][A-Za-z0-9_]*)=", tekst, re.M))
    return jawne | zakomentowane


def test_env_example_opisuje_wszystko_co_kod_czyta():
    braki = sorted(set(czytane_przez_kod()) - udokumentowane())
    assert not braki, (
        "Kod czyta zmienne środowiskowe, których NIE MA w .env.example:\n"
        + "\n".join(f"  {k}  ({', '.join(sorted(czytane_przez_kod()[k])[:2])})" for k in braki)
        + "\n\nDopisz je do .env.example — inaczej nikt ich nie skonfiguruje na deployu."
    )


def test_env_example_nie_obiecuje_martwych_zmiennych():
    """Wpis w `.env.example`, którego nikt nie czyta, to kłamiąca dokumentacja."""
    martwe = sorted(udokumentowane() - set(czytane_przez_kod()) - SYSTEMOWE)
    assert not martwe, (
        ".env.example dokumentuje zmienne, których ŻADEN kod nie czyta:\n"
        + "\n".join(f"  {k}" for k in martwe)
        + "\n\nUsuń je albo wskaż konsumenta. Nieużywany sekret to zbędne ryzyko."
    )


@pytest.mark.parametrize("krytyczna", [
    "DATABASE_URL", "JWT_SECRET", "BZZOIRO_KEY", "APISPORTS_KEY",
    "FOOTBALL_API_KEY", "GROQ_API_KEY", "CRON_SECRET",
])
def test_krytyczne_zmienne_sa_udokumentowane(krytyczna):
    """Zmienne, bez których pipeline stoi. Regresja po incydencie 07-29."""
    assert krytyczna in udokumentowane(), f"{krytyczna} zniknęło z .env.example"
