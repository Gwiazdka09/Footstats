"""POST /api/admin/opis-meczu — opis meczu tylko dla admina (karta liczb + opis LLM).

Bez sieci, bez prod DB, bez Telegrama: zbiór historyczny to atrapa `pd.DataFrame`,
Bzzoiro i Groq są podmienione na miejscu użycia w `admin_opisy`, statystyki drużyn
(player_db) też. Realny `require_admin` testujemy tokenami JWT (403 dla zwykłego
usera zapada PRZED odczytem bazy); ścieżkę 200 odpalamy z nadpisaną zależnością.
"""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from footstats.api import auth
from footstats.api.auth import require_admin
from footstats.api.main import app
from footstats.api.routes import admin_opisy
from footstats.core import opis_meczu

# Prawdziwy ładowacz zbioru, zapamiętany ZANIM autouse podmieni go na atrapę.
_PRAWDZIWY_WCZYTAJ = admin_opisy._wczytaj_zbior

_URL = "/api/admin/opis-meczu"
_BODY = {"home": "Alfa", "away": "Beta", "liga": "Test League", "data": "2026-10-25"}

_MECZE = [
    ("2026-08-01", "Alfa", "Beta", 2, 0), ("2026-08-08", "Gamma", "Alfa", 1, 1),
    ("2026-08-15", "Alfa", "Gamma", 3, 1), ("2026-08-22", "Beta", "Alfa", 0, 2),
    ("2026-08-29", "Alfa", "Beta", 1, 1), ("2026-09-05", "Gamma", "Alfa", 2, 0),
    ("2026-09-12", "Alfa", "Gamma", 2, 1), ("2026-09-19", "Beta", "Alfa", 1, 3),
    ("2026-09-26", "Alfa", "Beta", 0, 0), ("2026-10-03", "Gamma", "Alfa", 0, 1),
    ("2026-10-10", "Beta", "Gamma", 2, 2), ("2026-10-17", "Alfa", "Gamma", 2, 2),
]

_EVENT = {
    "gosp": "Alfa", "gosc": "Beta", "liga": "Test League", "data": "2026-10-25",
    "pred_ml": {"prob_home_win": 50, "prob_draw": 25, "prob_away_win": 25,
                "prob_over_25": 55, "prob_btts_yes": 60},
    "odds": {"home": 2.0, "draw": 3.5, "away": 4.0, "over_2_5": 1.9, "under_2_5": 1.95},
}


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [{"data": pd.Timestamp(d), "gospodarz": g, "goscie": a, "gole_g": hg, "gole_a": ag}
         for d, g, a, hg, ag in _MECZE]
    )


class _Groq:
    """Atrapa `zapytaj_ai`: zlicza wywołania."""

    def __init__(self, odpowiedz: str | None = "Opis testowy.") -> None:
        self.odpowiedz, self.wywolania = odpowiedz, 0

    def __call__(self, prompt: str, max_tokens: int = 600) -> str | None:
        self.wywolania += 1
        return self.odpowiedz


@pytest.fixture(autouse=True)
def _czysty_stan(monkeypatch):
    """Cache opisów wyczyszczony; źródła zewnętrzne domyślnie podmienione na atrapy."""
    opis_meczu.wyczysc_cache()
    monkeypatch.setattr(admin_opisy, "_pobierz_eventy", lambda: [_EVENT])
    monkeypatch.setattr(admin_opisy, "_zbior_df", None)
    monkeypatch.setattr(admin_opisy, "_wczytaj_zbior", _df)       # `_zbior()` idzie prawdziwą drogą
    monkeypatch.setattr(admin_opisy, "_statystyki_druzyn", lambda *a, **k: None)
    yield
    opis_meczu.wyczysc_cache()


@pytest.fixture(autouse=True)
def groq(monkeypatch) -> _Groq:
    """Atrapa Groqa ZAWSZE (autouse): regres bramki admina nie może uderzyć w prawdziwe API."""
    atrapa = _Groq()
    monkeypatch.setattr(admin_opisy, "zapytaj_ai", atrapa)
    return atrapa


@pytest.fixture
def admin_client():
    """Klient z nadpisanym `require_admin` (jak w testach innych endpointów admina)."""
    app.dependency_overrides[require_admin] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.pop(require_admin, None)


# ── dostęp ──────────────────────────────────────────────────────────────────

def test_bez_tokenu_odmowa():
    r = TestClient(app).post(_URL, json=_BODY)

    assert r.status_code in (401, 403)


def test_zwykly_user_dostaje_403(groq):
    token = auth._make_token("zwykly", 2, is_admin=False)

    r = TestClient(app).post(_URL, json=_BODY, headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 403
    assert groq.wywolania == 0                      # LLM nie został wywołany


def test_admin_dostaje_200(admin_client, groq):
    r = admin_client.post(_URL, json=_BODY)

    assert r.status_code == 200
    assert groq.wywolania == 1


# ── odpowiedź ───────────────────────────────────────────────────────────────

def test_odpowiedz_ma_karte_opis_i_z_cache(admin_client, groq):
    j = admin_client.post(_URL, json=_BODY).json()

    assert set(j) == {"karta", "opis", "z_cache"}
    assert j["opis"] == "Opis testowy." and j["z_cache"] is False
    k = j["karta"]
    assert k["poisson"]["lambda_home"] > 0
    assert k["bzzoiro"]["p1"] == 50.0
    assert k["rynek"]["p1"] > 0
    assert k["forma"]["home"]["ostatnie"][0]["data"] == "2026-10-17"


def test_drugie_zadanie_z_cache_bez_drugiego_wywolania_llm(admin_client, groq):
    admin_client.post(_URL, json=_BODY)
    j = admin_client.post(_URL, json=_BODY).json()

    assert j["z_cache"] is True and j["opis"] == "Opis testowy."
    assert groq.wywolania == 1


def test_llm_pada_karta_wraca_a_opis_none(admin_client, monkeypatch):
    def _pada(prompt, max_tokens=600):
        raise RuntimeError("Groq i Ollama padly")

    monkeypatch.setattr(admin_opisy, "zapytaj_ai", _pada)

    r = admin_client.post(_URL, json=_BODY)

    assert r.status_code == 200
    j = r.json()
    assert j["opis"] is None and j["z_cache"] is False
    assert j["karta"]["poisson"] is not None
    assert "Groq i Ollama padly" not in r.text


def test_brak_zbioru_ale_jest_bzzoiro_200_bez_poissona(admin_client, groq, monkeypatch):
    monkeypatch.setattr(admin_opisy, "_wczytaj_zbior", lambda: None)

    j = admin_client.post(_URL, json=_BODY).json()

    assert j["karta"]["poisson"] is None and j["karta"]["poisson_powod"]
    assert j["karta"]["bzzoiro"] is not None


def test_brak_eventu_ale_jest_poisson_200(admin_client, groq, monkeypatch):
    monkeypatch.setattr(admin_opisy, "_pobierz_eventy", lambda: [])

    j = admin_client.post(_URL, json=_BODY).json()

    assert j["karta"]["poisson"] is not None
    assert j["karta"]["bzzoiro"] is None and j["karta"]["rynek"] is None


def test_statystyki_druzyn_trafiaja_do_karty(admin_client, groq, monkeypatch):
    monkeypatch.setattr(admin_opisy, "_statystyki_druzyn", lambda *a, **k: {
        "home_stats": {"matches": 10, "gf_pg": 1.8, "ga_pg": 0.9, "rating": 7.1},
        "away_stats": {"matches": 10, "gf_pg": 1.1, "ga_pg": 1.4, "rating": 6.8},
        "top_scorers_home": [], "top_scorers_away": [],
    })

    k = admin_client.post(_URL, json=_BODY).json()["karta"]

    assert k["statystyki"]["home"]["gf_pg"] == 1.8


# ── błędy ───────────────────────────────────────────────────────────────────

def test_404_gdy_brak_meczu_w_bzzoiro_i_brak_poissona(admin_client, groq, monkeypatch):
    monkeypatch.setattr(admin_opisy, "_pobierz_eventy", lambda: [])
    monkeypatch.setattr(admin_opisy, "_wczytaj_zbior", lambda: None)

    r = admin_client.post(_URL, json=_BODY)

    assert r.status_code == 404
    assert r.json()["detail"] == "Brak danych o tym meczu"
    assert groq.wywolania == 0


def test_404_dla_nieznanej_pary_nie_przecieka_szczegolow(admin_client, groq, monkeypatch):
    monkeypatch.setattr(admin_opisy, "_pobierz_eventy", lambda: [])

    r = admin_client.post(_URL, json={**_BODY, "home": "Delta", "away": "Epsilon"})

    assert r.status_code == 404
    assert "Traceback" not in r.text and "predict_match" not in r.text


@pytest.mark.parametrize("body", [
    {},                                              # brak pól
    {"home": "", "away": "Beta"},                   # pusta nazwa
    {"home": "Alfa", "away": "B" * 101},            # za długa nazwa
])
def test_walidacja_ciala_zadania(admin_client, groq, body):
    assert admin_client.post(_URL, json=body).status_code == 422


def test_liga_i_data_sa_opcjonalne(admin_client, groq):
    r = admin_client.post(_URL, json={"home": "Alfa", "away": "Beta"})

    assert r.status_code == 200
    assert r.json()["karta"]["liga"] == "Test League"      # uzupełnione z eventu


def test_limit_10_na_minute(admin_client, groq):
    kody = [admin_client.post(_URL, json=_BODY).status_code for _ in range(11)]

    assert kody[:10] == [200] * 10
    assert kody[10] == 429


# ── leniwe ładowanie zbioru ─────────────────────────────────────────────────

def test_zbior_ladowany_raz_na_proces(monkeypatch):
    wywolania = []

    def _wczytaj():
        wywolania.append(1)
        return _df()

    monkeypatch.setattr(admin_opisy, "_wczytaj_zbior", _wczytaj)

    pierwszy, drugi = admin_opisy._zbior(), admin_opisy._zbior()

    assert pierwszy is drugi
    assert wywolania == [1]


def test_zbior_niedostepny_nie_jest_cache_owany(monkeypatch):
    """Porażka (brak pliku / pyarrow) nie może zamrozić None do restartu procesu."""
    wyniki = iter([None, _df()])

    monkeypatch.setattr(admin_opisy, "_wczytaj_zbior", lambda: next(wyniki))

    assert admin_opisy._zbior() is None
    assert admin_opisy._zbior() is not None


def test_wczytaj_zbior_brak_pliku_daje_none(monkeypatch):
    def _brak():
        raise FileNotFoundError("brak cache")

    monkeypatch.setattr("footstats.data.historical_loader.load_cached", _brak)

    assert _PRAWDZIWY_WCZYTAJ() is None


def test_wczytaj_zbior_adaptuje_schemat(monkeypatch):
    surowy = pd.DataFrame({"date": [pd.Timestamp("2026-10-01")], "home": ["Alfa"],
                           "away": ["Beta"], "hg": [1], "ag": [0]})
    monkeypatch.setattr("footstats.data.historical_loader.load_cached", lambda: surowy)

    df = _PRAWDZIWY_WCZYTAJ()

    assert df is not None
    assert {"gospodarz", "goscie", "gole_g", "gole_a", "data"} <= set(df.columns)
