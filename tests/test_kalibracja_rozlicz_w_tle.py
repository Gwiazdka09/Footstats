"""`/api/cron/kalibracja-rozlicz` konczy sie 202, praca leci w tle.

ZMIERZONE NA PRODUKCJI 01.09:

    05:00:44  Scheduler POST /api/cron/kalibracja-rozlicz  (attemptDeadline 300 s)
    05:00:54  Timeout 10s na POST ... — zwracam 504        (_TimeoutMiddleware)
    05:31:19  cron_kalibracja_rozlicz: {'sprawdzone': 175,
               'rozliczone': 34, 'bledy': 0}               <- praca DOSZLA DO KONCA

Scheduler zapisal `status.code: 4`, czyli zdrowy przebieg wyglada w monitoringu
na zepsuty — a prawdziwa awaria bylaby od niego NIEODROZNIALNA. Ten sam ksztalt
bledu, ktory ta sesja naprawiala juz kilka razy.

Dlaczego praca konczyla sie mimo 504: handler jest zwyklym `def`, wiec FastAPI
puszcza go w watku puli. `asyncio.wait_for` anuluje korutyne, ale watku nie
zatrzymuje.

Dlaczego nie wystarczy dopisac sciezki do `_LONG_RUNNING_PATHS`: tamten limit to
120 s, praca trwa ~30 minut, a `attemptDeadline` Schedulera ma maksimum 30 minut.
ZADEN uklad timeoutow nie utrzyma tu synchronicznego zadania — trzeba oddac
odpowiedz od razu.

202 zamiast 200 celowo: 200 z licznikami znaczylby "policzone", a w tym momencie
jeszcze nic nie jest policzone.
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

SEKRET = "test-cron-secret"


@pytest.fixture
def klient(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", SEKRET)
    from footstats.api.main import app
    return TestClient(app)


@pytest.fixture
def praca(monkeypatch):
    """Podstawia `rozlicz_dziennik` i zapamietuje wywolania."""
    wywolania = []

    def _fake(**kw):
        wywolania.append(kw)
        return {"sprawdzone": 175, "rozliczone": 34, "bez_wyniku": 141, "bledy": 0}

    monkeypatch.setattr("footstats.core.kalibracja_rozlicz.rozlicz_dziennik", _fake)
    return wywolania


def _post(klient, **params):
    return klient.post("/api/cron/kalibracja-rozlicz",
                       headers={"X-Cron-Secret": SEKRET}, params=params)


# ── odpowiedz natychmiastowa ────────────────────────────────────────────────

def test_zwraca_202_a_nie_200(klient, praca):
    """200 z licznikami znaczyloby 'policzone'. Nic jeszcze nie jest policzone."""
    assert _post(klient).status_code == 202


def test_odpowiedz_nie_udaje_ze_praca_skonczona(klient, praca):
    dane = _post(klient).json()

    assert "rozliczone" not in dane, "liczniki w odpowiedzi sugerowalyby ukonczenie"
    assert dane.get("started") is True


# ── praca faktycznie rusza ──────────────────────────────────────────────────

def test_praca_zostaje_uruchomiona(klient, praca):
    _post(klient)

    assert len(praca) == 1, "202 bez uruchomienia pracy bylby cisza udajaca sukces"


def test_parametry_przechodza_do_pracy(klient, praca):
    _post(klient, dni_wstecz=30, dry_run=True)

    assert praca[0]["dni_wstecz"] == 30
    assert praca[0]["dry_run"] is True


def test_wynik_pracy_trafia_do_logu(klient, praca, caplog):
    """Skoro odpowiedz nie niesie licznikow, log jest JEDYNYM zrodlem wyniku."""
    with caplog.at_level(logging.INFO):
        _post(klient)

    assert "rozliczone" in caplog.text or "175" in caplog.text


# ── awaria w tle nie moze zniknac ───────────────────────────────────────────

def test_awaria_w_tle_zostawia_ERROR(klient, monkeypatch, caplog):
    """Bez tego 202 zamienialby kazda awarie w ciche powodzenie."""
    def _wybuch(**kw):
        raise RuntimeError("baza nie odpowiada")

    monkeypatch.setattr("footstats.core.kalibracja_rozlicz.rozlicz_dziennik", _wybuch)

    with caplog.at_level(logging.ERROR):
        odp = _post(klient)

    assert odp.status_code == 202, "awaria w tle nie zmienia juz wyslanej odpowiedzi"
    assert [r for r in caplog.records if r.levelno >= logging.ERROR], (
        "awaria w tle musi zostawic ERROR — to jedyny sygnal, jaki zostal"
    )


# ── bramka pozostaje ────────────────────────────────────────────────────────

def test_bez_sekretu_401_i_praca_NIE_rusza(klient, praca):
    odp = klient.post("/api/cron/kalibracja-rozlicz")

    assert odp.status_code == 401
    assert praca == [], "praca nie moze ruszyc przed sprawdzeniem sekretu"


def test_zly_sekret_401(klient, praca):
    odp = klient.post("/api/cron/kalibracja-rozlicz",
                      headers={"X-Cron-Secret": "nie-ten"})

    assert odp.status_code == 401
    assert praca == []


# ── spojnosc z lista dlugich endpointow ─────────────────────────────────────

def test_sciezka_NIE_potrzebuje_juz_dlugiego_limitu():
    """Odpowiedz idzie w milisekundach, wiec limit 10 s wystarcza. Dopisanie
    sciezki do `_LONG_RUNNING_PATHS` bylo niewystarczajace i mylace: 120 s
    to nadal ulamek 30 minut, ktore praca realnie trwa."""
    from footstats.api.main import _LONG_RUNNING_PATHS

    assert "/api/cron/kalibracja-rozlicz" not in _LONG_RUNNING_PATHS
