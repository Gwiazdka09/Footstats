"""Katalog cache dyskowego API-Football musi powstawac takze bez rodzica.

W obrazie Cloud Run nie ma `cache/`, wiec `mkdir(exist_ok=True)` rzucal ENOENT
i logowal nieprawdziwe ostrzezenie o zuzyciu budzetu API.
"""
from __future__ import annotations

from footstats.utils import cache as uc


def test_af_ensure_dir_tworzy_brakujacego_rodzica(monkeypatch, tmp_path):
    cel = tmp_path / "cache" / "api_football"  # `cache/` nie istnieje
    monkeypatch.setattr(uc, "CACHE_DIR", cel)
    monkeypatch.setattr(uc, "_zgloszono_brak_katalogu", False)

    uc._af_ensure_dir()

    assert cel.is_dir()
    assert uc._zgloszono_brak_katalogu is False
