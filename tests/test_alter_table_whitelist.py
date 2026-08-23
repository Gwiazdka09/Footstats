"""B6 — jedyne dynamicznie sklejane SQL w projekcie.

`init_player_table` robi `ALTER TABLE player_stats ADD COLUMN {col} {typ}`, gdzie
nazwa i typ ida do zapytania przez f-string, bo SQLite nie pozwala parametryzowac
IDENTYFIKATOROW — `?` dziala dla wartosci, nie dla nazw kolumn. Parametryzacja
jest tu fizycznie niemozliwa, wiec jedyna obrona jest walidacja.

DZIS NIE JEST TO PODATNOSC i nie udaje, ze jest: `_OPTIONAL_COLS` to stala
w module, a nie dane z zewnatrz. Wartosc tej zmiany polega na czym innym —
zamienia „bezpieczne, bo nikt tego nie zmienil" na „bezpieczne, bo sprawdzane".
Roznica robi sie istotna w dniu, w ktorym ktos zechce wziac liste kolumn
z konfiguracji albo z odpowiedzi zrodla — a wtedy nikt nie bedzie pamietal,
ze ten f-string jest bezbronny.

Test celowo probuje przemycic ladunek przez OBA pola (nazwe i typ), bo walidacja
tylko nazwy zostawialaby druga polowe zapytania otwarta.
"""
from __future__ import annotations

import sqlite3

import pytest

from footstats.core.player_db import (
    _DOZWOLONE_TYPY,
    _sprawdz_identyfikator,
    init_player_table,
)


# ── co ma przechodzic ────────────────────────────────────────────────────────

@pytest.mark.parametrize("kolumna,typ", [("rating", "REAL"), ("xg", "REAL")])
def test_realne_kolumny_przechodza(kolumna: str, typ: str):
    """Te dwie sa w `_OPTIONAL_COLS` — gdyby walidacja je odrzucala, migracja
    padlaby przy kazdym starcie."""
    _sprawdz_identyfikator(kolumna, typ)


@pytest.mark.parametrize("typ", sorted(_DOZWOLONE_TYPY))
def test_kazdy_dozwolony_typ_przechodzi(typ: str):
    _sprawdz_identyfikator("jakas_kolumna", typ)


# ── co ma odpadac ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kolumna", [
    "rating; DROP TABLE player_stats",
    "rating, extra TEXT",
    "rating)--",
    "rating'",
    'rating"',
    "rating stats",
    "",
    "1rating",
])
def test_ladunek_w_nazwie_kolumny_odpada(kolumna: str):
    with pytest.raises(ValueError):
        _sprawdz_identyfikator(kolumna, "REAL")


@pytest.mark.parametrize("typ", [
    "REAL; DROP TABLE player_stats",
    "REAL DEFAULT (SELECT 1)",
    "BLOB",
    "REAL'",
    "",
])
def test_ladunek_w_TYPIE_odpada(typ: str):
    """Walidacja samej nazwy zostawialaby druga polowe zapytania otwarta."""
    with pytest.raises(ValueError):
        _sprawdz_identyfikator("rating", typ)


# ── ochrona dziala na prawdziwej sciezce, nie tylko w helperze ───────────────

def test_migracja_odrzuca_zatruta_kolumne(tmp_path, monkeypatch):
    """Sedno: helper podpiety do `init_player_table`, a nie stojacy obok niego."""
    from footstats.core import player_db

    monkeypatch.setattr(player_db, "_OPTIONAL_COLS",
                        {"zle; DROP TABLE player_stats": "REAL"})

    with pytest.raises(ValueError):
        init_player_table(tmp_path / "t.db")


def test_migracja_dziala_normalnie(tmp_path):
    """Walidacja nie moze zepsuc tego, co dziala — kolumny maja realnie powstac."""
    sciezka = tmp_path / "t.db"
    init_player_table(sciezka)
    init_player_table(sciezka)   # druga migracja: kolumny juz sa, ma przejsc

    with sqlite3.connect(str(sciezka)) as con:
        kolumny = {r[1] for r in con.execute("PRAGMA table_info(player_stats)")}

    assert {"rating", "xg"} <= kolumny, kolumny


def test_tabela_przezywa_probe_wstrzykniecia(tmp_path, monkeypatch):
    """Gdyby walidacja przepuscila ladunek, tabela zniknelaby — sprawdzamy skutek,
    nie samo podniesienie wyjatku."""
    from footstats.core import player_db

    sciezka = tmp_path / "t.db"
    init_player_table(sciezka)

    monkeypatch.setattr(player_db, "_OPTIONAL_COLS",
                        {"x REAL; DROP TABLE player_stats; --": "REAL"})
    with pytest.raises(ValueError):
        init_player_table(sciezka)

    with sqlite3.connect(str(sciezka)) as con:
        istnieje = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='player_stats'"
        ).fetchone()

    assert istnieje, "tabela player_stats zniknela — wstrzykniecie przeszlo"
