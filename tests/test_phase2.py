import os
import pytest
from fastapi.testclient import TestClient
from footstats.api.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_spa_root_returns_html():
    """GET / serves index.html from dist/."""
    resp = client.get("/", follow_redirects=True)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_spa_assets_served():
    """Static JS asset from dist/assets/ is accessible."""
    dist = "src/footstats/gui/dist/assets"
    if not os.path.exists(dist):
        pytest.skip("dist/ not built yet")
    asset = next((f for f in os.listdir(dist) if f.endswith(".js")), None)
    if asset is None:
        pytest.skip("no JS assets in dist/")
    resp = client.get(f"/assets/{asset}")
    assert resp.status_code == 200
