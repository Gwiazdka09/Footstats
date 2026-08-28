"""Kolektor kursow nie ma prawa wywrocic potoku produkcyjnego.

`footstats-final` uruchamia `python -m footstats.daily_agent --faza final`
(patrz scripts/run_job.sh). Pilot jest tam wpiety jako eksperyment, wiec jego
awaria musi byc GLOSNA, ale nieblokujaca — to jedyne miejsce w projekcie, gdzie
polkniecie wyjatku jest zamierzone.
"""
from __future__ import annotations

import pytest

from footstats.daily_agent import _zbierz_migawke_kursow


@pytest.fixture(autouse=True)
def _bez_migracji(monkeypatch):
    """Kolektor wola `run_migrations()` (patrz `odds_store.zbierz_i_zapisz`).
    Bez zaslepienia bilby po realnej bazie — regula `.claude/rules/tests-no-prod.md`.
    Test `test_kolektor_upewnia_sie_ze_migracje_poszly` nadpisuje to wlasnym
    szpiegiem, zeby sprawdzic, ze wywolanie faktycznie nastepuje."""
    import footstats.db.migrations as mig
    monkeypatch.setattr(mig, "run_migrations", lambda: None)


def _zamiecione(wiersze, zatrzymany=False, ligi=3):
    return {"ligi": ligi, "wierszy": len(wiersze), "kredyty": 400,
            "zatrzymany_przez_kredyty": zatrzymany, "wiersze": wiersze}


def test_wyjatek_kolektora_nie_wychodzi_na_zewnatrz(monkeypatch, caplog):
    import footstats.scrapers.odds_snapshot as snap

    def _wybuch(*a, **kw):
        raise RuntimeError("API padlo")

    monkeypatch.setattr(snap, "zamiataj_pilota", _wybuch)
    with caplog.at_level("ERROR"):
        wynik = _zbierz_migawke_kursow()
    assert wynik is None
    assert "migawka kursow" in caplog.text.lower(), "awaria musi byc GLOSNA"


def test_wyjatek_magazynu_tez_nie_wychodzi(monkeypatch, caplog):
    """Nie tylko kolektor moze paść — zapis do bazy tak samo."""
    import footstats.core.odds_store as store
    import footstats.scrapers.odds_snapshot as snap

    monkeypatch.setattr(snap, "zamiataj_pilota", lambda **kw: _zamiecione([{"a": 1}]))

    def _wybuch(*a, **kw):
        raise RuntimeError("baza padla")

    monkeypatch.setattr(store, "zapisz_migawke", _wybuch)
    with caplog.at_level("ERROR"):
        assert _zbierz_migawke_kursow() is None


def test_dry_run_przekazywany_do_magazynu(monkeypatch):
    import footstats.core.odds_store as store
    import footstats.scrapers.odds_snapshot as snap

    zapisy = []
    monkeypatch.setattr(snap, "zamiataj_pilota", lambda **kw: _zamiecione([{"a": 1}]))
    monkeypatch.setattr(store, "zapisz_migawke",
                        lambda w, **kw: zapisy.append(kw) or {"zapisane": 0})
    _zbierz_migawke_kursow(dry_run=True)
    assert zapisy and zapisy[0]["dry_run"] is True


def test_sciezka_szczesliwa_przekazuje_wiersze_do_magazynu(monkeypatch):
    import footstats.core.odds_store as store
    import footstats.scrapers.odds_snapshot as snap

    przekazane = {}
    monkeypatch.setattr(snap, "zamiataj_pilota",
                        lambda **kw: _zamiecione([{"a": 1}, {"b": 2}]))
    monkeypatch.setattr(store, "zapisz_migawke",
                        lambda w, **kw: przekazane.update(n=len(w)) or {"zapisane": len(w)})
    wynik = _zbierz_migawke_kursow()
    assert przekazane["n"] == 2
    assert wynik["zapisane"] == 2


def test_przerwanie_przez_prog_kredytowy_jest_zglaszane(monkeypatch, caplog):
    """Pula 500/mies. jest dzielona z produkcyjna sciezka kursow. Cisza tutaj
    wygladalaby identycznie jak 'nie bylo czego zbierac'."""
    import footstats.core.odds_store as store
    import footstats.scrapers.odds_snapshot as snap

    monkeypatch.setattr(snap, "zamiataj_pilota",
                        lambda **kw: _zamiecione([{"a": 1}], zatrzymany=True, ligi=1))
    monkeypatch.setattr(store, "zapisz_migawke", lambda w, **kw: {"zapisane": 1})
    with caplog.at_level("WARNING"):
        _zbierz_migawke_kursow()
    assert "prog kredytowy" in caplog.text.lower()


def test_kolektor_upewnia_sie_ze_migracje_poszly(monkeypatch):
    """Kolektor jest wolany w main() WCZESNIEJ niz tamtejsze run_migrations(),
    wiec pierwszego dnia tabeli by nie bylo i cala doba przepadlaby na blad
    zapisu. Migracje sa idempotentne, wiec taniej upewnic sie tutaj."""
    import footstats.core.odds_store as store
    import footstats.db.migrations as mig
    import footstats.scrapers.odds_snapshot as snap

    wolania = []
    monkeypatch.setattr(mig, "run_migrations", lambda: wolania.append("mig"))
    monkeypatch.setattr(snap, "zamiataj_pilota", lambda **kw: _zamiecione([{"a": 1}]))
    monkeypatch.setattr(store, "zapisz_migawke", lambda w, **kw: {"zapisane": 1})
    _zbierz_migawke_kursow()
    assert wolania == ["mig"], "migracje musza pojsc przed zapisem migawki"

