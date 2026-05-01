import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-long!!")
os.environ.setdefault("FOOTBALL_API_KEY", "test")
os.environ.setdefault("APISPORTS_KEY", "test")
os.environ.setdefault("BZZOIRO_KEY", "test")
os.environ.setdefault("GROQ_API_KEY", "test")

from fastapi.testclient import TestClient

from footstats.api.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body():
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_no_crash_without_sentry_dsn():
    """Sentry DSN optional — app must boot without it."""
    response = client.get("/health")
    assert response.status_code == 200
