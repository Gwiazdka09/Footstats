"""test_cloud_draft.py — lite draft System (dry-run default, requests-only, graceful)."""
from __future__ import annotations

import footstats.core.cloud_draft as cd
from footstats.scrapers.bzzoiro import ENV_BZZOIRO


class _ClientOK:
    def __init__(self, klucz):
        pass

    def waliduj(self):
        return (True, "ok")


class _ClientDown:
    def __init__(self, klucz):
        pass

    def waliduj(self):
        return (False, "503")


_WYNIKI = [
    {"gospodarz": "A", "goscie": "B", "liga": "ENG", "data": "2026-08-01", "odds": {"1": 1.8}},
    {"gospodarz": "C", "goscie": "D", "liga": "ITA", "data": "2026-08-01", "odds": {"2": 2.1}},
]


def _patch_pipeline(monkeypatch, build_counter=None):
    monkeypatch.setenv(ENV_BZZOIRO, "fake-key")
    monkeypatch.setattr("footstats.scrapers.bzzoiro.BzzoiroClient", _ClientOK)
    monkeypatch.setattr("footstats.core.quick_picks.szybkie_pewniaczki_2dni",
                        lambda klient, prog, godziny: list(_WYNIKI))
    monkeypatch.setattr("footstats.core.daily_filters._pre_filtruj_ligi", lambda w: list(w))
    monkeypatch.setattr("footstats.core.system_paper.najlepszy_typ", lambda w: (60.0, "1", 1.8))
    monkeypatch.setattr(cd, "_wykryj_model_source", lambda: "poisson-dc")
    if build_counter is not None:
        def _fake_build(*a, **k):
            build_counter["n"] += 1
            return 2
        monkeypatch.setattr("footstats.core.system_paper.build_single_leg_coupons", _fake_build)


def test_dry_run_nie_pisze_do_neon(monkeypatch):
    cnt = {"n": 0}
    _patch_pipeline(monkeypatch, cnt)
    r = cd.generuj_system_draft(dni=2, dry_run=True)
    assert r["ok"] and r["dry_run"] is True
    assert r["candidates"] == 2 and r["would_create"] == 2
    assert r["model_source"] == "poisson-dc"
    assert cnt["n"] == 0  # build_single_leg_coupons NIE wołane w dry-run


def test_live_pisze_przez_build(monkeypatch):
    cnt = {"n": 0}
    _patch_pipeline(monkeypatch, cnt)
    r = cd.generuj_system_draft(dni=2, dry_run=False)
    assert r["ok"] and r["dry_run"] is False
    assert r["created"] == 2 and cnt["n"] == 1


def test_brak_klucza_graceful(monkeypatch):
    monkeypatch.delenv(ENV_BZZOIRO, raising=False)
    r = cd.generuj_system_draft(dry_run=True)
    assert r["ok"] is False and "BZZOIRO" in r["error"]


def test_bzzoiro_down_graceful(monkeypatch):
    monkeypatch.setenv(ENV_BZZOIRO, "fake-key")
    monkeypatch.setattr("footstats.scrapers.bzzoiro.BzzoiroClient", _ClientDown)
    r = cd.generuj_system_draft(dry_run=True)
    assert r["ok"] is False and "niedost" in r["error"].lower()


def test_model_source_flaga_off_to_bzzoiro(monkeypatch):
    """Default (flaga OFF) → quick_picks pomija Poisson (schema mismatch) → bzzoiro-ml."""
    monkeypatch.delenv("QUICK_PICKS_USE_POISSON_CACHE", raising=False)
    assert cd._wykryj_model_source() == "bzzoiro-ml"


def test_model_source_flaga_on_z_danymi_to_poisson(monkeypatch):
    import pandas as pd
    monkeypatch.setenv("QUICK_PICKS_USE_POISSON_CACHE", "1")
    monkeypatch.setattr("footstats.data.historical_loader.load_cached",
                        lambda: pd.DataFrame({"home": ["A"], "away": ["B"], "hg": [1], "ag": [0]}))
    assert cd._wykryj_model_source() == "poisson-dc"


def test_model_source_flaga_on_bez_danych_to_bzzoiro(monkeypatch):
    monkeypatch.setenv("QUICK_PICKS_USE_POISSON_CACHE", "1")
    monkeypatch.setattr("footstats.data.historical_loader.load_cached", lambda: None)
    assert cd._wykryj_model_source() == "bzzoiro-ml"


def test_wyjatek_nie_rzuca(monkeypatch):
    monkeypatch.setenv(ENV_BZZOIRO, "fake-key")
    monkeypatch.setattr("footstats.scrapers.bzzoiro.BzzoiroClient", _ClientOK)

    def _boom(*a, **k):
        raise RuntimeError("API padło")
    monkeypatch.setattr("footstats.core.quick_picks.szybkie_pewniaczki_2dni", _boom)
    monkeypatch.setattr(cd, "_wykryj_model_source", lambda: "bzzoiro-ml")
    r = cd.generuj_system_draft(dry_run=True)
    assert r["ok"] is False and "API padło" in r["error"]
