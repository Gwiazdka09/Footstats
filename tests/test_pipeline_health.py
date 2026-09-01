"""test_pipeline_health.py — alarm, gdy pipeline przestaje produkować.

PO CO: 30.07–02.08 joby Cloud Run stały na uszkodzonym obrazie. Nikt tego nie
zauważył przez TRZY DNI, bo wykonania raportowały „Completed" bez liczników —
harmonogram działał, tylko kontener nie wstawał.

Wniosek architektoniczny: monitor NIE MOŻE żyć w jobie, który monitoruje.
Job, który się nie uruchamia, nie wyśle alarmu o tym, że się nie uruchomił.
Dlatego ten endpoint stoi na serwisie API (osobny kontener, był zdrowy przez
całą awarię) i pyta o SKUTEK, nie o proces: „czy w bazie przybywa predykcji".

Sprawdza trzy rzeczy, wszystkie po skutku:
  * WIEK NAJNOWSZEJ PREDYKCJI — jeśli pipeline stoi, nic nie przybywa,
    niezależnie od tego, co jest przyczyną (obraz, klucz, limit, sieć);
  * ZALEGŁOŚCI W ROZLICZENIACH — predykcje bez wyniku starsze niż okno
    `update_pending` (2 dni) nigdy same się nie rozliczą, więc rosnąca sterta
    znaczy, że pobieranie wyników padło;
  * WIEK NAJNOWSZEGO KUPONU System — dodane 24.08 po awarii I7, w której
    kuponów nie było przez OSIEM DNI, a monitor świecił zielono, bo predykcje
    płynęły dalej. Szczegóły przy testach na dole pliku.

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
    """Atrapa bazy — wiek najnowszej predykcji, zaległości i wiek kuponu System."""

    def __init__(self, wiek_h: float | None = 2.0, zaleglosci: int = 0,
                 wiek_kuponu_dni: int | None = 0):
        self.wiek_h = wiek_h
        self.zaleglosci = zaleglosci
        self.wiek_kuponu_dni = wiek_kuponu_dni
        self.blad: Exception | None = None
        self.zapytania: list[str] = []

    def execute(self, sql, params=()):
        if self.blad is not None:
            raise self.blad
        plaski = " ".join(sql.split())
        self.zapytania.append(plaski)
        # Kolejność WAŻNA: zapytanie o kupony też zawiera MAX(...created_at),
        # więc musi być rozpoznane PRZED gałęzią predykcji.
        if "coupons" in plaski:
            if self.wiek_kuponu_dni is None:
                return _Kursor({"ostatni_kupon": None})
            return _Kursor({
                "ostatni_kupon": datetime.now() - timedelta(days=self.wiek_kuponu_dni)
            })
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


# ── /cron/kalibracja-rozlicz ───────────────────────────────────────────────
#
# Dziennik kalibracyjny bez rozliczania zbiera oceny, ktorych nikt nie ocenia.
# Endpoint odpalany codziennie przez Schedulera, po jobie evening.

def test_rozliczanie_wymaga_sekretu(srodowisko):
    r = client.post("/api/cron/kalibracja-rozlicz", headers={"X-Cron-Secret": "zly"})

    assert r.status_code == 401


def test_rozliczanie_potwierdza_przyjecie(srodowisko, monkeypatch):
    """Od 01.09 praca leci w TLE, wiec odpowiedz potwierdza PRZYJECIE, nie wynik.

    Powod jest zmierzony: praca trwa ~30 minut, `attemptDeadline` Schedulera ma
    maksimum 30 minut, a `_TimeoutMiddleware` cial zadanie po 10 s i Scheduler
    zapisywal `status.code: 4` mimo ze robota dochodzila do konca. Liczniki
    przenioslly sie do logu — pilnuje ich `test_kalibracja_rozlicz_w_tle.py`."""
    import footstats.core.kalibracja_rozlicz as kr
    monkeypatch.setattr(kr, "rozlicz_dziennik",
                        lambda **kw: {"sprawdzone": 5, "rozliczone": 3,
                                      "bez_wyniku": 2, "bledy": 0})

    odp = client.post("/api/cron/kalibracja-rozlicz",
                      headers={"X-Cron-Secret": SEKRET})

    assert odp.status_code == 202
    assert odp.json()["started"] is True


def test_rozliczanie_przekazuje_okno(srodowisko, monkeypatch):
    import footstats.core.kalibracja_rozlicz as kr
    przekazane = {}
    monkeypatch.setattr(kr, "rozlicz_dziennik",
                        lambda **kw: przekazane.update(kw) or {"sprawdzone": 0})

    client.post("/api/cron/kalibracja-rozlicz?dni_wstecz=30",
                headers={"X-Cron-Secret": SEKRET})

    assert przekazane["dni_wstecz"] == 30


def test_rozliczanie_dry_run(srodowisko, monkeypatch):
    """Podglad przed zapisem — ta sama zasada co przy kuponach."""
    import footstats.core.kalibracja_rozlicz as kr
    przekazane = {}
    monkeypatch.setattr(kr, "rozlicz_dziennik",
                        lambda **kw: przekazane.update(kw) or {"sprawdzone": 0})

    client.post("/api/cron/kalibracja-rozlicz?dry_run=true",
                headers={"X-Cron-Secret": SEKRET})

    assert przekazane["dry_run"] is True


def test_awaria_rozliczania_NIE_jest_cisza(srodowisko, monkeypatch, caplog):
    """Niezmiennik zostaje: awaria nie moze zniknac. Zmienil sie tylko kanal.

    Do 01.09 bylo to HTTP 500. Odpowiedz wychodzi teraz PRZED praca, wiec
    wyjatek nie ma gdzie wyplynac — ERROR w logu jest jedynym sygnalem, jaki
    zostal, i dlatego musi byc."""
    import logging

    import footstats.core.kalibracja_rozlicz as kr

    def wybucha(**kw):
        raise RuntimeError("baza padla")

    monkeypatch.setattr(kr, "rozlicz_dziennik", wybucha)

    with caplog.at_level(logging.ERROR):
        r = client.post("/api/cron/kalibracja-rozlicz",
                        headers={"X-Cron-Secret": SEKRET})

    assert r.status_code == 202
    assert [x for x in caplog.records if x.levelno >= logging.ERROR], (
        "awaria w tle bez ERROR-a bylaby cichym powodzeniem"
    )


# ── TRZECI WYMIAR: czy kupony w ogóle powstają (dodane 24.08 po awarii I7) ──
#
# 15–23.08 kupony nie powstawały przez OSIEM DNI, a ten monitor świecił zielono
# przez cały ten czas. Powód: sprawdzał WYŁĄCZNIE wiek predykcji i zaległości
# w rozliczeniach. Predykcje płynęły (pisze je job), więc pierwszy warunek był
# spełniony — a kupony robi `/api/cron/draft` na serwisie API, który padał na
# przekroczeniu pamięci 512 MiB i oddawał 503.
#
# Sygnał `stale_days` ISTNIAŁ, ale mieszkał WEWNĄTRZ draftu — czyli wewnątrz tego,
# co było zepsute. Endpoint, który umiera, nie zgłosi, że umarł. Dokładnie ten sam
# błąd architektoniczny, przed którym ostrzega nagłówek tego pliku ("monitor nie
# może żyć w tym, co monitoruje") — tylko o jeden poziom wyżej.
#
# Dlatego monitor pyta o kupony SAM, niezależnie od draftu, i znów po SKUTKU:
# „czy w bazie przybywa kuponów System".

def test_zdrowo_gdy_kupony_powstaja(srodowisko):
    srodowisko["conn"].wiek_kuponu_dni = 0

    r = _sprawdz()

    assert r.json()["ok"] is True, r.json()
    assert srodowisko["alarmy"] == []


def test_alarm_gdy_kupony_nie_powstaja_od_dni(srodowisko):
    """Sedno I7: przez osiem dni nikt się nie dowiedział."""
    srodowisko["conn"].wiek_kuponu_dni = 8

    r = _sprawdz()
    dane = r.json()

    assert dane["ok"] is False, dane
    assert any("kupon" in p.lower() for p in dane["powody"]), dane["powody"]
    assert srodowisko["alarmy"], "alarm o braku kuponow nie poszedl"


def test_alarm_gdy_kuponow_nie_bylo_nigdy(srodowisko):
    """Świeża baza albo skasowana tabela — brak wiersza to nie jest 'zdrowo'."""
    srodowisko["conn"].wiek_kuponu_dni = None

    dane = _sprawdz().json()

    assert dane["ok"] is False
    assert any("kupon" in p.lower() for p in dane["powody"]), dane["powody"]


def test_swiezy_kupon_nie_wywoluje_alarmu_mimo_progu(srodowisko):
    """Próg to 3 dni — dwa dni bez kuponu bywają normalne (przerwa w rozgrywkach)."""
    srodowisko["conn"].wiek_kuponu_dni = 2

    dane = _sprawdz().json()

    assert dane["ok"] is True, dane


def test_monitor_pyta_o_kupony_NIEZALEZNIE_od_draftu(srodowisko):
    """Gdyby monitor czytał wynik draftu zamiast bazy, milczałby dokładnie wtedy,
    gdy draft padł — a to była cała przyczyna, dla której I7 przeżyło tydzień."""
    srodowisko["conn"].wiek_kuponu_dni = 8
    _sprawdz()

    zapytania = " ".join(srodowisko["conn"].zapytania).lower()

    assert "coupons" in zapytania, "monitor nie odpytal tabeli kuponow"


def test_wiek_kuponu_w_odpowiedzi(srodowisko):
    """Liczba w odpowiedzi, nie tylko w alarmie — inaczej nie da się śledzić trendu."""
    srodowisko["conn"].wiek_kuponu_dni = 5

    dane = _sprawdz().json()

    assert dane.get("wiek_kuponu_dni") == 5, dane


def test_awaria_bazy_przy_kuponach_nie_ucisza_monitora(srodowisko):
    """Monitor milczący przy własnej awarii jest gorszy niż jego brak."""
    srodowisko["conn"].blad = RuntimeError("baza padla")

    dane = _sprawdz().json()

    assert dane["ok"] is False
    assert dane["powody"]


# ── alarm, ktory nigdy nie gasnie (naprawione 24.08) ────────────────────────
#
# ZMIERZONE NA PRODUKCJI 24.08: monitor liczył 25 zaległych rozliczeń przy progu
# 10, więc alarm palił się bez przerwy. Z tych 25 **ZERO** było w zasięgu źródeł —
# najstarsze to mecze z MAJA 2026. Żadne źródło ich nie odda.
#
# Dlaczego nie wypadły jako „porzucone": wykluczenie działa po liczbie prób
# (`settle_attempts >= MAX_PROB_ROZLICZENIA`), a te mają prób mniej niż 5, bo
# pętla nadrabiania sięga tylko po świeże. Wiszą w limbo: za stare, żeby się
# rozliczyć, za mało prób, żeby przestać się liczyć.
#
# Właściwym kryterium nie jest liczba prób, tylko OSIĄGALNOŚĆ ŹRÓDŁA — ta sama
# granica `HORYZONT_ZRODEL_DNI`, którą wprowadziło D6. Starsze mecze to nie
# zaległość, tylko trupy.
#
# To nie jest kosmetyka. Alarm, który świeci zawsze, uczy go ignorować — a przy
# ignorowanym alarmie awaria kuponów (I7) przeleżała OSIEM DNI.

def test_zaleglosci_ograniczone_do_zasiegu_zrodel():
    """Zapytanie MUSI mieć dolną granicę okna, nie tylko górną.

    Sprawdzamy SQL, bo atrapa bazy zwraca liczbę niezależnie od parametrów —
    test na samej liczbie przeszedłby także dla zapytania bez granicy.
    """
    import inspect

    from footstats.core.coupon_settlement import HORYZONT_ZRODEL_DNI

    zrodlo = inspect.getsource(st.pipeline_health)

    assert "HORYZONT_ZRODEL_DNI" in zrodlo, (
        "zapytanie o zaleglosci nie ogranicza sie do zasiegu zrodel — bedzie "
        "liczyc mecze, ktorych zadne zrodlo juz nie odda, i alarm nie zgasnie"
    )
    assert HORYZONT_ZRODEL_DNI >= 2, "okno zaleglosci byloby puste"


def test_okno_zaleglosci_ma_obie_granice(srodowisko):
    """Dolna granica bez górnej liczyłaby mecze sprzed dwóch dni, które jeszcze
    mają prawo się nie rozliczyć; górna bez dolnej liczy trupy."""
    srodowisko["conn"].zaleglosci = 3
    _sprawdz()

    sql = " ".join(srodowisko["conn"].zapytania)
    zapytanie = next(z for z in sql.split("SELECT") if "settle_attempts" in z)

    assert zapytanie.count("match_date") >= 2, (
        f"okno zaleglosci ma tylko jedna granice: {zapytanie}"
    )
