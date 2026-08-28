"""Kupon z dziennika, którego nikt nie umie rozliczyć, nie może wisieć w nieskończoność.

ZMIERZONE 2026-08-25 na produkcji: kupon `#149` (Yunnan Yukun vs Dalian Yingbo FC,
chińska ekstraklasa, mecz 15.08) ma status ACTIVE od dziesięciu dni i zostanie
ACTIVE na zawsze. Żadne z naszych źródeł nie pokrywa tej ligi, więc `link_leg`
nigdy nie znajdzie predykcji z wynikiem, a fallback D5 nie ma gdzie szukać.

To lustro usterki naprawionej dzień wcześniej dla kuponów AI
(`test_void_bez_wyniku_nie_milczy`): tam kupon po `VOID_AFTER_DAYS` cicho znikał,
tu cicho zostaje. Ta sama cisza, przeciwny skutek.

DLACZEGO NIE AUTO-VOID — i to jest sedno tego pliku. `set_coupon_result`
(`api/routes/coupons.py`) rozlicza ręcznie wyłącznie kupony ze statusem ACTIVE
(CAS-guard `expected_status='ACTIVE'`). Automatyczne oznaczenie VOID odebrałoby
użytkownikowi jedyną drogę wpisania prawdziwego wyniku — skasowalibyśmy JEGO
zapis, bo MY nie umiemy go sprawdzić. Dziennik jest własnością użytkownika.

Więc: policzyć i zawołać, nie kasować. Status zostaje ACTIVE.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta

import pytest


class _SQLiteConn:
    """Adapter sqlite3 pod interfejs `footstats.utils.db._Conn`."""

    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()):
        return self._raw.execute(sql, params)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    def __enter__(self) -> "_SQLiteConn":
        return self

    def __exit__(self, exc_type, *_) -> bool:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


_SCHEMA = """
CREATE TABLE coupons (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    status           TEXT NOT NULL DEFAULT 'DRAFT',
    legs_json        TEXT NOT NULL DEFAULT '[]',
    total_odds       REAL,
    stake_pln        REAL,
    payout_pln       REAL,
    roi_pct          REAL,
    match_date_first TEXT,
    user_id          INTEGER DEFAULT 1,
    kupon_type       TEXT,
    bookmaker        TEXT
);
"""

# Noga dokladnie taka, jak w produkcyjnym kuponie #149.
NOGA = ('[{"home": "Yunnan Yukun", "away": "Dalian Yingbo FC", "tip": "Over 2.5",'
        ' "odds": 1.35, "mecz": "Yunnan Yukun vs Dalian Yingbo FC",'
        ' "result": null, "leg_won": null}]')


class _BrakDopasowania:
    """`link_leg` dla ligi, ktorej nie pokrywamy — nic nie znajduje.

    `match_confidence` MUSI tu byc: rozliczanie odroznia "brak meczu" od
    "dwa rozne mecze w oknie dat" i tylko to pierwsze schodzi do `model_log`.
    Atrapa bez tego pola udawalaby kontrakt `LinkResult`, ktorego nie spelnia.
    """

    matched = ""
    match_confidence = "none"
    prediction = None


def _baza(tmp_path, monkeypatch, dni_temu: int):
    path = str(tmp_path / "dziennik.db")
    setup = sqlite3.connect(path)
    setup.executescript(_SCHEMA)
    data = (datetime.now().date() - timedelta(days=dni_temu)).isoformat()
    setup.execute(
        "INSERT INTO coupons (status, legs_json, total_odds, stake_pln,"
        " match_date_first, kupon_type) VALUES (?,?,?,?,?,?)",
        ("ACTIVE", NOGA, 1.35, 2.0, data, "manual"),
    )
    setup.commit()
    setup.close()

    import footstats.core.backtest as bt
    import footstats.core.coupon_settlement as cs
    from footstats.core import match_linker

    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(path))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    monkeypatch.setattr(match_linker, "link_leg",
                        lambda *a, **k: _BrakDopasowania())
    # D5 wylaczone: chinska ekstraklasa i tak nie siedzi w zadnym z tych zrodel.
    monkeypatch.setattr(cs, "_manual_zrodla_zewnetrzne", lambda: False)
    return path


@pytest.fixture
def baza_stara(tmp_path, monkeypatch):
    """Mecz sprzed 12 dni — poza `VOID_AFTER_DAYS` (10)."""
    return _baza(tmp_path, monkeypatch, dni_temu=12)


@pytest.fixture
def baza_swieza(tmp_path, monkeypatch):
    """Mecz z wczoraj — wynik moze jeszcze przyjsc, nikt nie ma prawa alarmowac."""
    return _baza(tmp_path, monkeypatch, dni_temu=1)


def _status(path: str) -> str:
    conn = sqlite3.connect(path)
    st = conn.execute("SELECT status FROM coupons WHERE id = 1").fetchone()[0]
    conn.close()
    return st


# -- licznik ---------------------------------------------------------------

def test_kupon_dziennika_poza_zasiegiem_ma_wlasny_licznik(baza_stara):
    """Bez licznika `skipped` miesza "jeszcze poczekamy" z "nigdy sie nie doczekamy"."""
    import footstats.core.coupon_settlement as cs

    stats = cs.settle_manual_coupons(dry_run=False, verbose=False)

    assert stats["skipped"] == 1
    assert stats.get("przeterminowane") == 1, (
        "brak licznika — kupon wisi ACTIVE i nikt nie wie, ze utknal na stale"
    )


def test_swiezy_kupon_nie_jest_przeterminowany(baza_swieza):
    """Alarm palacy sie na wczorajszym meczu przestaje cokolwiek znaczyc."""
    import footstats.core.coupon_settlement as cs

    stats = cs.settle_manual_coupons(dry_run=False, verbose=False)

    assert stats["skipped"] == 1
    assert stats.get("przeterminowane", 0) == 0


def test_status_zostaje_active_bo_dziennik_nalezy_do_uzytkownika(baza_stara):
    """Sedno decyzji: `set_coupon_result` wymaga ACTIVE (CAS-guard).

    Auto-VOID zamknalby uzytkownikowi jedyna droge wpisania wyniku, ktory on
    moze znac, a my nie. Kasujemy JEGO zapis za NASZ brak zrodla.
    """
    import footstats.core.coupon_settlement as cs

    cs.settle_manual_coupons(dry_run=False, verbose=False)

    assert _status(baza_stara) == "ACTIVE", (
        "auto-VOID odbiera userowi mozliwosc recznego rozliczenia (409 z CAS-guarda)"
    )


def test_przeterminowany_kupon_zostawia_ostrzezenie(baza_stara, caplog):
    """Bez logu utkniety kupon to zero linijek w Cloud Logging."""
    import footstats.core.coupon_settlement as cs

    with caplog.at_level(logging.WARNING, logger=cs.log.name):
        cs.settle_manual_coupons(dry_run=False, verbose=False)

    assert caplog.records, "kupon utknal po cichu — brak ostrzezenia w logu"
    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert "1" in tresc


# -- alarm -----------------------------------------------------------------

def test_alarm_milczy_gdy_nic_nie_utknelo():
    from footstats.core.coupon_settlement import dziennik_utknal

    assert dziennik_utknal(0) is None


def test_alarm_mowi_ile_i_czego_oczekuje_od_uzytkownika():
    from footstats.core.coupon_settlement import dziennik_utknal

    opis = dziennik_utknal(3)

    assert opis is not None
    assert "3" in opis
    # Alarm o kuponie AI kieruje na selekcje; ten ma kierowac na CZLOWIEKA,
    # bo tylko on moze ten wpis domknac.
    assert "recznie" in opis.lower() or "ręcznie" in opis.lower(), (
        "alarm ma mowic, ze wynik wpisuje uzytkownik — inaczej nikt nic nie zrobi"
    )


def test_alarm_nie_obiecuje_ze_system_to_naprawi():
    """Tresc alarmu nie moze sugerowac, ze kupon rozliczy sie sam."""
    from footstats.core.coupon_settlement import dziennik_utknal

    opis = dziennik_utknal(1).lower()

    assert "void" not in opis, (
        "alarm sugerujacy VOID klamie — status zostaje ACTIVE"
    )


# -- alarm wychodzi realna droga -------------------------------------------

def test_endpoint_alarmuje_gdy_dziennik_utknal(monkeypatch):
    """Detektor bez podpiecia to martwy kod."""
    import footstats.api.routes.coupons as rc
    import footstats.core.coupon_settlement as cs
    import footstats.utils.telegram_notify as tg

    monkeypatch.setenv("CRON_SECRET", "sekret")
    monkeypatch.setattr(cs, "settle_manual_coupons",
                        lambda **kw: {"settled": 0, "skipped": 4, "errors": 0,
                                      "z_zewnatrz": 0, "przeterminowane": 4})
    wyslane = []
    monkeypatch.setattr(tg, "send_alert", lambda tytul, tresc: wyslane.append(tresc))

    odp = rc.cron_settle_manual(x_cron_secret="sekret")

    assert wyslane, "cztery utkniete kupony bez jednego sygnalu"
    assert "4" in wyslane[0]
    assert odp["przeterminowane"] == 4, (
        "licznik nie wychodzi z endpointu — operator go nie zobaczy"
    )


def test_endpoint_milczy_gdy_dziennik_plynie(monkeypatch):
    import footstats.api.routes.coupons as rc
    import footstats.core.coupon_settlement as cs
    import footstats.utils.telegram_notify as tg

    monkeypatch.setenv("CRON_SECRET", "sekret")
    monkeypatch.setattr(cs, "settle_manual_coupons",
                        lambda **kw: {"settled": 2, "skipped": 1, "errors": 0,
                                      "z_zewnatrz": 0, "przeterminowane": 0})
    wyslane = []
    monkeypatch.setattr(tg, "send_alert", lambda tytul, tresc: wyslane.append(tresc))

    rc.cron_settle_manual(x_cron_secret="sekret")

    assert wyslane == [], "alarm palacy sie bez powodu przestaje cokolwiek znaczyc"


def test_kupon_ktory_da_sie_rozliczyc_nie_jest_przeterminowany(tmp_path, monkeypatch):
    """Stary mecz, ale wynik MAMY — to nie jest utkniecie, tylko zaleglosc."""
    import footstats.core.backtest as bt
    import footstats.core.coupon_settlement as cs
    from footstats.core import match_linker

    path = str(tmp_path / "ok.db")
    setup = sqlite3.connect(path)
    setup.executescript(_SCHEMA)
    stary = (datetime.now().date() - timedelta(days=12)).isoformat()
    setup.execute(
        "INSERT INTO coupons (status, legs_json, total_odds, stake_pln,"
        " match_date_first, kupon_type) VALUES (?,?,?,?,?,?)",
        ("ACTIVE", NOGA, 1.35, 2.0, stary, "manual"),
    )
    setup.commit()
    setup.close()

    class _Znalezione:
        matched = "exact"
        prediction = {"actual_result": "2-1"}

    import footstats.core.coupon_tracker as ct

    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(path))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    monkeypatch.setattr(ct, "_connect", lambda: _SQLiteConn(path))
    # DDL w `init_coupon_tables` jest postgresowe (SERIAL) — schemat testu
    # juz istnieje, wiec inicjalizacja nie ma tu nic do roboty.
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(match_linker, "link_leg", lambda *a, **k: _Znalezione())
    monkeypatch.setattr(cs, "_manual_zrodla_zewnetrzne", lambda: False)

    stats = cs.settle_manual_coupons(dry_run=False, verbose=False)

    assert stats["settled"] == 1
    assert stats.get("przeterminowane", 0) == 0
    assert _status(path) == "WON"
