"""test_pipeline_health.py — alarm, gdy pipeline przestaje produkować.

PO CO: 30.07–02.08 joby Cloud Run stały na uszkodzonym obrazie. Nikt tego nie
zauważył przez TRZY DNI, bo wykonania raportowały „Completed" bez liczników —
harmonogram działał, tylko kontener nie wstawał.

Wniosek architektoniczny: monitor NIE MOŻE żyć w jobie, który monitoruje.
Job, który się nie uruchamia, nie wyśle alarmu o tym, że się nie uruchomił.
Dlatego ten endpoint stoi na serwisie API (osobny kontener, był zdrowy przez
całą awarię) i pyta o SKUTEK, nie o proces: „czy w bazie przybywa predykcji".

Sprawdza dwie rzeczy, obie po skutku:
  * WIEK NAJNOWSZEJ PREDYKCJI — jeśli pipeline stoi, nic nie przybywa,
    niezależnie od tego, co jest przyczyną (obraz, klucz, limit, sieć);
  * ZALEGŁOŚCI W ROZLICZENIACH — predykcje bez wyniku starsze niż okno
    `update_pending` (2 dni) nigdy same się nie rozliczą, więc rosnąca sterta
    znaczy, że pobieranie wyników padło.

Alarm ma być CICHY, gdy jest dobrze — inaczej po tygodniu nikt go nie czyta.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

from fastapi.testclient import TestClient  # noqa: E402

import footstats.api.routes.status as st  # noqa: E402
import footstats.utils.telegram_notify as tg  # noqa: E402
from footstats.api.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

SEKRET = "sekret-crona-0123456789"


class _Kursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    """Atrapa bazy — oddaje wiek najnowszej predykcji i liczbę zaległości."""

    def __init__(self, wiek_h: float | None = 2.0, zaleglosci: int = 0):
        self.wiek_h = wiek_h
        self.zaleglosci = zaleglosci
        self.blad: Exception | None = None
        self.zapytania: list[str] = []

    def execute(self, sql, params=()):
        if self.blad is not None:
            raise self.blad
        plaski = " ".join(sql.split())
        self.zapytania.append(plaski)
        if "MAX(created_at)" in plaski or "max_created" in plaski:
            if self.wiek_h is None:
                return _Kursor({"ostatnia": None})
            return _Kursor({"ostatnia": datetime.now() - timedelta(hours=self.wiek_h)})
        return _Kursor({"n": self.zaleglosci})

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def srodowisko(monkeypatch):
    """Podstawia bazę i Telegram; zwraca uchwyt do sterowania i log alarmów."""
    stan = {"conn": _Conn(), "alarmy": []}

    monkeypatch.setattr(st, "_connect", lambda *a, **k: stan["conn"])
    monkeypatch.setattr(tg, "_send", lambda text, **kw: stan["alarmy"].append(text) or True)
    monkeypatch.setenv("CRON_SECRET", SEKRET)
    return stan


def _sprawdz(**params):
    return client.post("/api/cron/pipeline-health",
                       headers={"X-Cron-Secret": SEKRET}, params=params)


# ── bramka CRON_SECRET (ta sama klasa co pozostałe /cron/*) ────────────────

def test_zly_sekret_odrzucony(srodowisko):
    r = client.post("/api/cron/pipeline-health", headers={"X-Cron-Secret": "zly"})

    assert r.status_code == 401
    assert srodowisko["alarmy"] == []


def test_brak_naglowka_odrzucony(srodowisko):
    assert client.post("/api/cron/pipeline-health").status_code == 401


def test_pusty_sekret_w_srodowisku_zamyka_endpoint(srodowisko, monkeypatch):
    """hmac.compare_digest("", "") == True — bez warunku `not expected`
    deploy bez zmiennej otwiera endpoint dla każdego."""
    monkeypatch.setenv("CRON_SECRET", "")

    r = client.post("/api/cron/pipeline-health", headers={"X-Cron-Secret": ""})

    assert r.status_code == 401


# ── pipeline zdrowy ────────────────────────────────────────────────────────

def test_swieza_predykcja_to_zdrowy_pipeline(srodowisko):
    srodowisko["conn"] = _Conn(wiek_h=3.0)

    dane = _sprawdz().json()

    assert dane["ok"] is True
    assert dane["powody"] == []


def test_zdrowy_pipeline_nie_wysyla_alarmu(srodowisko):
    """Alarm codziennie „wszystko gra" przestaje być czytany po tygodniu."""
    srodowisko["conn"] = _Conn(wiek_h=3.0)

    _sprawdz()

    assert srodowisko["alarmy"] == []


def test_wiek_predykcji_raportowany(srodowisko):
    srodowisko["conn"] = _Conn(wiek_h=5.0)

    assert _sprawdz().json()["wiek_predykcji_h"] == pytest.approx(5.0, abs=0.1)


# ── pipeline stoi ──────────────────────────────────────────────────────────

def test_stara_predykcja_to_alarm(srodowisko):
    """Dokładnie ta awaria: joby stały 3 dni, w bazie nic nie przybywało."""
    srodowisko["conn"] = _Conn(wiek_h=72.0)

    dane = _sprawdz().json()

    assert dane["ok"] is False
    assert any("predykcj" in p.lower() for p in dane["powody"])


def test_stary_pipeline_wysyla_alarm(srodowisko):
    srodowisko["conn"] = _Conn(wiek_h=72.0)

    _sprawdz()

    assert len(srodowisko["alarmy"]) == 1
    assert "72" in srodowisko["alarmy"][0] or "3" in srodowisko["alarmy"][0]


def test_prog_wieku_konfigurowalny(srodowisko):
    """Domyślnie 26h = doba + margines na opóźniony start joba."""
    srodowisko["conn"] = _Conn(wiek_h=30.0)

    assert _sprawdz(max_wiek_h=48).json()["ok"] is True
    assert _sprawdz(max_wiek_h=24).json()["ok"] is False


def test_prog_domyslny_przepuszcza_dobe(srodowisko):
    srodowisko["conn"] = _Conn(wiek_h=25.0)

    assert _sprawdz().json()["ok"] is True


def test_brak_jakichkolwiek_predykcji_to_alarm(srodowisko):
    """Pusta baza na produkcji znaczy, że pipeline nie wystartował nigdy."""
    srodowisko["conn"] = _Conn(wiek_h=None)

    dane = _sprawdz().json()

    assert dane["ok"] is False
    assert dane["wiek_predykcji_h"] is None


# ── zaległości w rozliczeniach ─────────────────────────────────────────────

def test_zaleglosci_ponad_prog_to_alarm(srodowisko):
    """Predykcje starsze niż okno `update_pending` (2 dni) nigdy same się nie
    rozliczą — rosnąca sterta znaczy, że pobieranie wyników padło."""
    srodowisko["conn"] = _Conn(wiek_h=2.0, zaleglosci=15)

    dane = _sprawdz(max_zaleglosci=10).json()

    assert dane["ok"] is False
    assert any("rozlicz" in p.lower() for p in dane["powody"])


def test_zaleglosci_ponizej_progu_bez_alarmu(srodowisko):
    srodowisko["conn"] = _Conn(wiek_h=2.0, zaleglosci=3)

    assert _sprawdz(max_zaleglosci=10).json()["ok"] is True


def test_liczba_zaleglosci_raportowana(srodowisko):
    srodowisko["conn"] = _Conn(wiek_h=2.0, zaleglosci=7)

    assert _sprawdz().json()["nierozliczone"] == 7


def test_oba_problemy_naraz_w_jednym_alarmie(srodowisko):
    """Jedna wiadomość z dwoma powodami, nie dwie wiadomości."""
    srodowisko["conn"] = _Conn(wiek_h=72.0, zaleglosci=20)

    dane = _sprawdz(max_zaleglosci=5).json()

    assert len(dane["powody"]) == 2
    assert len(srodowisko["alarmy"]) == 1


# ── awarie samego monitora ─────────────────────────────────────────────────

def test_awaria_bazy_to_alarm_a_nie_cisza(srodowisko):
    """Monitor, który milczy przy własnej awarii, jest gorszy niż jego brak."""
    srodowisko["conn"].blad = RuntimeError("connection refused")

    dane = _sprawdz().json()

    assert dane["ok"] is False
    assert any("baz" in p.lower() for p in dane["powody"])


def test_awaria_bazy_nie_zwraca_500(srodowisko):
    """Scheduler ma dostać odpowiedź, nie błąd — inaczej retry zapętla alarm."""
    srodowisko["conn"].blad = RuntimeError("connection refused")

    assert _sprawdz().status_code == 200


def test_niedzialajacy_telegram_nie_wywala_sprawdzenia(srodowisko, monkeypatch):
    """Brak Telegrama ma być odnotowany, ale nie może ukryć wyniku kontroli."""
    def wybucha(text, **kw):
        raise RuntimeError("brak tokenu")

    monkeypatch.setattr(tg, "_send", wybucha)
    srodowisko["conn"] = _Conn(wiek_h=72.0)

    dane = _sprawdz().json()

    assert dane["ok"] is False
    assert dane["alarm_wyslany"] is False


def test_status_wysylki_raportowany(srodowisko):
    srodowisko["conn"] = _Conn(wiek_h=72.0)

    assert _sprawdz().json()["alarm_wyslany"] is True
