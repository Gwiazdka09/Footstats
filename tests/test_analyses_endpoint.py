"""test_analyses_endpoint.py — walidacja wejścia + auth POST/GET /api/analyses/* (BP-01/T1+T2).

T1 (audyt M1): body spoza schematu = 422 (Pydantic na granicy systemu), nie 500 (KeyError).
T2 (audyt H1): oba endpointy wymagają JWT — bez tokenu 401/403, zero palenia tokenów Groq
przez anonimów. Bez sieci/LLM — cache zamockowany, auth przez dependency_overrides.
"""
import pytest
from fastapi.testclient import TestClient

from footstats.api.auth import require_auth
from footstats.api.main import app


@pytest.fixture
def client():
    """Klient ZALOGOWANY — require_auth podmienione na stałego usera 1."""
    app.dependency_overrides[require_auth] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture
def anon_client():
    """Klient BEZ tokenu — realny require_auth."""
    return TestClient(app)


# ── T2: auth (H1) ──────────────────────────────────────────────────────────────

def test_analyses_matches_wymaga_auth(anon_client):
    r = anon_client.get("/api/analyses/matches")
    assert r.status_code in (401, 403)   # HTTPBearer bez nagłówka → 403/401


def test_analyses_llm_wymaga_auth(anon_client):
    r = anon_client.post("/api/analyses/llm", json={"foo": 1})
    assert r.status_code in (401, 403)   # auth PRZED walidacją body


# ── T1: walidacja wejścia (M1) ─────────────────────────────────────────────────

def test_analyses_llm_odrzuca_body_bez_home(client):
    # M1: {"foo": 1} nie ma wymaganych pól karty → 422, nie KeyError/500
    r = client.post("/api/analyses/llm", json={"foo": 1})
    assert r.status_code == 422


def test_analyses_llm_odrzuca_zly_typ_pola(client):
    # model jako string zamiast dict → 422
    r = client.post("/api/analyses/llm", json={
        "home": "France", "away": "Egypt", "model": "nie-dict",
        "home_stats": {}, "away_stats": {},
    })
    assert r.status_code == 422


def test_analyses_llm_przyjmuje_poprawna_karte(client, monkeypatch):
    # Poprawna karta przechodzi walidację; LLM niepotrzebny (cache-hit zamockowany).
    import footstats.api.routes.analyses as an
    monkeypatch.setattr(an, "get_cached_analysis", lambda h: "gotowa analiza")
    card = {
        "home": "France", "away": "Egypt", "data": "2026-07-08",
        "liga": "World Cup 2026", "host": "France",
        "model": {"pw": 56, "pr": 24, "pp": 20, "o25": 54, "bt": 54},
        "home_stats": {"team": "France", "gf_pg": 2.1},
        "away_stats": {"team": "Egypt", "gf_pg": 0.9},
        "injuries_home": [], "injuries_away": [],
        "top_scorers_home": [], "top_scorers_away": [],
        "odds": {"home": 1.4},   # pole nadmiarowe z GUI — ignorowane, nie 422
    }
    r = client.post("/api/analyses/llm", json=card)
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"] == "gotowa analiza"
    assert body["cached"] is True
