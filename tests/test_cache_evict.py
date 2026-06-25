"""test_cache_evict.py — eviction starych plików cache (prod /cron/evict-cache)."""
from __future__ import annotations

import os
import time

import footstats.utils.cache_evict as ce


def _plik(path, wiek_dni: float) -> None:
    """Tworzy plik i ustawia jego mtime na `wiek_dni` wstecz."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    stary = time.time() - wiek_dni * 86400
    os.utime(path, (stary, stary))


def test_brak_katalogu_zwraca_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "_CACHE_DIR", tmp_path / "nie_ma")
    assert ce.evict_old_cache(max_days=30) == 0


def test_usuwa_stare_zostawia_nowe(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "_CACHE_DIR", tmp_path)
    _plik(tmp_path / "stary.json", wiek_dni=40)
    _plik(tmp_path / "nowy.json", wiek_dni=1)
    deleted = ce.evict_old_cache(max_days=30)
    assert deleted == 1
    assert not (tmp_path / "stary.json").exists()
    assert (tmp_path / "nowy.json").exists()


def test_dry_run_liczy_nie_usuwa(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "_CACHE_DIR", tmp_path)
    _plik(tmp_path / "stary.json", wiek_dni=40)
    deleted = ce.evict_old_cache(max_days=30, dry_run=True)
    assert deleted == 1
    assert (tmp_path / "stary.json").exists()  # dry-run nie kasuje


def test_zagniezdzone_pliki_rglob(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "_CACHE_DIR", tmp_path)
    _plik(tmp_path / "a" / "b" / "stary.html", wiek_dni=99)
    _plik(tmp_path / "a" / "nowy.html", wiek_dni=2)
    assert ce.evict_old_cache(max_days=30) == 1
    assert not (tmp_path / "a" / "b" / "stary.html").exists()


def test_prog_graniczny(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "_CACHE_DIR", tmp_path)
    _plik(tmp_path / "tuz_przed.json", wiek_dni=29)
    _plik(tmp_path / "tuz_po.json", wiek_dni=31)
    assert ce.evict_old_cache(max_days=30) == 1  # tylko 31-dniowy
