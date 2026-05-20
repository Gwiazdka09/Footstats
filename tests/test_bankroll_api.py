"""Bankroll API endpoint tests."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_require_auth():
    """Mock auth to return test user_id."""
    def _mock(user_id=1):
        return user_id
    return _mock


@pytest.fixture
def client(mock_require_auth):
    """Create FastAPI test client with mocked auth."""
    from footstats.api.main import app
    with patch("footstats.api.routes.bankroll.require_auth", return_value=1):
        yield TestClient(app)


def test_update_bankroll_new_user(client):
    """Test INSERT new user bankroll without specifying id."""
    with patch("footstats.api.routes.bankroll._connect") as mock_conn:
        mock_db = MagicMock()
        mock_conn.return_value.__enter__.return_value = mock_db
        mock_conn.return_value.__exit__.return_value = None

        response = client.post("/api/bankroll", json={"balance": 100.0})
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["balance"] == 100.0

        # Verify INSERT was called (not checking id)
        mock_db.execute.assert_called()


def test_update_bankroll_existing_user(client):
    """Test ON CONFLICT UPDATE for existing user."""
    with patch("footstats.api.routes.bankroll._connect") as mock_conn:
        mock_db = MagicMock()
        mock_conn.return_value.__enter__.return_value = mock_db
        mock_conn.return_value.__exit__.return_value = None

        response = client.post("/api/bankroll", json={"balance": 250.5})
        assert response.status_code == 200
        assert response.json()["balance"] == 250.5


def test_update_bankroll_negative_balance(client):
    """Test validation: negative balance rejected."""
    response = client.post("/api/bankroll", json={"balance": -50.0})
    assert response.status_code == 400
    assert "ujemne" in response.json()["detail"]


def test_get_bankroll_history(client):
    """Test bankroll history endpoint."""
    with patch("footstats.api.routes.bankroll._connect") as mock_conn:
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            {"timestamp": datetime.now(), "new_balance": 100.0},
        ]
        mock_conn.return_value.__enter__.return_value = mock_db
        mock_conn.return_value.__exit__.return_value = None

        response = client.get("/api/bankroll/history")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
