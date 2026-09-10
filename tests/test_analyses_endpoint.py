"""test_analyses_endpoint.py — auth GET /api/analyses/matches (BP-01/T2) i brak
endpointu LLM (usunięty 10.09.2026 razem z przyciskiem „Analiza AI”).
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


# ── 10.09: analiza LLM usunięta ────────────────────────────────────────────────

def test_analiza_llm_nie_istnieje(client):
    """Przycisk „Analiza AI” zniknął z GUI; endpoint palący tokeny Groqa nie
    może zostać osierocony i dostępny dla każdego zalogowanego."""
    r = client.post("/api/analyses/llm", json={"home": "France", "away": "Egypt"})
    assert r.status_code in (404, 405)
