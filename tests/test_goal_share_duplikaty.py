"""Ten sam zawodnik w dwoch pisowniach podwaja mianownik `goal_share`.

STAN ZASTANY (2026-09-07, po backfillu pelnych skladow). `player_stats` kluczuje
wiersz po `(name, team_norm, season)`, a zrodla pisza nazwiska inaczej:

    Liverpool 2025:  'Hugo Ekitike', 'H. Ekitike', 'Cody Gakpo', 'C. Gakpo', ...

To ten sam czlowiek dwa razy. `team_goal_shares` dzieli gole przez sume goli
graczy zapisanych, wiec duplikat wchodzi do mianownika DWUKROTNIE i zanizza
udzialy wszystkich — sanity po backfillu pokazywal Bayern z 38 nazwiskami przy
kadrze okolo 30.

Regula scalania jest CELOWO waska: laczymy tylko wtedy, gdy jedna pisownia jest
SKROTEM drugiej (pierwszy czlon to jedna litera). "Moussa Diallo" i "Mamadou
Diallo" zostaja osobno, bo zaden nie jest skrotem — to moga byc dwie rozne
osoby, a scalenie ich byloby cichym bledem w danych.
"""
from __future__ import annotations

import sqlite3

import pytest

from footstats.core import player_db as pdb


def _baza(tmp_path, wiersze):
    """`wiersze`: (nazwa, team_norm, sezon, gole)."""
    p = tmp_path / "gracze.db"
    con = sqlite3.connect(p)
    con.execute(
        "CREATE TABLE player_stats (name TEXT, team_norm TEXT, season INTEGER,"
        " goals INTEGER, PRIMARY KEY (name, team_norm, season))"
    )
    con.executemany(
        "INSERT INTO player_stats (name, team_norm, season, goals) VALUES (?,?,?,?)",
        wiersze)
    con.commit()
    con.close()
    return p


def test_skrot_scala_sie_z_pelnym_nazwiskiem(tmp_path):
    baza = _baza(tmp_path, [
        ("Hugo Ekitike", "liverpool", 2025, 10),
        ("H. Ekitike", "liverpool", 2025, 10),
        ("Mohamed Salah", "liverpool", 2025, 10),
    ])
    udzialy = pdb.team_goal_shares("Liverpool", 2025, db_path=baza)

    assert len(udzialy) == 2, f"duplikat nie scalony: {sorted(udzialy)}"
    assert udzialy["Hugo Ekitike"] == pytest.approx(0.5)
    assert udzialy["Mohamed Salah"] == pytest.approx(0.5)


def test_zostaje_PELNA_pisownia(tmp_path):
    """Pelne imie lepiej dopasowuje sie do FotMoba, ktory skrotow nie uzywa."""
    baza = _baza(tmp_path, [("C. Gakpo", "liverpool", 2025, 5),
                            ("Cody Gakpo", "liverpool", 2025, 5)])
    assert list(pdb.team_goal_shares("Liverpool", 2025, db_path=baza)) == ["Cody Gakpo"]


def test_rozne_liczby_goli_daja_WIEKSZA_nie_sume(tmp_path):
    """Zrodla moga pokrywac rozne rozgrywki. Suma podwoilaby dorobek gracza."""
    baza = _baza(tmp_path, [("Harry Kane", "bayern munich", 2025, 26),
                            ("H. Kane", "bayern munich", 2025, 20),
                            ("Michael Olise", "bayern munich", 2025, 26)])
    udzialy = pdb.team_goal_shares("Bayern Munich", 2025, db_path=baza)
    assert udzialy["Harry Kane"] == pytest.approx(0.5)


def test_dwoch_ROZNYCH_graczy_o_tym_samym_nazwisku_zostaje(tmp_path):
    """Zaden nie jest skrotem drugiego — scalenie byloby bledem w danych."""
    baza = _baza(tmp_path, [("Moussa Diallo", "psg", 2025, 4),
                            ("Mamadou Diallo", "psg", 2025, 6)])
    udzialy = pdb.team_goal_shares("PSG", 2025, db_path=baza)
    assert set(udzialy) == {"Moussa Diallo", "Mamadou Diallo"}


def test_dwa_skroty_bez_pelnego_zostaja_osobno(tmp_path):
    """'M. Diallo' i 'M. Diallo Jr' — nie ma pelnej pisowni, ktora rozstrzyga."""
    baza = _baza(tmp_path, [("M. Diallo", "psg", 2025, 4),
                            ("Mamadou Diallo", "psg", 2025, 6),
                            ("Moussa Diallo", "psg", 2025, 5)])
    udzialy = pdb.team_goal_shares("PSG", 2025, db_path=baza)
    # Skrot pasuje do DWOCH pelnych pisowni → nie scalamy niczego.
    assert len(udzialy) == 3


def test_gracz_bez_duplikatu_bez_zmian(tmp_path):
    baza = _baza(tmp_path, [("Mohamed Salah", "liverpool", 2025, 10),
                            ("Virgil van Dijk", "liverpool", 2025, 10)])
    udzialy = pdb.team_goal_shares("Liverpool", 2025, db_path=baza)
    assert set(udzialy) == {"Mohamed Salah", "Virgil van Dijk"}
    assert all(v == pytest.approx(0.5) for v in udzialy.values())


def test_jednoczlonowe_nazwisko_nie_scala_sie_z_niczym(tmp_path):
    # `team_norm` MUSI byc juz znormalizowane — "Manchester City" daje "man city".
    baza = _baza(tmp_path, [("Rodri", "arsenal", 2025, 5),
                            ("R. Silva", "arsenal", 2025, 5)])
    assert len(pdb.team_goal_shares("Arsenal", 2025, db_path=baza)) == 2


def test_scalanie_dziala_takze_na_zrzucie(tmp_path, monkeypatch):
    """Kontener czyta zrzut, nie baze — poprawka tylko w SQLite bylaby no-opem."""
    import json

    zrzut = tmp_path / "player_stats.json"
    zrzut.write_text(json.dumps(
        [{"name": "Hugo Ekitike", "team_norm": "liverpool", "season": 2025, "goals": 10},
         {"name": "H. Ekitike", "team_norm": "liverpool", "season": 2025, "goals": 10}]
        + [{"name": f"Gracz {i}", "team_norm": "liverpool", "season": 2025, "goals": 2}
           for i in range(pdb.MIN_SKLAD)]), encoding="utf-8")
    monkeypatch.setattr(pdb, "SCIEZKA_ZRZUTU", zrzut)
    pdb._zrzut_goli.cache_clear()

    udzialy = pdb.team_goal_shares("Liverpool", 2025, db_path=tmp_path / "brak" / "x.db")
    pdb._zrzut_goli.cache_clear()

    assert "H. Ekitike" not in udzialy
    assert "Hugo Ekitike" in udzialy
    assert len(udzialy) == pdb.MIN_SKLAD + 1
