"""Dziennik rozlicza się z `model_log`, zanim sięgnie po zewnętrzne API.

ZMIERZONE 25-28.08: kupon #149 wisiał ACTIVE dziesiąty dzień i trzeba go było
domknąć ręcznie, mimo że wynik jego meczu leżał w naszej bazie. `link_leg`
czyta wyłącznie `predictions` (161 wierszy na prod), a `model_log` — dziennik
kalibracyjny zapisujący każdy oceniony mecz — miał wtedy 424.

Dwa oddzielne roszczenia, dwa oddzielne testy:
  * noga bez predykcji, ale z wpisem w `model_log`, ROZLICZA SIĘ;
  * to źródło jest pytane PRZED zewnętrznymi API, więc przy włączonej fladze
    D5 nie generuje ani jednego wywołania limitowanego planu.

Fikstura `db` (z `test_settle_manual_zrodla`) wysadza test, gdy `_find_leg_result`
zostanie wywołane bez flagi — regres w kolejności źródeł byłby widoczny od razu.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

import footstats.core.backtest as backtest
import footstats.core.coupon_settlement as settlement
import footstats.core.coupon_tracker as coupon_tracker
import footstats.core.match_linker as match_linker
from footstats.core.match_linker import LinkResult

from tests.test_settle_manual_coupons import _SCHEMA, _SQLiteConn

DATA = "2026-07-20"

_SCHEMA_MODEL_LOG = """
CREATE TABLE IF NOT EXISTS model_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date    TEXT NOT NULL,
    team_home     TEXT NOT NULL,
    team_away     TEXT NOT NULL,
    actual_result TEXT
);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Własna plikowa SQLite z `coupons` + `model_log`; zero sieci."""
    sciezka = str(tmp_path / "test.db")
    setup = sqlite3.connect(sciezka)
    setup.executescript(_SCHEMA)
    setup.executescript(_SCHEMA_MODEL_LOG)
    setup.commit()
    setup.close()

    monkeypatch.setattr(backtest, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(backtest, "init_db", lambda: None)
    monkeypatch.setattr(coupon_tracker, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(coupon_tracker, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(match_linker, "connect", lambda: _SQLiteConn(sciezka))
    # Brak wpisu w `predictions` — stan 11 z 12 nóg serii 4.
    monkeypatch.setattr(match_linker, "link_leg",
                        lambda *a, **k: LinkResult(False, "none", None, "brak"))
    return sciezka


def _kupon(sciezka: str, nogi: list[dict], kurs: float = 2.0) -> int:
    conn = sqlite3.connect(sciezka)
    cur = conn.execute(
        """INSERT INTO coupons (status, kupon_type, legs_json, total_odds,
                                stake_pln, match_date_first, user_id)
           VALUES ('ACTIVE', 'manual', ?, ?, 10.0, ?, 1)""",
        (json.dumps(nogi), kurs, DATA),
    )
    conn.commit()
    kupon_id = cur.lastrowid
    conn.close()
    return kupon_id


def _wpis_model_log(sciezka: str, home: str, away: str, wynik: str | None) -> None:
    conn = sqlite3.connect(sciezka)
    conn.execute(
        "INSERT INTO model_log (match_date, team_home, team_away, actual_result)"
        " VALUES (?, ?, ?, ?)",
        (DATA, home, away, wynik),
    )
    conn.commit()
    conn.close()


def _status(sciezka: str, kupon_id: int) -> str:
    conn = sqlite3.connect(sciezka)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT status FROM coupons WHERE id = ?", (kupon_id,)).fetchone()
    conn.close()
    return row["status"]


def test_noga_bez_predykcji_rozlicza_sie_z_model_log(db):
    """SEDNO. Bez tego kupon #149 wisiał ACTIVE, choć wynik był w naszej bazie."""
    kupon_id = _kupon(db, [{"home": "Arsenal", "away": "Chelsea", "tip": "1"}])
    _wpis_model_log(db, "Arsenal", "Chelsea", "2-1")

    stats = settlement.settle_manual_coupons(verbose=False)

    assert stats["settled"] == 1
    assert stats["z_model_log"] == 1
    assert _status(db, kupon_id) == "WON"


def test_przegrana_noga_tez_rozlicza_kupon(db):
    """Kontrola: źródło nie może rozliczać tylko wygranych."""
    kupon_id = _kupon(db, [{"home": "Arsenal", "away": "Chelsea", "tip": "2"}])
    _wpis_model_log(db, "Arsenal", "Chelsea", "2-1")

    settlement.settle_manual_coupons(verbose=False)
    assert _status(db, kupon_id) == "LOST"


def test_mecz_bez_wyniku_zostawia_kupon_active(db):
    """Mecz w `model_log`, ale jeszcze nierozegrany — nie zgadujemy."""
    kupon_id = _kupon(db, [{"home": "Arsenal", "away": "Chelsea", "tip": "1"}])
    _wpis_model_log(db, "Arsenal", "Chelsea", None)

    stats = settlement.settle_manual_coupons(verbose=False)

    assert stats["settled"] == 0
    assert stats["z_model_log"] == 0
    assert _status(db, kupon_id) == "ACTIVE"


def test_model_log_pytany_przed_zrodlami_zewnetrznymi(db, monkeypatch):
    """KOLEJNOŚĆ ŹRÓDEŁ. `model_log` jest darmowy, zewnętrzne API kosztują
    wywołania limitowanego planu — przy dostępnym wpisie w naszej bazie nie
    wolno wykonać ani jednego."""
    monkeypatch.setenv("MANUAL_SETTLE_EXTERNAL", "1")
    import footstats.scrapers.results_updater as ru
    monkeypatch.setattr(ru, "_get_api_key", lambda: "klucz-af")
    monkeypatch.setenv("FOOTBALL_API_KEY", "klucz-fdb")

    def _nie_wolno(*_a, **_k):
        raise AssertionError("model_log ma być pytany PRZED zewnętrznymi API")

    monkeypatch.setattr(settlement, "_find_leg_result", _nie_wolno)

    kupon_id = _kupon(db, [{"home": "Arsenal", "away": "Chelsea", "tip": "1"}])
    _wpis_model_log(db, "Arsenal", "Chelsea", "2-1")

    stats = settlement.settle_manual_coupons(verbose=False)

    assert stats["z_model_log"] == 1
    assert stats["z_zewnatrz"] == 0
    assert _status(db, kupon_id) == "WON"


def test_kupon_wielonogi_wymaga_wszystkich_wynikow(db):
    """All-legs-or-nothing zostaje bez zmian: jedna noga z `model_log`,
    druga bez żadnego źródła → cały kupon ACTIVE."""
    kupon_id = _kupon(db, [
        {"home": "Arsenal", "away": "Chelsea", "tip": "1"},
        {"home": "Roma", "away": "Lazio", "tip": "1"},
    ])
    _wpis_model_log(db, "Arsenal", "Chelsea", "2-1")

    stats = settlement.settle_manual_coupons(verbose=False)

    assert stats["settled"] == 0
    assert _status(db, kupon_id) == "ACTIVE"


def test_dwa_rozne_mecze_w_oknie_nie_rozliczaja_kuponu(db):
    """Niejednoznaczność w `model_log` musi zachować się jak brak danych,
    nie jak wynik — rozliczenie z niewłaściwego meczu jest nieodwracalne."""
    kupon_id = _kupon(db, [{"home": "Arsenal", "away": "Chelsea", "tip": "1"}])
    _wpis_model_log(db, "Arsenal", "Chelsea", "2-1")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO model_log (match_date, team_home, team_away, actual_result)"
        " VALUES ('2026-07-21', 'Arsenal', 'Chelsea', '0-3')"
    )
    conn.commit()
    conn.close()

    stats = settlement.settle_manual_coupons(verbose=False)

    assert stats["settled"] == 0
    assert _status(db, kupon_id) == "ACTIVE"
