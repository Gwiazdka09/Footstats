"""Brak playwrighta nie moze ubijac importu ani kolekcji testow.

ZMIERZONE NA CI 01.09 — `pytest tests/ --cov=...` przerwane po zebraniu 5094
testow, ZERO uruchomionych:

    INTERNALERROR> File ".../src/footstats/scrapers/superbet.py", line 35, in <module>
    INTERNALERROR>     sys.exit(1)
    INTERNALERROR> SystemExit: 1
    Error: Process completed with exit code 3

`superbet.py` wolal `sys.exit(1)` na poziomie MODULU, gdy `import playwright`
sie nie udal. Modul biblioteczny nie moze ubijac interpretera: pytest importuje
go w trakcie kolekcji, wiec jeden brakujacy pakiet opcjonalny zabieral CALY
przebieg, a nie tylko testy, ktore go potrzebuja. Lokalnie playwright jest
zainstalowany, wiec awaria pokazywala sie wylacznie na CI.

Drugi, cichszy: `base_playwright` w galezi `except ImportError` ustawia
`PLAYWRIGHT_OK = False`, ale NIE definiuje `PWError`/`PWTimeout`. Kazdy
`from footstats.scrapers.base_playwright import PWError` (robi tak m.in.
`tests/test_superbet_nie_milczy.py`) konczyl sie wtedy ImportError — awaria
przesunieta o jeden import dalej, nie usunieta.

Brak playwrighta to NORMALNY stan srodowiska CI (nie ma go w lock-u), nie awaria.
Glosny ma byc dopiero moment, w ktorym ktos naprawde chce przegladarki.
"""
from __future__ import annotations

import importlib
import sys

import pytest

_MODULY = ("footstats.scrapers.base_playwright", "footstats.scrapers.superbet")


@pytest.fixture
def bez_playwrighta(monkeypatch):
    """Symuluje srodowisko bez pakietu `playwright` i przeladowuje nasze moduly."""
    for nazwa in [m for m in list(sys.modules) if m.startswith("playwright")]:
        monkeypatch.delitem(sys.modules, nazwa, raising=False)
    # `None` w sys.modules → `import playwright.sync_api` podnosi ImportError,
    # dokladnie jak brak pakietu na CI.
    monkeypatch.setitem(sys.modules, "playwright", None)
    for nazwa in _MODULY:
        monkeypatch.delitem(sys.modules, nazwa, raising=False)
    yield
    # Przywroc czysty stan dla reszty zestawu — inaczej kolejne testy dostana
    # moduly zaimportowane BEZ playwrighta i beda zielone z niewlasciwego powodu.
    for nazwa in _MODULY:
        sys.modules.pop(nazwa, None)


@pytest.mark.parametrize("modul", _MODULY)
def test_import_sie_udaje_bez_playwrighta(bez_playwrighta, modul):
    """To jest ta wlasciwosc, ktorej brak wywalil kolekcje na CI."""
    m = importlib.import_module(modul)

    assert m is not None


@pytest.mark.parametrize("modul", _MODULY)
def test_import_nie_wola_sys_exit(bez_playwrighta, modul):
    """SystemExit nie dziedziczy po Exception — `except ImportError` go nie zlapie."""
    try:
        importlib.import_module(modul)
    except SystemExit as e:
        pytest.fail(f"{modul} wywolal sys.exit({e.code}) przy imporcie")


@pytest.mark.parametrize("nazwa", ["PWError", "PWTimeout"])
def test_typy_bledow_istnieja_takze_bez_pakietu(bez_playwrighta, nazwa):
    """`except (PWTimeout, PWError)` w kodzie musi sie skompilowac bez playwrighta."""
    bp = importlib.import_module("footstats.scrapers.base_playwright")

    typ = getattr(bp, nazwa, None)
    assert typ is not None, f"{nazwa} niezdefiniowany — `from ... import {nazwa}` padnie"
    assert isinstance(typ, type) and issubclass(typ, BaseException), (
        f"{nazwa} = {typ!r} nie jest klasa wyjatku, wiec nie nadaje sie do `except`"
    )


def test_flaga_mowi_ze_playwrighta_nie_ma(bez_playwrighta):
    bp = importlib.import_module("footstats.scrapers.base_playwright")

    assert bp.PLAYWRIGHT_OK is False


def test_uzycie_przegladarki_pada_GLOSNO_i_z_instrukcja(bez_playwrighta):
    """Cisza przy imporcie owszem — ale nie przy realnej probie uruchomienia."""
    bp = importlib.import_module("footstats.scrapers.base_playwright")

    with pytest.raises(RuntimeError, match="playwright"):
        with bp.browser_context():
            pass


def test_z_playwrightem_flaga_jest_prawdziwa():
    """Kontrola negatywna: bez tego testy wyzej przechodzilyby takze wtedy,
    gdyby ktos na stale ustawil PLAYWRIGHT_OK=False."""
    pytest.importorskip("playwright")
    sys.modules.pop("footstats.scrapers.base_playwright", None)
    bp = importlib.import_module("footstats.scrapers.base_playwright")

    assert bp.PLAYWRIGHT_OK is True
