"""Evening agent: raport z bazy, brak nadpisywania nóg, coupons.settled_at.

Źródło wyników API-Football jest wyłączone (APISPORTS_ENABLED=0), więc `fixtures`
są puste, a kupony rozlicza `/cron/settle`. Dotąd evening mimo to zerował
`result/leg_won` każdej nogi i raportował „Sprawdzono N, W 0, L 0”.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from tests.test_evening_agent import _SCHEMA, _SQLiteConn

@pytest.fixture
def baza(tmp_path, monkeypatch):
    """Lokalny SQLite z kolumną settled_at; zero kontaktu z prod."""
    path = str(tmp_path / "raport.db")
    setup = sqlite3.connect(path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()
    fabryka = lambda: _SQLiteConn(path)  # noqa: E731

    import footstats.core.backtest as bt
    import footstats.core.coupon_tracker as ct
    import footstats.core.bankroll as bk

    monkeypatch.setattr(ct, "_connect", fabryka)
    monkeypatch.setattr(bt, "_connect", fabryka)
    monkeypatch.setattr(bk, "_db_connect", fabryka)
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(bt, "init_db", lambda: None)
    import footstats.evening_agent as ea
    monkeypatch.setattr(ea, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(ea, "init_db", lambda: None)
    return path


def _wstaw(path: str, status: str, legs: list[dict], kupon_type: str = "A",
           settled_at: str | None = None, match_date_first: str | None = None) -> int:
    conn = sqlite3.connect(path)
    cur = conn.execute(
        "INSERT INTO coupons (status, kupon_type, legs_json, stake_pln, total_odds,"
        " settled_at, match_date_first, user_id) VALUES (?,?,?,?,?,?,?,1)",
        (status, kupon_type, json.dumps(legs), 10.0, 2.0, settled_at, match_date_first),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return int(cid)


def _nogi_z_bazy(path: str, cid: int) -> list[dict]:
    conn = sqlite3.connect(path)
    raw = conn.execute("SELECT legs_json FROM coupons WHERE id=?", (cid,)).fetchone()[0]
    conn.close()
    return json.loads(raw)


def _uruchom(fixtures: list[dict]) -> dict:
    from footstats.evening_agent import run_evening_agent
    with patch("footstats.evening_agent._fetch_results_today", return_value=fixtures), \
         patch("footstats.evening_agent._kurs_zamkniecia_nogi", return_value=None), \
         patch("footstats.core.clv_zalegle.uzupelnij_clv_zaleglych", return_value=(0, 0)), \
         patch("footstats.evening_agent._send_telegram_summary"), \
         patch("footstats.utils.telegram_notify.check_and_alert_agent_down"), \
         patch("footstats.scrapers.results_updater.update_pending", return_value={}), \
         patch("footstats.evening_agent.load_dotenv"), \
         patch("footstats.db.migrations.run_migrations"):
        return run_evening_agent("2026-11-05")


def _fixture(home: str, away: str, hg: int, ag: int) -> dict:
    return {
        "fixture": {"id": 1, "status": {"short": "FT"}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": hg, "away": ag},
    }


# ── puste fixtures: żadnych zapisów ─────────────────────────────────────────

def test_puste_fixtures_nie_zapisuja_nog_ani_statusu(baza):
    nogi = [{"gospodarz": "A", "goscie": "B", "typ": "1", "result": "2-0", "leg_won": True}]
    cid = _wstaw(baza, "ACTIVE", nogi)

    with patch("footstats.evening_agent._save_coupon_legs") as zapis, \
         patch("footstats.evening_agent.update_coupon_status") as status:
        summary = _uruchom([])

    zapis.assert_not_called()
    status.assert_not_called()
    assert _nogi_z_bazy(baza, cid)[0]["leg_won"] is True
    assert summary["checked"] == 0 and summary["active"] == 0


# ── niepuste fixtures ───────────────────────────────────────────────────────

def test_kupon_manual_pomijany_przy_niepustych_fixtures(baza):
    nogi = [{"gospodarz": "Arsenal", "goscie": "Chelsea", "typ": "1"}]
    cid = _wstaw(baza, "ACTIVE", nogi, kupon_type="manual")

    with patch("footstats.evening_agent._save_coupon_legs") as zapis, \
         patch("footstats.evening_agent.update_coupon_status") as status, \
         patch("footstats.evening_agent.credit_win") as kredyt:
        _uruchom([_fixture("Arsenal", "Chelsea", 2, 0)])

    zapis.assert_not_called()
    status.assert_not_called()
    kredyt.assert_not_called()
    assert "leg_won" not in _nogi_z_bazy(baza, cid)[0]


def test_wczorajsza_noga_z_wynikiem_zostaje(baza):
    nogi = [
        {"gospodarz": "Wczoraj", "goscie": "Mecz", "typ": "1",
         "result": "3-0", "leg_won": True},
        {"gospodarz": "Arsenal", "goscie": "Chelsea", "typ": "1"},
    ]
    cid = _wstaw(baza, "ACTIVE", nogi)
    # Dzisiaj gra tylko druga noga; pierwszej nie ma w fixtures.
    summary = _uruchom([_fixture("Arsenal", "Chelsea", 2, 0)])

    po = _nogi_z_bazy(baza, cid)
    assert po[0]["leg_won"] is True and po[0]["result"] == "3-0"
    assert po[1]["leg_won"] is True
    assert summary["won"] == 1  # obie nogi wygrane -> WON


def test_noga_bez_rozstrzygniecia_to_pending_nie_void(baza):
    """oblicz_tip_correct == None (typ niemożliwy do oceny) nie może dać VOID."""
    nogi = [{"gospodarz": "Arsenal", "goscie": "Chelsea", "typ": "Inny rynek xyz"}]
    cid = _wstaw(baza, "ACTIVE", nogi)

    with patch("footstats.evening_agent.oblicz_tip_correct", return_value=None):
        summary = _uruchom([_fixture("Arsenal", "Chelsea", 2, 0)])

    assert summary["active"] == 1
    conn = sqlite3.connect(baza)
    assert conn.execute("SELECT status FROM coupons WHERE id=?", (cid,)).fetchone()[0] == "ACTIVE"
    conn.close()


def test_status_przegrana_noga_przy_pending_to_lost():
    from footstats.evening_agent import _status_kuponu
    assert _status_kuponu(["LOSS", "PENDING"]) == "LOST"
    assert _status_kuponu(["WIN", "PENDING"]) == "ACTIVE"


# ── settled_at ──────────────────────────────────────────────────────────────

def _settled_at(path: str, cid: int):
    conn = sqlite3.connect(path)
    v = conn.execute("SELECT settled_at FROM coupons WHERE id=?", (cid,)).fetchone()[0]
    conn.close()
    return v


def test_update_coupon_status_ustawia_settled_at(baza):
    from footstats.core.coupon_tracker import update_coupon_status
    cid = _wstaw(baza, "ACTIVE", [])

    assert update_coupon_status(cid, "LOST", payout_pln=0.0) is True

    assert _settled_at(baza, cid) is not None


def test_korekta_won_won_nie_nadpisuje_settled_at(baza):
    from footstats.core.coupon_tracker import update_coupon_status
    cid = _wstaw(baza, "WON", [], settled_at="2026-11-01 10:00:00")

    update_coupon_status(cid, "WON", payout_pln=17.6)

    assert _settled_at(baza, cid) == "2026-11-01 10:00:00"


def test_ustawienie_active_nie_ustawia_settled_at(baza):
    from footstats.core.coupon_tracker import update_coupon_status
    cid = _wstaw(baza, "DRAFT", [])

    update_coupon_status(cid, "ACTIVE")

    assert _settled_at(baza, cid) is None


# ── raport z bazy ───────────────────────────────────────────────────────────

def test_statystyki_raportu_licza_z_bazy(baza):
    from footstats.evening_agent import _statystyki_raportu
    teraz = datetime.now()
    swiezo = (teraz - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    dawno = (teraz - timedelta(hours=60)).strftime("%Y-%m-%d %H:%M:%S")
    wczoraj = (date.today() - timedelta(days=3)).isoformat()
    dzis = date.today().isoformat()
    _wstaw(baza, "WON", [], settled_at=swiezo)
    _wstaw(baza, "LOST", [], settled_at=swiezo)
    _wstaw(baza, "LOST", [], settled_at=swiezo)
    _wstaw(baza, "VOID", [], settled_at=swiezo)
    _wstaw(baza, "WON", [], settled_at=dawno)           # poza oknem 24 h
    _wstaw(baza, "LOST", [], settled_at=None)           # stary, bez znacznika
    _wstaw(baza, "ACTIVE", [{"match_date": wczoraj}])    # zaległy
    _wstaw(baza, "ACTIVE", [{"match_date": dzis}])       # świeży
    _wstaw(baza, "DRAFT", [{"match_date": dzis}, {"match_date": wczoraj}])  # ostatnia dziś

    st = _statystyki_raportu()

    assert st == {"won": 1, "lost": 2, "void": 1, "aktywne": 3, "zalegle": 1}


def test_telegram_podaje_liczby_z_bazy(baza):
    from footstats.evening_agent import _send_telegram_summary
    _wstaw(baza, "WON", [], settled_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    wyslane: list[str] = []

    with patch("footstats.utils.telegram_notify.send_message", side_effect=wyslane.append):
        _send_telegram_summary({"checked": 99}, "2026-11-05")

    msg = wyslane[0]
    assert "Sprawdzono" not in msg
    assert "Rozliczone w 24 h: W 1 / L 0 / V 0" in msg
    assert "Aktywne: 0, w tym zaległe 0" in msg


def test_blad_zapytania_raportu_nie_wywraca_joba(baza):
    from footstats.evening_agent import _send_telegram_summary
    wyslane: list[str] = []

    with patch("footstats.evening_agent._statystyki_raportu", side_effect=OSError("db")), \
         patch("footstats.utils.telegram_notify.send_message", side_effect=wyslane.append):
        _send_telegram_summary({}, "2026-11-05")

    assert "brak danych" in wyslane[0]


# ── migracja ────────────────────────────────────────────────────────────────

def test_migracja_settled_at_idempotentna(tmp_path):
    from footstats.db.migrations import _get_migrations_for_dialect
    wersje = {v: (n, s) for v, n, s in _get_migrations_for_dialect("sqlite")}
    assert any("settled_at" in sql for _, (_, st) in wersje.items() for sql in st)
    nazwa, stmts = next((n, s) for v, (n, s) in wersje.items()
                        if any("settled_at" in q for q in s))

    conn = sqlite3.connect(str(tmp_path / "m.db"))
    conn.execute("CREATE TABLE coupons (id INTEGER PRIMARY KEY, status TEXT)")
    conn.execute("INSERT INTO coupons (status) VALUES ('WON')")
    from footstats.db.migrations import _exec_statements
    _exec_statements(conn, stmts, "sqlite")
    _exec_statements(conn, stmts, "sqlite")  # drugi raz: bez wyjątku

    kolumny = [r[1] for r in conn.execute("PRAGMA table_info(coupons)")]
    assert kolumny.count("settled_at") == 1
    assert conn.execute("SELECT settled_at FROM coupons").fetchone()[0] is None
    assert nazwa
