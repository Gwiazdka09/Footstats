"""Migracja 16 — tabela odds_snapshots dla pilotu rozrzutu kursow."""
import sqlite3

from footstats.db import migrations


def _kolumny(conn, tabela: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def test_migracja_16_tworzy_tabele_odds_snapshots(tmp_path, monkeypatch):
    """Tabela musi powstac z kompletem kolumn w gałęzi SQLite."""
    baza = tmp_path / "test.db"
    conn = sqlite3.connect(baza)
    migracje = migrations._get_migrations_for_dialect("sqlite")
    wpis = [m for m in migracje if m[0] == 16]
    assert wpis, "brak migracji 16 w gałęzi sqlite"
    for sql in wpis[0][2]:
        conn.execute(sql)
    assert _kolumny(conn, "odds_snapshots") == {
        "id", "captured_at", "snapshot_date", "sport_key", "event_id",
        "commence_time", "team_home", "team_away", "market", "line",
        "outcome", "bookmaker", "price",
    }
    conn.close()


def test_migracja_16_jest_w_obu_dialektach():
    """Rozjazd dialektow jest cichy: testy chodza na SQLite, produkcja na Postgresie."""
    for dialekt in ("sqlite", "postgresql"):
        numery = [m[0] for m in migrations._get_migrations_for_dialect(dialekt)]
        assert 16 in numery, f"brak migracji 16 w gałęzi {dialekt}"


def test_migracja_16_indeks_unikalny_blokuje_duplikat(tmp_path):
    """Idempotencja zapisu opiera sie na tym indeksie — bez niego dwa przebiegi
    tego samego dnia zdublowalyby kazdy wiersz."""
    conn = sqlite3.connect(tmp_path / "test.db")
    for sql in [m for m in migrations._get_migrations_for_dialect("sqlite") if m[0] == 16][0][2]:
        conn.execute(sql)
    wiersz = ("2026-08-27", "soccer_epl", "abc", "2026-08-27T14:00:00Z",
              "Crystal Palace", "Manchester City", "h2h", 0.0, "Draw", "pinnacle", 4.21)
    sql_ins = ("INSERT INTO odds_snapshots (snapshot_date, sport_key, event_id,"
               " commence_time, team_home, team_away, market, line, outcome,"
               " bookmaker, price) VALUES (?,?,?,?,?,?,?,?,?,?,?)")
    conn.execute(sql_ins, wiersz)
    try:
        conn.execute(sql_ins, wiersz)
        assert False, "indeks unikalny nie zadzialal — duplikat przeszedl"
    except sqlite3.IntegrityError:
        pass
    conn.close()
