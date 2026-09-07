"""Stan staly ma krzyczec RAZ, nie przy kazdym odczycie.

STAN ZASTANY (pomiar logow `footstats-api`, 2026-09-07, jedna godzina):

    69 x  no such table: player_stats
    42 x  no such table: team_stats

`data/footstats_backtest.db` jest wykluczony z obrazow (`.dockerignore`,
`.gcloudignore`), wiec w kontenerze tych tabel NIE MA i nigdy nie bedzie —
to warunek staly na caly czas zycia procesu, a nie zdarzenie. 111 ostrzezen
na godzine o czyms, co sie nie zmieni, to szum, ktory niszczy alarmy tak samo
skutecznie jak cisza. Ta sama lekcja co przy `player_db` 07.09 rano (105 wpisow
w jednym przebiegu jobu).

DRUGA RZECZ, DROBNIEJSZA I GORSZA: komunikat klamal. Mowil „i nie ma zrzutu",
podczas gdy zrzut JEST w obrazie i dziala — po prostu nie zna tej pary
druzyna/sezon (np. Ekstraklasa, albo sezon 2026, ktorego nie ma czym odswiezyc).
„Puste wyjscie" i „brak zrodla" to dwa rozne stany i mylenie ich juz raz w tym
projekcie doprowadzilo do falszywej diagnozy.

`team_stats` warto znac osobno: ma 48 wierszy, wszystkie `league='WC'`,
sezon 2026 — powstala na kadry mistrzostw swiata. Dla meczu klubowego jej brak
jest NORMALNY, wiec ostrzeganie o nim przy kazdej druzynie bylo podwojnie mylace.
"""
from __future__ import annotations

import logging
import sqlite3

import pytest

from footstats.core import player_db as pdb


@pytest.fixture(autouse=True)
def czysty_stan():
    pdb._zrzut_goli.cache_clear()
    pdb._ostrzezenia_o_bazie.clear()
    yield
    pdb._zrzut_goli.cache_clear()
    pdb._ostrzezenia_o_bazie.clear()


def _brak_bazy(tmp_path):
    return tmp_path / "nie_ma" / "gracze.db"


def test_martwa_baza_ostrzega_raz_na_proces(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(pdb, "SCIEZKA_ZRZUTU", tmp_path / "brak.json")
    caplog.set_level(logging.WARNING, logger=pdb.log.name)

    for i in range(20):
        pdb.team_goal_shares(f"Druzyna {i}", 2026, db_path=_brak_bazy(tmp_path))

    ostrzezenia = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(ostrzezenia) == 1, (
        f"{len(ostrzezenia)} ostrzezen na 20 odczytow tego samego stanu stalego")


def test_team_stats_tez_ostrzega_raz(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger=pdb.log.name)

    for i in range(20):
        pdb.get_team_stats(f"Druzyna {i}", 2026, db_path=_brak_bazy(tmp_path))

    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 1


def test_dwie_tabele_to_dwa_osobne_ostrzezenia(tmp_path, caplog, monkeypatch):
    """Cichniecie jednej nie moze wyciszyc drugiej — to rozne braki."""
    monkeypatch.setattr(pdb, "SCIEZKA_ZRZUTU", tmp_path / "brak.json")
    caplog.set_level(logging.WARNING, logger=pdb.log.name)

    pdb.team_goal_shares("Arsenal", 2026, db_path=_brak_bazy(tmp_path))
    pdb.get_team_stats("Arsenal", 2026, db_path=_brak_bazy(tmp_path))

    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 2


def test_komunikat_nie_klamie_gdy_zrzut_jest(tmp_path, caplog, monkeypatch):
    """Zrzut, ktory nie zna druzyny, to NIE to samo co brak zrzutu."""
    import json

    zrzut = tmp_path / "player_stats.json"
    zrzut.write_text(json.dumps(
        [{"name": f"g{i}", "team_norm": "arsenal", "season": 2025, "goals": 3}
         for i in range(pdb.MIN_SKLAD)]), encoding="utf-8")
    monkeypatch.setattr(pdb, "SCIEZKA_ZRZUTU", zrzut)
    caplog.set_level(logging.WARNING, logger=pdb.log.name)

    # Druzyna, ktorej zrzut NIE zna.
    pdb.team_goal_shares("Wisla Plock", 2026, db_path=_brak_bazy(tmp_path))

    tekst = " ".join(r.getMessage() for r in caplog.records)
    assert "nie ma zrzutu" not in tekst, (
        "komunikat twierdzi, ze zrzutu nie ma, a zrzut jest i dziala")
    assert "zrzut" in tekst.lower(), "komunikat nie mowi, ze zrzut byl sprawdzony"


def test_zrzut_dziala_mimo_wyciszenia(tmp_path, monkeypatch):
    """Wyciszenie dotyczy LOGU, nie zachowania — dane maja dalej plynac."""
    import json

    zrzut = tmp_path / "player_stats.json"
    zrzut.write_text(json.dumps(
        [{"name": f"g{i}", "team_norm": "arsenal", "season": 2025, "goals": 3}
         for i in range(pdb.MIN_SKLAD)]), encoding="utf-8")
    monkeypatch.setattr(pdb, "SCIEZKA_ZRZUTU", zrzut)

    for _ in range(5):
        udzialy = pdb.team_goal_shares("Arsenal", 2025, db_path=_brak_bazy(tmp_path))
        assert len(udzialy) == pdb.MIN_SKLAD


def test_zdrowa_baza_bez_druzyny_nadal_milczy(tmp_path):
    """Regresja z 07.09: pusty wynik ze ZDROWEJ bazy to nie awaria."""
    baza = tmp_path / "gracze.db"
    con = sqlite3.connect(baza)
    con.execute("CREATE TABLE player_stats (name TEXT, team_norm TEXT,"
                " season INTEGER, goals INTEGER)")
    con.commit()
    con.close()

    assert pdb.team_goal_shares("Arsenal", 2026, db_path=baza) == {}
