"""Mecz, ktory sie juz zaczal, nie moze trafic do kreatora ani do analizy.

Zgloszone z GUI 04.09.2026 o 20:32: „Krok 1: Wybierz mecze na dzis" pokazywal
mecze o 18:45, a `POST /api/matches/analyze` przyjmowal je bez mrugniecia.

Dwie osobne przyczyny, obie pokryte tutaj:

1. `godzina` NIE MA jednej konwencji w calym projekcie. `api_football` oraz
   `football_data` dopisuja do niej " UTC", `bzzoiro` i `terminarz` oddaja
   sam wycinek ISO bez strefy. Filtr uzywal `strptime(..., "%H:%M")`, wiec
   wiersze z sufiksem " UTC" rzucaly ValueError i byly CICHO pomijane, a te
   bez sufiksu przechodzily z nieznana strefa.

2. `POST /api/matches/analyze` nie filtrowal po czasie W OGOLE — bral `match_ids`
   wprost z globalnego `_MATCHES_CACHE`, ktory bywa wypelniony NIEFILTROWANA
   lista przez `/coupons/daily-proposals`. Czyli nawet po naprawie punktu 1
   mecz zakonczony dalo sie zanalizowac, wysylajac jego id.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("FOOTSTATS_USER", "admin")
os.environ.setdefault("OPERATOR_ADMIN_USERNAME", "admin")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")
_hash = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
os.environ.setdefault("FOOTSTATS_PASSWORD_HASH", _hash)

from fastapi.testclient import TestClient  # noqa: E402

from footstats.api import routes  # noqa: E402
from footstats.api.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    def fake_get(username: str):
        if username in ("admin", "Admin_JG"):
            return {"id": 1, "username": username, "password_hash": _hash}
        return None
    monkeypatch.setattr("footstats.api.auth.get_user_by_username", fake_get)


def _h() -> dict:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _mecz(mid: str, kiedy: datetime, sufiks_utc: bool = False,
          status: str = "notstarted") -> dict:
    g = kiedy.strftime("%H:%M") + (" UTC" if sufiks_utc else "")
    return {
        "id": mid, "gosp": f"Dom{mid}", "gosc": f"Wyj{mid}",
        "liga": "TEST", "data": kiedy.strftime("%Y-%m-%d"), "godzina": g,
        "data_full": kiedy.isoformat(), "status": status,
        "pw": 45.0, "pr": 27.0, "pp": 28.0,
    }


@pytest.fixture()
def _bez_cache(monkeypatch):
    from footstats.core.response_cache import clear_response_cache
    monkeypatch.setattr(routes.coupons, "_MATCHES_CACHE", [], raising=False)
    clear_response_cache()
    yield
    clear_response_cache()


def _podstaw(monkeypatch, mecze: list[dict]) -> None:
    monkeypatch.setattr(routes.coupons, "_fetch_predictions", lambda: mecze)


def test_mecz_ktory_sie_zaczal_nie_jest_proponowany(monkeypatch, _bez_cache):
    teraz = datetime.now(timezone.utc)
    _podstaw(monkeypatch, [
        _mecz("stary", teraz - timedelta(hours=2)),
        _mecz("nowy", teraz + timedelta(hours=3)),
    ])
    r = client.get("/api/matches/today", headers=_h())
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()}
    assert "stary" not in ids, "mecz sprzed dwoch godzin trafil do kreatora"
    assert "nowy" in ids


def test_godzina_z_sufiksem_UTC_nie_wypada_cicho(monkeypatch, _bez_cache):
    """Mecz z ' UTC' w godzinie ma sie POJAWIC, a nie zostac zjedzony przez
    ValueError w `strptime`. Cicha strata to najgorszy wariant: lista wyglada
    poprawnie i po prostu brakuje w niej polowy zrodel."""
    teraz = datetime.now(timezone.utc)
    _podstaw(monkeypatch, [_mecz("zutc", teraz + timedelta(hours=4), sufiks_utc=True)])
    r = client.get("/api/matches/today", headers=_h())
    assert r.status_code == 200
    assert {m["id"] for m in r.json()} == {"zutc"}


def test_status_inny_niz_notstarted_wyklucza_mecz(monkeypatch, _bez_cache):
    """Zrodlo mowi wprost, ze mecz trwa albo sie skonczyl. To jest informacja
    autorytatywna i wazniejsza niz jakiekolwiek liczenie stref czasowych."""
    teraz = datetime.now(timezone.utc)
    _podstaw(monkeypatch, [
        _mecz("gra", teraz + timedelta(hours=1), status="inprogress"),
        _mecz("koniec", teraz + timedelta(hours=1), status="finished"),
        _mecz("ok", teraz + timedelta(hours=1), status="notstarted"),
    ])
    r = client.get("/api/matches/today", headers=_h())
    ids = {m["id"] for m in r.json()}
    assert ids == {"ok"}, f"status zignorowany, dostalismy {ids}"


def test_ANALIZA_odrzuca_mecz_ktory_sie_zaczal(monkeypatch, _bez_cache):
    """Sedno zgloszenia. Nawet gdy id trafi do zadania — bo pochodzi ze starej
    zakladki albo z globalnego cache'u wypelnionego przez inny endpoint —
    analiza meczu rozpoczetego ma sie NIE odbyc."""
    teraz = datetime.now(timezone.utc)
    mecze = [
        _mecz("stary", teraz - timedelta(hours=2)),
        _mecz("nowy", teraz + timedelta(hours=3)),
    ]
    _podstaw(monkeypatch, mecze)
    monkeypatch.setattr(routes.coupons, "_MATCHES_CACHE", mecze, raising=False)

    r = client.post("/api/matches/analyze", headers=_h(),
                    json={"match_ids": ["stary", "nowy"]})
    assert r.status_code == 200, r.text
    zwrocone = r.json()
    assert all(t.get("id") != "stary" for t in zwrocone), (
        "analiza wykonana dla meczu, ktory sie juz zaczal")


def test_ANALIZA_samego_rozpoczetego_meczu_zwraca_pustke(monkeypatch, _bez_cache):
    teraz = datetime.now(timezone.utc)
    mecze = [_mecz("stary", teraz - timedelta(minutes=30))]
    _podstaw(monkeypatch, mecze)
    monkeypatch.setattr(routes.coupons, "_MATCHES_CACHE", mecze, raising=False)
    r = client.post("/api/matches/analyze", headers=_h(),
                    json={"match_ids": ["stary"]})
    assert r.status_code == 200
    assert r.json() == []


def test_bzzoiro_oddaje_pelne_ISO_a_nie_tylko_wycinki(monkeypatch):
    """Zrodlowa naprawa. `data`/`godzina` to wycinki po znakach, wiec gubia
    przesuniecie strefy — a konsument musial przez to ZAKLADAC UTC. Zalozenie
    bylo bledne co najmniej raz (kreator 04.09.2026)."""
    from footstats.scrapers.bzzoiro import BzzoiroClient

    odpowiedz = {"results": [{"event": {
        "id": 1, "home_team": "A", "away_team": "B",
        "league": {"name": "L"}, "status": "notstarted",
        "event_date": "2026-09-04T18:45:00+04:00",
    }}]}
    klient = BzzoiroClient.__new__(BzzoiroClient)
    monkeypatch.setattr(BzzoiroClient, "_get", lambda self, *a, **k: odpowiedz)

    wynik = klient.predykcje_tygodnia()
    assert len(wynik) == 1
    assert wynik[0]["data_full"] == "2026-09-04T18:45:00+04:00"
    # Wycinki zostaja bez zmiany — GUI ma dalej wyswietlac to samo.
    assert wynik[0]["data"] == "2026-09-04"
    assert wynik[0]["godzina"] == "18:45"


def test_moment_meczu_szanuje_przesuniecie_strefy():
    """18:45+04:00 to 14:45 UTC. Gdyby konsument dalej ciął string i zakladal
    UTC, mecz wygladalby na cztery godziny pozniejszy — dokladnie ten blad
    pokazywal kreator."""
    from footstats.api.routes.coupons import _moment_meczu

    m = {"data": "2026-09-04", "godzina": "18:45",
         "data_full": "2026-09-04T18:45:00+04:00"}
    assert _moment_meczu(m) == datetime(2026, 9, 4, 14, 45, tzinfo=timezone.utc)


def test_moment_meczu_bez_data_full_przyjmuje_UTC():
    from footstats.api.routes.coupons import _moment_meczu

    m = {"data": "2026-09-04", "godzina": "18:45 UTC"}
    assert _moment_meczu(m) == datetime(2026, 9, 4, 18, 45, tzinfo=timezone.utc)


def test_moment_meczu_oddaje_None_gdy_nie_da_sie_odczytac():
    from footstats.api.routes.coupons import _moment_meczu

    assert _moment_meczu({}) is None
    assert _moment_meczu({"data": "2026-09-04"}) is None
    assert _moment_meczu({"data": "bez sensu", "godzina": "18:45"}) is None
