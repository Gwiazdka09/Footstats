"""Zapis migawek kursow — idempotentny w obrebie doby.

Baza tymczasowa SQLite z migracji 16. NIGDY prod (`.claude/rules/tests-no-prod.md`).
"""
from __future__ import annotations

import sqlite3

import pytest

from footstats.core import odds_store
from footstats.db import migrations


def _wiersz(bookmaker="pinnacle", outcome="Draw", price=4.21,
            market="h2h", line=0.0, event="abc123"):
    return {
        "sport_key": "soccer_epl",
        "event_id": event,
        "commence_time": "2026-08-27T14:00:00Z",
        "team_home": "Crystal Palace",
        "team_away": "Manchester City",
        "market": market,
        "line": line,
        "outcome": outcome,
        "bookmaker": bookmaker,
        "price": price,
    }


@pytest.fixture()
def conn(tmp_path):
    c = sqlite3.connect(tmp_path / "test.db")
    c.row_factory = sqlite3.Row
    migracja = [m for m in migrations._get_migrations_for_dialect("sqlite") if m[0] == 16][0]
    for sql in migracja[2]:
        c.execute(sql)
    yield c
    c.close()


def _ile(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM odds_snapshots").fetchone()["n"]


def test_zapis_wstawia_wiersze(conn):
    stat = odds_store.zapisz_migawke(
        [_wiersz(), _wiersz("everygame", price=4.00)], conn=conn, dzien="2026-08-27")
    assert stat["zapisane"] == 2
    assert _ile(conn) == 2


def test_dry_run_niczego_nie_zapisuje(conn):
    stat = odds_store.zapisz_migawke([_wiersz()], conn=conn,
                                     dzien="2026-08-27", dry_run=True)
    assert stat["zapisane"] == 1
    assert _ile(conn) == 0, "dry_run nie moze pisac do bazy"


def test_drugi_przebieg_tego_samego_dnia_nie_duplikuje(conn):
    odds_store.zapisz_migawke([_wiersz()], conn=conn, dzien="2026-08-27")
    stat = odds_store.zapisz_migawke([_wiersz()], conn=conn, dzien="2026-08-27")
    assert _ile(conn) == 1
    assert stat["pominiete"] == 1
    assert stat["zapisane"] == 0


def test_duplikat_w_JEDNEJ_partii_tez_jest_odsiewany(conn):
    """Ten sam wiersz dwa razy w jednym wywolaniu. Bez tego indeks unikalny
    rzucilby wyjatek w polowie partii, a w Postgresie przerwalby CALA transakcje
    — czyli reszta ~3000 wierszy migawki przepadlaby przez jeden duplikat."""
    stat = odds_store.zapisz_migawke([_wiersz(), _wiersz()], conn=conn,
                                     dzien="2026-08-27")
    assert _ile(conn) == 1
    assert stat["zapisane"] == 1
    assert stat["pominiete"] == 1


def test_ten_sam_wiersz_w_kolejnej_dobie_wchodzi_jako_nowy(conn):
    """Pilot narasta dzien po dniu — blokada duplikatow nie moze zablokowac jutra."""
    odds_store.zapisz_migawke([_wiersz()], conn=conn, dzien="2026-08-27")
    odds_store.zapisz_migawke([_wiersz()], conn=conn, dzien="2026-08-28")
    assert _ile(conn) == 2


def test_rozne_ksiazki_tego_samego_wyniku_to_rozne_wiersze(conn):
    """Os, dla ktorej caly pilot istnieje. Gdyby bookmaker wypadl z klucza,
    zostawalaby jedna cena na wynik i rozrzutu nie byloby jak policzyc."""
    odds_store.zapisz_migawke(
        [_wiersz("pinnacle", price=4.21), _wiersz("betfair_ex_eu", price=4.20)],
        conn=conn, dzien="2026-08-27")
    assert _ile(conn) == 2


def test_rynek_h2h_z_linia_zero_nie_jest_odrzucany(conn):
    """`line` = 0.0 jest wartoscia poprawna (rynek bez linii), nie brakiem.
    Sprawdzanie falsy zamiast `is None` wyrzucaloby KAZDE kwotowanie 1X2."""
    stat = odds_store.zapisz_migawke([_wiersz(market="h2h", line=0.0)],
                                     conn=conn, dzien="2026-08-27")
    assert stat["odrzucone"] == 0
    assert _ile(conn) == 1


def test_wiersz_bez_wymaganego_pola_jest_pomijany_a_nie_wywala(conn):
    zly = _wiersz()
    del zly["bookmaker"]
    stat = odds_store.zapisz_migawke([zly, _wiersz()], conn=conn, dzien="2026-08-27")
    assert stat["odrzucone"] == 1
    assert _ile(conn) == 1


def test_pusta_lista_zwraca_zera(conn):
    stat = odds_store.zapisz_migawke([], conn=conn, dzien="2026-08-27")
    assert stat == {"kandydaci": 0, "zapisane": 0, "pominiete": 0, "odrzucone": 0}


def test_zapisane_wartosci_zgadzaja_sie_z_wejsciem(conn):
    odds_store.zapisz_migawke([_wiersz(market="totals", line=2.5, outcome="Over",
                                       price=1.90, bookmaker="pinnacle")],
                              conn=conn, dzien="2026-08-27")
    r = conn.execute("SELECT * FROM odds_snapshots").fetchone()
    assert r["snapshot_date"] == "2026-08-27"
    assert r["market"] == "totals"
    assert r["line"] == pytest.approx(2.5)
    assert r["outcome"] == "Over"
    assert r["bookmaker"] == "pinnacle"
    assert r["price"] == pytest.approx(1.90)
