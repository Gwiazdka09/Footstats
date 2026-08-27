"""Migracja 16 — tabela odds_snapshots dla pilotu rozrzutu kursow."""
import sqlite3

import pytest

from footstats.db import migrations

# Komplet kolumn ze specu (13) — jedno zrodlo prawdy dla obu testow ponizej.
_KOLUMNY_ZE_SPECU: frozenset[str] = frozenset({
    "id", "captured_at", "snapshot_date", "sport_key", "event_id",
    "commence_time", "team_home", "team_away", "market", "line",
    "outcome", "bookmaker", "price",
})
# Indeks unikalny, na ktorym opiera sie idempotencja zapisu — musi obejmowac
# bukmachera, bo to wlasnie os, dla ktorej zbieramy surowe kwoty.
_INDEKS_UNIKALNY_KOLUMNY = "(snapshot_date, event_id, market, line, outcome, bookmaker)"


def _kolumny(conn, tabela: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def _sql_migracji_16(dialekt: str) -> str:
    """Zescala wszystkie statementy migracji 16 dla danego dialektu w jeden tekst."""
    return " ".join(
        " ".join(m[2])
        for m in migrations._get_migrations_for_dialect(dialekt)
        if m[0] == 16
    ).lower()


def test_migracja_16_tworzy_tabele_odds_snapshots(tmp_path):
    """Tabela musi powstac z kompletem kolumn w gałęzi SQLite."""
    baza = tmp_path / "test.db"
    conn = sqlite3.connect(baza)
    migracje = migrations._get_migrations_for_dialect("sqlite")
    wpis = [m for m in migracje if m[0] == 16]
    assert wpis, "brak migracji 16 w gałęzi sqlite"
    for sql in wpis[0][2]:
        conn.execute(sql)
    assert _kolumny(conn, "odds_snapshots") == _KOLUMNY_ZE_SPECU
    conn.close()


def test_migracja_16_jest_w_obu_dialektach():
    """Rozjazd dialektow jest cichy: testy chodza na SQLite, produkcja na Postgresie.

    Sam numer migracji na liscie juz bronia
    `test_migracja_clv.py::test_oba_dialekty_maja_ten_sam_zestaw_numerow` i
    `test_model_source_predykcji.py::test_numeracja_migracji_bez_dziur_i_zgodna_miedzy_dialektami`.
    Tutaj sprawdzamy TRESC SQL osobno dla kazdego dialektu: komplet kolumn i
    indeks unikalny z szescioma kolumnami musza byc identyczne w SQLite i w
    PostgreSQL, bo od nich zalezy idempotencja zapisu na produkcji.
    """
    for dialekt in ("sqlite", "postgresql"):
        sql = _sql_migracji_16(dialekt)
        assert sql, f"brak migracji 16 w gałęzi {dialekt}"
        for kolumna in _KOLUMNY_ZE_SPECU:
            assert kolumna in sql, f"brak kolumny {kolumna} w migracji 16 dla {dialekt}"
        assert "ux_odds_snapshots_dzien" in sql, f"brak indeksu unikalnego w {dialekt}"
        assert _INDEKS_UNIKALNY_KOLUMNY in sql, (
            f"indeks unikalny nie obejmuje wlasciwych 6 kolumn w {dialekt}"
        )


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
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql_ins, wiersz)
    conn.close()
