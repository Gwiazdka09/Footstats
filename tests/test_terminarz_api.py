"""test_terminarz_api.py — endpointy zakładki „Terminarz".

Źródła są darmowe i bez klucza, ale to nadal ruch sieciowy — w testach mockujemy
warstwę scrapera (reguła: testy nie biją po zewnętrznych źródłach).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from footstats.api.auth import require_auth
from footstats.api.main import app
from footstats.core.response_cache import clear_response_cache

_MECZE = [
    {"data": "2026-09-20", "godzina": "17:30", "kolejka": "Matchday 5",
     "gospodarz": "Arsenal FC", "goscie": "Chelsea FC", "rozegrany": False,
     "wynik": None, "liga": "Premier League", "sezon": "2026-27"},
    {"data": "2025-08-16", "godzina": "20:00", "kolejka": "Matchday 1",
     "gospodarz": "Man Utd", "goscie": "Fulham", "rozegrany": True,
     "wynik": "1-0", "liga": "Premier League", "sezon": "2026-27"},
]


@pytest.fixture
def klient():
    # Endpointy mają cache 6h (terminarz zmienia się rzadko), więc bez czyszczenia
    # pierwszy test zatruwałby kolejne swoim wynikiem.
    clear_response_cache()
    app.dependency_overrides[require_auth] = lambda: 1
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    clear_response_cache()


def test_lista_lig_ma_nazwy_i_kraje(klient):
    r = klient.get("/api/terminarz/ligi")
    assert r.status_code == 200
    dane = r.json()
    assert dane["ligi"], "lista lig nie może być pusta"
    assert {"kod", "nazwa", "kraj"} <= set(dane["ligi"][0])


def test_terminarz_ligi_zwraca_tylko_nadchodzace(klient):
    with patch("footstats.api.routes.terminarz.pobierz_terminarz", return_value=_MECZE):
        r = klient.get("/api/terminarz/en.1?tylko_nadchodzace=true")

    assert r.status_code == 200
    dane = r.json()
    assert dane["liga"] == "Premier League"
    assert len(dane["mecze"]) == 1
    assert dane["mecze"][0]["gospodarz"] == "Arsenal FC"
    assert dane["meczow_total"] == 2
    assert dane["meczow_rozegranych"] == 1


def test_terminarz_ligi_moze_zwrocic_wszystko(klient):
    with patch("footstats.api.routes.terminarz.pobierz_terminarz", return_value=_MECZE):
        r = klient.get("/api/terminarz/en.1?tylko_nadchodzace=false")
    assert len(r.json()["mecze"]) == 2


def test_nieznana_liga_to_404(klient):
    assert klient.get("/api/terminarz/nie.ma").status_code == 404


def test_brak_danych_to_pusty_stan_nie_blad(klient):
    """Niedostępne źródło = pusta zakładka, nie 500 — GUI ma co pokazać."""
    with patch("footstats.api.routes.terminarz.pobierz_terminarz", return_value=[]):
        r = klient.get("/api/terminarz/en.1")
    assert r.status_code == 200
    assert r.json()["mecze"] == []
    assert r.json()["start_sezonu"] is None


def test_przeglad_zwraca_liste_lig(klient):
    przeglad = [{"kod": "en.1", "nazwa": "Premier League", "kraj": "Anglia",
                 "sezon": "2026-27", "start_sezonu": "2026-08-14",
                 "dni_do_startu": 16, "meczow_total": 380,
                 "meczow_rozegranych": 0, "nastepne": _MECZE[:1]}]
    with patch("footstats.api.routes.terminarz.przeglad_lig", return_value=przeglad):
        r = klient.get("/api/terminarz?limit_na_lige=2")

    assert r.status_code == 200
    assert r.json()["liczba_lig"] == 1
    assert r.json()["ligi"][0]["dni_do_startu"] == 16


def test_limit_poza_zakresem_odrzucony(klient):
    assert klient.get("/api/terminarz?limit_na_lige=99").status_code == 422


def test_endpointy_wymagaja_auth():
    """Bez tokenu ma być 401 — zakładka jest za logowaniem jak reszta."""
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        assert c.get("/api/terminarz").status_code == 401
        assert c.get("/api/terminarz/ligi").status_code == 401
