"""Raport dzienny — codzienne potwierdzenie, ze przebieg poszedl.

PO CO OSOBNO OD ALARMU: `pipeline-health` MILCZY, gdy jest dobrze, i to jest
swiadome — alarm wysylany codziennie "wszystko gra" przestaje byc czytany po
tygodniu. Ale cisza nie odroznia "poszlo dobrze" od "monitor tez padl", a przy
awarii I7 (kupony stanely na osiem dni) cisza znaczyla dokladnie to drugie.

Raport odpowiada na inne pytanie niz alarm. Alarm: "czy cos jest zepsute".
Raport: "ile dzis powstalo". Spadek z 14 kuponow na 2 nie jest awaria i alarmu
nie wywola, ale jest sygnalem — i wlasnie po to sa liczby.

DLACZEGO WEWNATRZ PRODUKCJI, a nie z agenta w chmurze: agent startuje z czystym
checkoutem, bez `gcloud`, bez `DATABASE_URL` i bez `CRON_SECRET`, a kazdy endpoint
mowiacy cokolwiek o stanie wymaga uwierzytelnienia. Zeby dzialal, trzeba by wkleic
sekret do przechowywanej konfiguracji rutyny — ten sam blad, przez ktory 14.08
`CRON_SECRET` wyciekl i wymagal rotacji. Raport liczy tam, gdzie poswiadczenia juz sa.
"""
from __future__ import annotations

import os

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
    """Atrapa bazy — kazde zapytanie raportu oddaje swoja liczbe."""

    def __init__(self, kupony=14, predykcje=8, rozliczone=7):
        self.liczby = {"coupons": kupony, "predictions": predykcje,
                       "rozliczone": rozliczone}
        self.blad: Exception | None = None
        self.zapytania: list[str] = []

    def execute(self, sql, params=()):
        if self.blad is not None:
            raise self.blad
        plaski = " ".join(sql.split())
        self.zapytania.append(plaski)
        if "coupons" in plaski:
            return _Kursor({"n": self.liczby["coupons"]})
        if "tip_correct IS NOT NULL" in plaski:
            return _Kursor({"n": self.liczby["rozliczone"]})
        return _Kursor({"n": self.liczby["predictions"]})

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def srodowisko(monkeypatch):
    stan = {"conn": _Conn(), "wiadomosci": []}
    monkeypatch.setattr(st, "_connect", lambda *a, **k: stan["conn"])
    monkeypatch.setattr(tg, "_send",
                        lambda text, **kw: stan["wiadomosci"].append(text) or True)
    monkeypatch.setenv("CRON_SECRET", SEKRET)
    return stan


def _raport():
    return client.post("/api/cron/raport-dzienny", headers={"X-Cron-Secret": SEKRET})


# ── bramka, ta sama co pozostale /cron/* ────────────────────────────────────

def test_zly_sekret_odrzucony(srodowisko):
    r = client.post("/api/cron/raport-dzienny", headers={"X-Cron-Secret": "zly"})

    assert r.status_code == 401
    assert srodowisko["wiadomosci"] == []


def test_brak_naglowka_odrzucony(srodowisko):
    assert client.post("/api/cron/raport-dzienny").status_code == 401


# ── raport idzie ZAWSZE, tez gdy dobrze ─────────────────────────────────────

def test_raport_wysylany_takze_przy_zdrowym_stanie(srodowisko):
    """Rozni sie tym od alarmu: cisza nie odroznia 'poszlo dobrze' od
    'monitor tez padl'."""
    _raport()

    assert len(srodowisko["wiadomosci"]) == 1, srodowisko["wiadomosci"]


def test_jedna_wiadomosc_nie_trzy(srodowisko):
    """Trzy osobne wiadomosci dziennie ucza wyciszac powiadomienia."""
    _raport()

    assert len(srodowisko["wiadomosci"]) == 1


@pytest.mark.parametrize("klucz,wartosc", [
    ("kupony", 14), ("predykcje", 8), ("rozliczone", 7),
])
def test_liczby_w_odpowiedzi(srodowisko, klucz: str, wartosc: int):
    """Liczby wracaja tez w JSON — inaczej da sie je odczytac tylko z Telegrama."""
    dane = _raport().json()

    assert dane[klucz] == wartosc, dane


def test_liczby_w_tresci_wiadomosci(srodowisko):
    _raport()
    tresc = srodowisko["wiadomosci"][0]

    assert "14" in tresc and "8" in tresc and "7" in tresc, tresc


# ── zero kuponow to sedno: dokladnie tak wygladala awaria I7 ────────────────

def test_zero_kuponow_wyroznione_w_raporcie(srodowisko):
    """Przez osiem dni bylo dokladnie zero i nikt sie nie dowiedzial."""
    srodowisko["conn"] = _Conn(kupony=0)

    dane = _raport().json()

    assert dane["kupony"] == 0
    assert dane["ok"] is False, "zero kuponow to nie jest zdrowy dzien"


def test_zero_kuponow_widoczne_w_wiadomosci(srodowisko):
    srodowisko["conn"] = _Conn(kupony=0)

    _raport()

    assert "0" in srodowisko["wiadomosci"][0]


def test_kupony_powstaly_to_dzien_ok(srodowisko):
    srodowisko["conn"] = _Conn(kupony=3)

    assert _raport().json()["ok"] is True


# ── awaria nie moze uciszyc raportu ─────────────────────────────────────────

def test_awaria_bazy_nie_ucisza_raportu(srodowisko):
    """Raport, ktory milczy przy wlasnej awarii, jest gorszy niz jego brak —
    cisza wyglada wtedy identycznie jak zdrowy dzien."""
    srodowisko["conn"].blad = RuntimeError("baza padla")

    dane = _raport().json()

    assert srodowisko["wiadomosci"], "raport nie poszedl mimo awarii bazy"
    assert dane["ok"] is False
    assert "baza" in " ".join(dane.get("problemy", [])).lower() or dane.get("problemy")


def test_awaria_telegrama_nie_wywala_endpointu(srodowisko, monkeypatch):
    """Scheduler dostajacy 500 zapetla retry — a i tak nie ma komu wyslac."""
    monkeypatch.setattr(tg, "_send", lambda *a, **k: (_ for _ in ()).throw(OSError("brak sieci")))

    r = _raport()

    assert r.status_code == 200
    assert r.json()["wyslany"] is False
