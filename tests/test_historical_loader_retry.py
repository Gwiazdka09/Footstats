"""Ponowienia pobrania CSV w `_get` (incydent 19.10: read timeouty wywracały odświeżenie)."""
from __future__ import annotations

import pytest
import requests

from footstats.data import historical_loader as hl

URL = "https://example.test/plik.csv"


def _odp(status: int, tresc: bytes = b"a,b\n1,2\n") -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = tresc
    r.url = URL
    return r


@pytest.fixture()
def spiace(monkeypatch):
    """Podmienia sleep — zero realnego czekania; zwraca listę przerw."""
    przerwy: list[float] = []
    monkeypatch.setattr(hl.time, "sleep", lambda s: przerwy.append(s))
    return przerwy


def _mock_get(monkeypatch, kolejne: list):
    wywolania: list[str] = []

    def _get(url, **kw):
        wywolania.append(url)
        w = kolejne[len(wywolania) - 1]
        if isinstance(w, Exception):
            raise w
        return w

    monkeypatch.setattr(hl.requests, "get", _get)
    return wywolania


def test_timeout_potem_sukces(monkeypatch, spiace):
    wyw = _mock_get(monkeypatch, [requests.Timeout("read"), _odp(200)])
    assert hl._get(URL) == b"a,b\n1,2\n"
    assert len(wyw) == 2
    assert spiace == [2]


def test_trzy_timeouty_daja_none(monkeypatch, spiace, caplog):
    wyw = _mock_get(monkeypatch, [requests.Timeout("x")] * 3)
    with caplog.at_level("WARNING"):
        assert hl._get(URL) is None
    assert len(wyw) == 3
    assert spiace == [2, 5]
    assert any("HTTP error" in m for m in caplog.messages)


def test_404_bez_ponowien(monkeypatch, spiace):
    wyw = _mock_get(monkeypatch, [_odp(404)])
    assert hl._get(URL) is None
    assert len(wyw) == 1
    assert spiace == []


def test_503_potem_200(monkeypatch, spiace):
    wyw = _mock_get(monkeypatch, [_odp(503), _odp(200)])
    assert hl._get(URL) == b"a,b\n1,2\n"
    assert len(wyw) == 2
    assert spiace == [2]


def test_429_potem_200(monkeypatch, spiace):
    wyw = _mock_get(monkeypatch, [_odp(429), _odp(200)])
    assert hl._get(URL) == b"a,b\n1,2\n"
    assert len(wyw) == 2
    assert spiace == [2]
