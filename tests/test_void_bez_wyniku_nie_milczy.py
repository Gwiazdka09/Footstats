"""Kupon skasowany przez upływ czasu nie może zniknąć bez śladu.

ZMIERZONE 2026-08-24 na produkcji: 20 kuponów z 15.08 wisi ACTIVE z wszystkimi
nogami `result: null`. Mecze mają 9 dni, a `HORYZONT_ZRODEL_DNI = 7` — żadne
źródło już ich nie odda. Nazajutrz mija `VOID_AFTER_DAYS = 10` i wszystkie
dwadzieścia zostanie oznaczonych VOID, wypadając z accuracy i ROI na stałe.

Samo VOID jest POPRAWNE — wyniku naprawdę nie ma skąd wziąć. Problemem jest cisza:

- ścieżka „dogrywka/karne" (`powod_nierozliczalny`) woła `log.warning` z powodem,
- ścieżka „brak wyniku po N dniach" robi wyłącznie `print` pod `verbose`,
- obie zliczają się do tego samego `stats["voided"]`.

Skutek: nie da się odróżnić trzech meczów rozstrzygniętych po karnych od dwudziestu
kuponów zabitych przez zawieszone konto API-Football. A różnica jest zasadnicza —
pierwsze to normalna praca systemu, drugie to awaria źródeł, która trwa i będzie
zjadać kolejne kupony.

To ten sam kształt, co reszta usterek z 24.08: system robi dokładnie to, co ma
zrobić, wynik jest zły, i nikt się nie dowiaduje.
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
CREATE TABLE bankroll_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT, balance REAL,
    updated_at TEXT, user_id INTEGER DEFAULT 1 UNIQUE
);
CREATE TABLE bankroll_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, change_pln REAL,
    new_balance REAL, type TEXT, description TEXT, user_id INTEGER DEFAULT 1
);
"""

# Noga bez wyniku — dokładnie to, co siedzi w produkcji przy tych 20 kuponach.
NOGA = ('[{"home": "Grimsby Town", "away": "Shrewsbury Town", "tip": "BTTS",'
        ' "odds": 1.8, "mecz": "Grimsby Town vs Shrewsbury Town",'
        ' "result": null, "leg_won": null}]')


@pytest.fixture
def baza(tmp_path, monkeypatch):
    """Jeden kupon ACTIVE poza zasięgiem źródeł, którego wyniku nie da się zdobyć."""
    path = str(tmp_path / "settle.db")
    setup = sqlite3.connect(path)
    setup.executescript(_SCHEMA)

    # 12 dni wstecz: poza HORYZONT_ZRODEL_DNI (7) i poza VOID_AFTER_DAYS (10).
    stary = (datetime.now().date() - timedelta(days=12)).isoformat()
    setup.execute(
        "INSERT INTO coupons (status, legs_json, total_odds, stake_pln,"
        " match_date_first, kupon_type) VALUES (?,?,?,?,?,?)",
        ("ACTIVE", NOGA, 1.8, 2.0, stary, "SINGLE"),
    )
    setup.commit()
    setup.close()

    import footstats.core.backtest as bt
    import footstats.core.coupon_settlement as cs

    monkeypatch.setattr(cs, "_connect", lambda: _SQLiteConn(path), raising=False)
    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(path))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    # Zadne zrodlo nie odda wyniku — tak jak w produkcji dla meczow sprzed 9 dni.
    monkeypatch.setattr(cs, "_find_leg_result", lambda *a, **k: None)
    return path


def _status(path: str) -> str:
    conn = sqlite3.connect(path)
    st = conn.execute("SELECT status FROM coupons WHERE id = 1").fetchone()[0]
    conn.close()
    return st


def test_void_z_braku_wyniku_zostawia_ostrzezenie(baza, caplog):
    """Bez logu dwadzieścia skasowanych kuponów to zero linijek w Cloud Logging."""
    import footstats.core.coupon_settlement as cs

    with caplog.at_level(logging.WARNING, logger=cs.log.name):
        cs.settle_active_coupons(dry_run=False, verbose=False)

    assert _status(baza) == "VOID"
    assert caplog.records, "kupon skasowany po cichu — brak ostrzezenia w logu"

    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert "Grimsby Town" in tresc, f"log nie mowi KTORY mecz przepadl: {tresc}"


def test_licznik_oddziela_brak_wyniku_od_reszty(baza):
    """`voided` miesza karne z awaria zrodel — potrzebny osobny licznik."""
    import footstats.core.coupon_settlement as cs

    stats = cs.settle_active_coupons(dry_run=False, verbose=False)

    assert stats["voided"] == 1
    assert stats.get("voided_brak_wyniku") == 1, (
        "brak osobnego licznika — nie odroznisz dogrywki od awarii zrodel"
    )


def test_suchy_przebieg_nic_nie_kasuje(baza):
    """`--dry` ma pokazywac, nie wykonywac."""
    import footstats.core.coupon_settlement as cs

    stats = cs.settle_active_coupons(dry_run=True, verbose=False)

    assert _status(baza) == "ACTIVE"
    assert stats.get("voided_brak_wyniku") == 1


# ── alarm ──────────────────────────────────────────────────────────────────

def test_alarm_milczy_gdy_nic_nie_przepadlo():
    """Alarm palacy sie co przebieg przestaje cokolwiek znaczyc."""
    from footstats.core.coupon_settlement import kupony_przepadly

    assert kupony_przepadly(0) is None


def test_alarm_mowi_ile_i_dlaczego():
    from footstats.core.coupon_settlement import kupony_przepadly

    opis = kupony_przepadly(20)

    assert opis is not None
    assert "20" in opis
    # Operator ma z tego wiedziec, gdzie szukac, a nie tylko ze "cos znikelo".
    # Rdzen bez koncowki — komunikat moze odmieniac (zrodlo/zrodla/zrodel).
    assert "zrodl" in opis.lower() or "źródł" in opis.lower()
    assert "selekcj" in opis.lower(), (
        "alarm ma kierowac na prawdziwa przyczyne — dobor meczow, nie samo rozliczanie"
    )


# ── alarm wychodzi realna droga, nie tylko istnieje ────────────────────────

def test_endpoint_alarmuje_gdy_kupony_przepadly(monkeypatch):
    """Detektor bez podpiecia to martwy kod.

    Scenariusz jest DOKLADNIE ten z produkcji 25.08: `czekajace_w_zasiegu = 0`,
    wiec `rozliczanie_stoi` milczy — i slusznie, bo tych wynikow naprawde nie ma
    skad wziac. Bez drugiego alarmu 20 kuponow znika przy calkowitej ciszy.
    """
    import footstats.api.routes.coupons as rc
    import footstats.core.coupon_settlement as cs
    import footstats.utils.telegram_notify as tg

    monkeypatch.setenv("CRON_SECRET", "sekret")
    monkeypatch.setattr(cs, "settle_active_coupons",
                        lambda **kw: {"settled": 0, "partial": 13, "errors": 0,
                                      "voided": 20, "voided_brak_wyniku": 20,
                                      "czekajace_w_zasiegu": 0})
    wyslane = []
    monkeypatch.setattr(tg, "send_alert", lambda tytul, tresc: wyslane.append(tresc))

    odp = rc.cron_settle(x_cron_secret="sekret")

    assert wyslane, "20 kuponow przepadlo bez jednego sygnalu"
    assert "20" in wyslane[0]
    assert odp["voided_brak_wyniku"] == 20, (
        "licznik nie wychodzi z endpointu — operator go nie zobaczy"
    )


def test_endpoint_milczy_gdy_nic_nie_przepadlo(monkeypatch):
    import footstats.api.routes.coupons as rc
    import footstats.core.coupon_settlement as cs
    import footstats.utils.telegram_notify as tg

    monkeypatch.setenv("CRON_SECRET", "sekret")
    monkeypatch.setattr(cs, "settle_active_coupons",
                        lambda **kw: {"settled": 4, "partial": 2, "errors": 0,
                                      "voided": 0, "voided_brak_wyniku": 0,
                                      "czekajace_w_zasiegu": 0})
    wyslane = []
    monkeypatch.setattr(tg, "send_alert", lambda tytul, tresc: wyslane.append(tresc))

    rc.cron_settle(x_cron_secret="sekret")

    assert wyslane == [], "alarm palacy sie bez powodu przestaje cokolwiek znaczyc"


def test_void_po_karnych_nie_liczy_sie_jako_awaria_zrodel(monkeypatch):
    """Rozroznienie, o ktore chodzi w calym tym pliku.

    Mecz rozstrzygniety po karnych tez konczy sie VOID-em, ale to normalna praca
    systemu — zaden alarm sie nie nalezy. Gdyby oba trafialy do jednego licznika,
    kazda seria dogrywek udawalaby awarie zrodel.
    """
    import footstats.api.routes.coupons as rc
    import footstats.core.coupon_settlement as cs
    import footstats.utils.telegram_notify as tg

    monkeypatch.setenv("CRON_SECRET", "sekret")
    monkeypatch.setattr(cs, "settle_active_coupons",
                        lambda **kw: {"settled": 3, "partial": 1, "errors": 0,
                                      "voided": 5, "voided_brak_wyniku": 0,
                                      "czekajace_w_zasiegu": 0})
    wyslane = []
    monkeypatch.setattr(tg, "send_alert", lambda tytul, tresc: wyslane.append(tresc))

    rc.cron_settle(x_cron_secret="sekret")

    assert wyslane == [], "dogrywki zglaszane jako awaria zrodel"
