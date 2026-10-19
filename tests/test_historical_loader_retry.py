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


# ───────────────── dryf typów datasetu (pandas 3 w odświeżeniu) ─────────────────

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

KOLUMNY_KURSOW = [
    "odds_h_pinn", "odds_d_pinn", "odds_a_pinn",
    "odds_h_max", "odds_d_max", "odds_a_max",
    "odds_over25_pinn", "odds_under25_pinn", "odds_over25_max", "odds_under25_max",
]


def test_ostre_i_najlepsze_bez_zrodla_daja_float64_takze_po_concat():
    """Pusta kolumna kursów musi być float64, nie Float64 (zaraża concat)."""
    pusty = pd.DataFrame({"HomeTeam": ["A", "B"]})
    z_danymi = pd.DataFrame({"PSCH": [2.0, 3.0], "PSCD": [3.0, 3.1], "PSCA": [4.0, 2.5]})
    a = pd.DataFrame(index=range(2))
    b = pd.DataFrame(index=range(2))
    hl._wpisz_ostre_i_najlepsze(a, pusty, sezonowy=True)
    hl._wpisz_ostre_i_najlepsze(b, z_danymi, sezonowy=True)
    razem = pd.concat([a, b], ignore_index=True)
    for kol in KOLUMNY_KURSOW:
        assert a[kol].dtype == np.float64, kol
        assert razem[kol].dtype == np.float64, kol


def test_uzupelnij_schemat_daje_float64():
    out = hl.uzupelnij_schemat(pd.DataFrame({"home": ["A"]}))
    for kol in hl.KOLUMNY_OPCJONALNE:
        assert out[kol].dtype == np.float64, kol


def _dryfnieta() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]).astype("datetime64[us]"),
        "odds_h_pinn": pd.array([1.5, pd.NA], dtype="Float64"),
        "hg": pd.array([1, pd.NA], dtype="Int64"),
        "home": ["A", "B"],
        "away": ["C", "D"],
        "league": ["X", "X"],
    })


def test_normalizuj_typy_float64_i_data_ns_bez_mutacji():
    wejscie = _dryfnieta()
    out = hl._normalizuj_typy(wejscie)
    assert out["odds_h_pinn"].dtype == np.float64
    assert np.isnan(out["odds_h_pinn"].iloc[1])
    assert out["hg"].dtype == np.float64
    assert out["date"].dtype == np.dtype("datetime64[ns]")
    assert out["home"].tolist() == ["A", "B"]
    # wejście nietknięte
    assert str(wejscie["odds_h_pinn"].dtype) == "Float64"
    assert str(wejscie["date"].dtype) == "datetime64[us]"


def test_load_cached_normalizuje_dryf_z_parquet(monkeypatch, tmp_path):
    pytest.importorskip("pyarrow")
    _dryfnieta().to_parquet(tmp_path / hl.NAZWA_PELNEGO, index=False)
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    df = hl.load_cached(z_af=False)
    assert df["odds_h_pinn"].dtype == np.float64
    assert df["date"].dtype == np.dtype("datetime64[ns]")
