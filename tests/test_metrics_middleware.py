"""test_metrics_middleware.py — Test Prometheus metrics middleware."""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from unittest.mock import Mock, patch


@pytest.fixture
def app_with_metrics():
    """FastAPI app with metrics middleware."""
    from footstats.api.main import app
    return app


def test_metrics_middleware_records_request(app_with_metrics):
    """Metrics middleware should record request path, status, and duration."""
    client = TestClient(app_with_metrics)

    with patch("footstats.core.logging_config.metrics") as mock_metrics:
        response = client.get("/health")
        assert response.status_code == 200

        mock_metrics.record_request.assert_called()
        call_args = mock_metrics.record_request.call_args
        assert "/health" in call_args[0]
        assert 200 in call_args[0]


def test_metrics_endpoint_returns_dict_or_prometheus(app_with_metrics):
    """GET /metrics should return metrics in dict or Prometheus format."""
    client = TestClient(app_with_metrics)

    response = client.get("/metrics")
    assert response.status_code == 200

    # Should be either dict (JSON) or text (Prometheus format)
    try:
        data = response.json()
        assert isinstance(data, dict)
    except:
        assert isinstance(response.text, str)
        assert len(response.text) > 0


def test_metrics_middleware_on_error(app_with_metrics):
    """Metrics should record 404 and other error responses."""
    client = TestClient(app_with_metrics)

    with patch("footstats.core.logging_config.metrics") as mock_metrics:
        response = client.get("/nonexistent")
        assert response.status_code == 404

        mock_metrics.record_request.assert_called()
        call_args = mock_metrics.record_request.call_args
        assert "/nonexistent" in call_args[0]
        assert 404 in call_args[0]
