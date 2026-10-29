"""Opis meczu na produkcji (25.10): dwie przyczyny pustego opisu, których testy
jednostkowe na atrapach nie widziały — timeout middleware i brak Groqa w obrazie API."""
from pathlib import Path

from footstats.api.main import _LONG_RUNNING_PATHS

ROOT = Path(__file__).resolve().parents[1]


def test_opis_meczu_ma_dlugi_timeout():
    # Pierwsze żądanie ładuje zbiór historyczny (~18 s) — przy 10 s było 504.
    assert "/api/admin/opis-meczu" in _LONG_RUNNING_PATHS


def test_obraz_api_ma_paczke_groq():
    lock = (ROOT / "requirements-api.lock").read_text(encoding="utf-8")
    assert any(linia.startswith("groq==") for linia in lock.splitlines())


def test_cd_daje_serwisowi_klucz_groq():
    cd = (ROOT / ".github" / "workflows" / "cd.yml").read_text(encoding="utf-8")
    linie = cd.splitlines()
    # Cała linia, nie podciąg: `secrets: |` pada też w komentarzu nad blokiem.
    start = next(i for i, linia in enumerate(linie) if linia.strip() == "secrets: |")
    koniec = next(i for i, linia in enumerate(linie)
                  if i > start and "secrets_update_strategy" in linia)
    blok = linie[start + 1:koniec]
    assert "GROQ_API_KEY=GROQ_API_KEY:latest" in (linia.strip() for linia in blok)
    # `secrets: |` to literal scalar — linia z `#` w bloku wywala deploy (24.08).
    assert not any(linia.strip().startswith("#") for linia in blok)


def test_analizy_meczow_maja_dlugi_timeout():
    # Od paginacji Bzzoiro (25.10) karta „Analiz” to ~35 meczów × 4 zapytania DB.
    assert "/api/analyses/matches" in _LONG_RUNNING_PATHS


def test_kreator_kuponu_ma_dlugi_timeout():
    # Kilka stron Bzzoiro na zimnym starcie nie mieści się w 10 s.
    assert "/api/matches/today" in _LONG_RUNNING_PATHS
    assert "/api/coupons/daily-proposals" in _LONG_RUNNING_PATHS
