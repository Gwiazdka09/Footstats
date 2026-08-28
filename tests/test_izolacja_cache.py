"""Katalogi cache nie mogą być współdzielone przez dwa równoległe przebiegi.

POWÓD (26.08 → 28.08): suita bywała czerwona losowo, bez związku ze zmianą
w kodzie. Hipoteza „zanieczyszczenie kolejnością" odpadła — `pytest-randomly`
nie jest zainstalowany, więc kolejność testów jest deterministyczna. Została
hipoteza DWÓCH RÓWNOLEGŁYCH PRZEBIEGÓW, i ta ma poszlakę wprost w repo:
fikstura `clean_checkpoint_dir` w `tests/test_checkpoint.py` powstała dokładnie
dlatego, że „dwa równoległe przebiegi pytest (np. dwa agenty naraz) kasowały
sobie nawzajem pliki" w `cache/checkpoints`.

`CHECKPOINT_DIR` dało się załatać, bo czyta się przez `os.getenv` w czasie
wywołania. Reszta katalogów cache była wyliczana PRZY IMPORCIE jako stała
modułowa — żadna zmienna środowiskowa ich nie przekierowywała, więc dwa procesy
pytest pisały i kasowały te same pliki.

Te testy pilnują dwóch rzeczy naraz:
  1. `FOOTSTATS_CACHE_ROOT` realnie przekierowuje KAŻDY katalog cache,
  2. conftest ustawia go na katalog unikalny dla procesu — bo sam mechanizm
     bez tego kroku niczego nie izoluje.
"""
from __future__ import annotations

import importlib
import os
import re
from pathlib import Path

import pytest

KORZEN_REPO = Path(__file__).resolve().parents[1]

# (moduł, nazwa atrybutu ze ścieżką) — każdy katalog cache w projekcie.
# Dopisujesz tu RAZEM z nowym katalogiem cache, nigdy później.
MODULY_CACHE = [
    ("footstats.utils.cache", "CACHE_DIR"),
    ("footstats.utils.cache_evict", "_CACHE_DIR"),
    ("footstats.scrapers.kursy", "CACHE_DIR"),
    ("footstats.scrapers.sts_kursy", "CACHE_DIR"),
    ("footstats.scrapers.sts_inspiracje", "CACHE_DIR"),
    ("footstats.scrapers.superbet", "CACHE_DIR"),
    ("footstats.scrapers.enriched", "CACHE_DIR"),
    ("footstats.scrapers.form_scraper", "CACHE_DIR"),
    ("footstats.scrapers.sofascore_odds", "CACHE_DIR"),
    ("footstats.scrapers.understat_xg", "_CACHE_DIR"),
    ("footstats.scrapers.flashscore_results", "CACHE_DIR"),
    ("footstats.scrapers.sources.flashscore_source", "CACHE_DIR"),
    ("footstats.scrapers.sources.thesportsdb_source", "CACHE_DIR"),
    ("footstats.scrapers.sources.footballdata_source", "CACHE_DIR"),
    ("footstats.data.context_scraper", "CACHE_DIR"),
]


def _sciezka(modul: str, atrybut: str) -> Path:
    return Path(getattr(importlib.import_module(modul), atrybut))


# ── 1. mechanizm: env przekierowuje wszystko ────────────────────────────────

@pytest.mark.parametrize(("modul", "atrybut"), MODULY_CACHE, ids=lambda v: v)
def test_katalog_cache_lezy_pod_korzeniem_z_env(modul: str, atrybut: str):
    """Sedno. Katalog liczony przy imporcie jako stała modułowa NIE DA SIĘ
    przekierować — dwa procesy pytest dzielą wtedy te same pliki."""
    korzen = os.environ.get("FOOTSTATS_CACHE_ROOT")
    assert korzen, "conftest nie ustawił FOOTSTATS_CACHE_ROOT"

    sciezka = _sciezka(modul, atrybut).resolve()
    assert sciezka.is_relative_to(Path(korzen).resolve()), (
        f"{modul}.{atrybut} = {sciezka} — poza korzeniem cache tego procesu."
        " Dwa rownolegle przebiegi pytest beda sie tu nadpisywac."
    )


def test_konfiguracje_playwright_tez_sa_przekierowane():
    """`SiteConfig.cache_dir` to domyślna wartość pola dataclassy — wyliczana
    przy imporcie tak samo jak stała modułowa i tak samo łatwa do przeoczenia."""
    korzen = Path(os.environ["FOOTSTATS_CACHE_ROOT"]).resolve()
    from footstats.scrapers import base_playwright

    for konfig in (base_playwright.STS_CONFIG, base_playwright.SUPERBET_CONFIG):
        assert Path(konfig.cache_dir).resolve().is_relative_to(korzen), (
            f"{konfig.name}: cache_dir={konfig.cache_dir} poza korzeniem cache"
        )


def test_checkpointy_tez_ida_pod_ten_sam_korzen():
    """`CHECKPOINT_DIR` miał własny mechanizm zanim powstał wspólny korzeń.
    Ma nadal działać, ale domyślnie lądować w tym samym izolowanym miejscu."""
    korzen = Path(os.environ["FOOTSTATS_CACHE_ROOT"]).resolve()
    from footstats.core import checkpoint

    assert checkpoint._checkpoint_dir().resolve().is_relative_to(korzen)


def test_wlasny_checkpoint_dir_dalej_wygrywa(monkeypatch, tmp_path):
    """Regres: `clean_checkpoint_dir` w test_checkpoint.py opiera się na tym,
    że `CHECKPOINT_DIR` nadpisuje wszystko inne."""
    monkeypatch.setenv("CHECKPOINT_DIR", str(tmp_path))
    from footstats.core import checkpoint

    assert checkpoint._checkpoint_dir() == tmp_path


# ── 2. helper ───────────────────────────────────────────────────────────────

def test_helper_bez_env_zachowuje_domyslna_sciezke(monkeypatch, tmp_path):
    """Produkcja nie ustawia tej zmiennej — bez niej ścieżki muszą zostać
    dokładnie tam, gdzie były, łącznie z modułami kotwiczonymi do `__file__`."""
    from footstats.utils import paths

    monkeypatch.delenv("FOOTSTATS_CACHE_ROOT", raising=False)
    assert paths.katalog_cache("kursy") == Path("cache") / "kursy"

    wlasny = tmp_path / "gdzies" / "indziej"
    assert paths.katalog_cache("kursy", domyslny=wlasny) == wlasny


def test_helper_z_env_ignoruje_domyslna_sciezke(monkeypatch, tmp_path):
    from footstats.utils import paths

    monkeypatch.setenv("FOOTSTATS_CACHE_ROOT", str(tmp_path))
    assert paths.katalog_cache("kursy", domyslny=Path("/gdzie/indziej")) == tmp_path / "kursy"
    assert paths.korzen_cache() == tmp_path


def test_pusty_env_nie_przekierowuje_do_katalogu_biezacego(monkeypatch):
    """`FOOTSTATS_CACHE_ROOT=""` to nie jest „korzeń = CWD" — to brak wartości.
    Bez tego `Path("") / "kursy"` dałoby ścieżkę względną i cichy rozjazd."""
    from footstats.utils import paths

    monkeypatch.setenv("FOOTSTATS_CACHE_ROOT", "")
    assert paths.katalog_cache("kursy") == Path("cache") / "kursy"


# ── 3. conftest realnie izoluje ─────────────────────────────────────────────

def test_korzen_cache_jest_poza_repo():
    """Gdyby korzeń wskazywał `<repo>/cache`, mechanizm istniałby, a izolacji
    nadal by nie było — oba przebiegi trafiałyby w to samo miejsce."""
    korzen = Path(os.environ["FOOTSTATS_CACHE_ROOT"]).resolve()
    assert not korzen.is_relative_to(KORZEN_REPO), (
        f"korzen cache {korzen} lezy w repo — rownolegle przebiegi go dziela"
    )


def test_korzen_cache_jest_unikalny_dla_procesu():
    korzen = Path(os.environ["FOOTSTATS_CACHE_ROOT"])
    assert str(os.getpid()) in korzen.name, (
        f"{korzen.name} nie zawiera PID — dwa procesy dostana ten sam katalog"
    )


# ── 4. ratchet: nowy katalog cache nie wejdzie tylnymi drzwiami ─────────────

def test_zaden_modul_nie_tworzy_sciezki_cache_z_palca():
    """Cały mechanizm obchodzi jedna linijka `Path("cache/cokolwiek")`.
    Wyjątek: `utils/paths.py`, czyli miejsce, w którym ta ścieżka POWSTAJE."""
    wzor = re.compile(r"""Path\(\s*["'](?:\./)?cache[/"']""")
    winowajcy = []
    for plik in (KORZEN_REPO / "src" / "footstats").rglob("*.py"):
        if plik.name == "paths.py":
            continue
        tekst = plik.read_text(encoding="utf-8")
        for nr, linia in enumerate(tekst.splitlines(), 1):
            if wzor.search(linia):
                winowajcy.append(f"{plik.relative_to(KORZEN_REPO)}:{nr}")

    assert not winowajcy, (
        "katalog cache liczony z palca zamiast przez `utils.paths.katalog_cache`"
        f" — nie da sie go przekierowac: {winowajcy}"
    )


def test_kazdy_katalog_cache_jest_na_liscie():
    """Lista wyżej jest tylko tak dobra, jak jej kompletność. Każde wołanie
    `katalog_cache(...)` w src musi mieć swój wpis w `MODULY_CACHE`."""
    zadeklarowane = {modul for modul, _ in MODULY_CACHE}
    zadeklarowane |= {
        "footstats.scrapers.base_playwright",   # osobny test (dataclass)
        "footstats.core.checkpoint",            # osobny test (wlasny env)
        "footstats.utils.logging",              # sciezki lokalne w funkcjach
    }
    brakujace = []
    for plik in (KORZEN_REPO / "src" / "footstats").rglob("*.py"):
        if plik.name == "paths.py":
            continue
        if "katalog_cache(" not in plik.read_text(encoding="utf-8"):
            continue
        modul = "footstats." + str(
            plik.relative_to(KORZEN_REPO / "src" / "footstats").with_suffix("")
        ).replace(os.sep, ".")
        if modul not in zadeklarowane:
            brakujace.append(modul)

    assert not brakujace, f"katalogi cache poza testem izolacji: {brakujace}"
