"""Testy regresji hardeningu bezpieczeństwa (OWASP API Top 10).

Blokują powrót: leaku danych biznesowych na publicznym /health (API3),
braku nagłówków bezpieczeństwa (API8), ekspozycji schematu /openapi w prod (API8).
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-long!!")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-chars-long!!!")
os.environ.setdefault("FOOTBALL_API_KEY", "test")
os.environ.setdefault("APISPORTS_KEY", "test")
os.environ.setdefault("BZZOIRO_KEY", "test")
os.environ.setdefault("GROQ_API_KEY", "test")

from fastapi.testclient import TestClient

from footstats.api.main import app

client = TestClient(app)


# ── API3: /health nie wystawia danych biznesowych ──────────────────────────
def test_health_nie_wystawia_danych_biznesowych():
    data = client.get("/health").json()
    # Wrażliwe pola (bankroll, accuracy, liczba userów, daty) muszą być usunięte.
    assert "bankroll_pln" not in data
    assert "rolling_accuracy_pct" not in data
    assert "detail" not in data.get("auth", {})  # string z liczbą userów
    assert "last_prediction_date" not in data.get("agent", {})


def test_health_zwraca_tylko_status_wersje_i_booleany():
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert "version" in data
    assert set(data["auth"].keys()) == {"ok"}
    assert set(data["agent"].keys()) == {"ok"}


# ── API8: nagłówki bezpieczeństwa ──────────────────────────────────────────
def test_naglowki_bezpieczenstwa_obecne():
    h = client.get("/health").headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy") == "no-referrer"
    assert "Strict-Transport-Security" in h


# ── API8: schemat API wyłączony w produkcji (ENV domyślnie 'production') ────
def test_openapi_schema_wylaczony_w_prod():
    # Test uruchamia się bez ENV=dev → app zbudowane z openapi_url=None.
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
