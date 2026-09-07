"""Cienki sezon nie moze przeslaniac pelnego — `goal_share` z 1 gracza to smiec.

OBIETNICA, KTOREJ KOD NIE DOTRZYMYWAL. Docstring `core/absencje.py` opisuje
dokladnie ten mechanizm jako juz dzialajacy:

    "Premier League po dwoch kolejkach dala 5 goli na dwie kadry, wiec udzial
     jednego strzelca wyszedlby 0,4 i model policzylby jego absencje jako utrate
     40% ataku. `team_goal_shares_recent` siega po poprzedni pelny sezon
     i takiego skoku nie ma."

Siegalo po pierwszy NIEPUSTY, nie po pelny. Jeden gracz w tabeli wystarczyl,
zeby sezon zostal uznany za dobry — a `team_goal_shares` dzieli gole przez sume
gracz ZAPISANYCH, wiec przy jednym wpisie ten jeden dostaje 100% ataku druzyny.

STAN ZASTANY (pomiar `data/player_stats.json`, 2026-09-07 — STRZELCY na druzyne,
bo `team_goal_shares` odrzuca graczy bez goli i to oni tworza mianownik):

    sezon  druzyn  min  p25  mediana  p75  max
     2024     212    1    1        2   13   29    zrodlo mieszane
     2025      95    9   13       15   17   30    pelne sklady (Understat)
     2026      53    1    1        1    2    4    /players/topscorers

Tylko 2025 pochodzi z pelnych skladow. `/players/topscorers` API-Football oddaje
20 nazwisk na CALA lige, wiec na druzyne wypada 1-4. Luka 4 ↔ 9 jest pusta,
wiec `MIN_SKLAD` musi w niej siedziec.

Produkcja czyta `team_goal_shares_recent(team, 2026, lookback=2)`, wiec przed ta
poprawka kazda druzyna obecna w cienkim 2026 dostawala zmyslony udzial zamiast
kompletnego 2025.
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
        " goals INTEGER, assists INTEGER, minutes INTEGER, rating REAL, xg REAL,"
        " league TEXT, PRIMARY KEY (name, team_norm, season))"
    )
    con.executemany(
        "INSERT INTO player_stats (name, team_norm, season, goals) VALUES (?,?,?,?)",
        wiersze,
    )
    con.commit()
    con.close()
    return p


def _pelny_sklad(sezon, druzyna="arsenal", n=24):
    return [(f"gracz {i}", druzyna, sezon, 3) for i in range(n)]


def test_prog_lezy_w_zmierzonej_luce():
    """Pelny sklad ma >=9 strzelcow, resztka z topscorers <=4 — prog miedzy nimi.

    Gorna granica jest tu rownie wazna jak dolna: prog 12 gubil 12 prawdziwych
    sezonow-druzyn z 95, a prog 16 gubil 58 — za zero dodatkowej ochrony, bo
    smiec i tak konczy sie na 4.
    """
    assert 4 < pdb.MIN_SKLAD <= 9


def test_cienki_sezon_nie_przeslania_pelnego(tmp_path):
    baza = _baza(tmp_path, [("Mbappe", "real madrid", 2026, 4)]
                 + _pelny_sklad(2025, "real madrid"))

    udzialy = pdb.team_goal_shares_recent("Real Madrid", 2026, lookback=2, db_path=baza)

    assert "Mbappe" not in udzialy, "jeden gracz z 2026 przeslonil pelne 2025"
    assert len(udzialy) == 24
    assert max(udzialy.values()) == pytest.approx(1 / 24)


def test_jeden_gracz_dalby_sto_procent_ataku(tmp_path):
    """Dowod na rozmiar szkody: bez progu udzial wychodzi 1.0, nie 0.04."""
    baza = _baza(tmp_path, [("Mbappe", "real madrid", 2026, 4)])

    surowy = pdb.team_goal_shares("Real Madrid", 2026, db_path=baza)
    assert surowy["Mbappe"] == pytest.approx(1.0)

    # Ten sam odczyt przez sciezke produkcyjna nie ma prawa tego oddac.
    assert pdb.team_goal_shares_recent("Real Madrid", 2026, lookback=2, db_path=baza) == {}


def test_pelny_biezacy_sezon_wygrywa_z_poprzednim(tmp_path):
    """Prog odrzuca cienkie sezony, nie swieze — komplet z 2026 ma byc uzyty."""
    baza = _baza(tmp_path, _pelny_sklad(2026, "arsenal", n=23)
                 + _pelny_sklad(2025, "arsenal", n=24))

    udzialy = pdb.team_goal_shares_recent("Arsenal", 2026, lookback=2, db_path=baza)

    assert len(udzialy) == 23


def test_brak_pelnego_sezonu_w_oknie_to_pustka_nie_smiec(tmp_path):
    """Gdy w calym oknie sa same resztki — lepiej nic niz zmyslony udzial."""
    baza = _baza(tmp_path, [("a", "lecce", 2026, 2), ("b", "lecce", 2025, 5),
                            ("c", "lecce", 2024, 1)])

    assert pdb.team_goal_shares_recent("Lecce", 2026, lookback=2, db_path=baza) == {}


def test_zrzut_tez_podlega_progowi(tmp_path, monkeypatch):
    """Zrzut jest jedynym zrodlem w kontenerze — musi byc chroniony tak samo.

    Bez tego poprawka dzialalaby lokalnie (baza jest) i milczaco nie dzialala na
    produkcji (baza padla, zrzut wchodzi awaryjnie) — czyli dokladnie tam, gdzie
    korekta lambda naprawde sie liczy.
    """
    import json

    zrzut = tmp_path / "player_stats.json"
    zrzut.write_text(json.dumps(
        [{"name": "Mbappe", "team_norm": "real madrid", "season": 2026, "goals": 4}]
        + [{"name": f"gracz {i}", "team_norm": "real madrid", "season": 2025, "goals": 3}
           for i in range(24)]), encoding="utf-8")
    monkeypatch.setattr(pdb, "SCIEZKA_ZRZUTU", zrzut)
    pdb._zrzut_goli.cache_clear()

    # Baza nie istnieje → `sqlite3.Error` → sciezka zrzutu.
    brak_bazy = tmp_path / "nie_ma" / "gracze.db"
    udzialy = pdb.team_goal_shares_recent("Real Madrid", 2026, lookback=2, db_path=brak_bazy)
    pdb._zrzut_goli.cache_clear()

    assert "Mbappe" not in udzialy
    assert len(udzialy) == 24
