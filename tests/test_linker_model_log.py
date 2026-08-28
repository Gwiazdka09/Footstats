"""Dziennik kuponów sięga po wynik meczu także do `model_log`.

PROBLEM: `link_leg` czyta WYŁĄCZNIE `predictions`, a to najwęższa z naszych
dwóch tabel — na produkcji 2026-08-28 `predictions` ma 161 wierszy, `model_log`
424. Kupon #149 z dziennika wisiał ACTIVE mimo że wynik jego meczu leżał
w bazie przez cały czas; trzeba go było domknąć ręcznie.

`model_log` zapisuje KAŻDY oceniony mecz (dziennik kalibracyjny), a `predictions`
tylko ścieżkę `top3`/`kupon_d`. To ta sama nasza baza i te same nasze dane —
więc to źródło DARMOWE, które musi być pytane PRZED zewnętrznymi API z D5.

Izolacja: własna plikowa SQLite, `match_linker.connect` podmieniony.
Zero sieci i zero prod (`.claude/rules/tests-no-prod.md`).
"""
from __future__ import annotations

import sqlite3

import pytest

import footstats.core.match_linker as match_linker

from tests.test_match_linker import _SQLiteConn

DATA = "2026-03-15"

_SCHEMA_MODEL_LOG = """
CREATE TABLE IF NOT EXISTS model_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date    TEXT NOT NULL,
    league        TEXT,
    team_home     TEXT NOT NULL,
    team_away     TEXT NOT NULL,
    model_tip     TEXT,
    actual_result TEXT
);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    sciezka = str(tmp_path / "test.db")
    setup = sqlite3.connect(sciezka)
    setup.executescript(_SCHEMA_MODEL_LOG)
    setup.commit()
    setup.close()
    monkeypatch.setattr(match_linker, "connect", lambda: _SQLiteConn(sciezka))
    return sciezka


def _wstaw(sciezka: str, home: str, away: str, wynik: str | None,
           data: str = DATA) -> None:
    conn = sqlite3.connect(sciezka)
    conn.execute(
        "INSERT INTO model_log (match_date, team_home, team_away, actual_result)"
        " VALUES (?, ?, ?, ?)",
        (data, home, away, wynik),
    )
    conn.commit()
    conn.close()


def test_znajduje_wynik_meczu_ktorego_nie_ma_w_predictions(db):
    """SEDNO. Mecz oceniony przez model, ale bez wiersza w `predictions` —
    dokładnie sytuacja kuponu #149."""
    _wstaw(db, "Arsenal", "Chelsea", "2-1")
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) == "2-1"


def test_brak_wyniku_to_brak_odpowiedzi_a_nie_pusty_string(db):
    """Mecz zapisany, ale jeszcze nierozegrany. `""` przepuszczone dalej
    udawałoby wynik i `oblicz_tip_correct` dostałby śmieć."""
    _wstaw(db, "Arsenal", "Chelsea", None)
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) is None
    _wstaw(db, "Roma", "Lazio", "")
    assert match_linker.wynik_z_model_log("Roma", "Lazio", DATA) is None


def test_brak_meczu_w_oknie_dat(db):
    _wstaw(db, "Arsenal", "Chelsea", "2-1", data="2026-04-01")
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) is None


def test_okno_dat_lapie_sasiedni_dzien(db):
    """Ta sama tolerancja +-1 dnia co `link_leg` — strefy czasowe przesuwają
    datę meczu między naszym zapisem a wpisem użytkownika."""
    _wstaw(db, "Arsenal", "Chelsea", "2-1", data="2026-03-16")
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) == "2-1"


def test_odwrocone_druzyny_to_brak_dopasowania(db):
    """Swap odwróciłby znaczenie tipu 1/2 — ta sama zasada co w `link_leg`."""
    _wstaw(db, "Chelsea", "Arsenal", "2-1")
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) is None


def test_dwa_rozne_mecze_w_oknie_to_odmowa_a_nie_zgadywanie(db):
    """Ambiguous → None. Rozliczenie z niewłaściwego meczu jest gorsze
    niż kupon czekający dzień dłużej."""
    _wstaw(db, "Arsenal", "Chelsea", "2-1", data="2026-03-14")
    _wstaw(db, "Arsenal", "Chelsea", "0-3", data="2026-03-16")
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) is None


def test_ten_sam_mecz_w_wielu_wierszach_jest_rozliczalny(db):
    """`model_log` zapisuje mecz raz na przebieg, więc duplikaty tego samego
    meczu (final + evening) są normą — nie mogą blokować rozliczenia."""
    _wstaw(db, "Arsenal", "Chelsea", "2-1")
    _wstaw(db, "Arsenal", "Chelsea", "2-1")
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) == "2-1"


def test_sprzeczne_wyniki_tego_samego_meczu_to_odmowa(db):
    """Dwa przebiegi zapisały RÓŻNY wynik — któryś jest zły i nie wiemy który."""
    _wstaw(db, "Arsenal", "Chelsea", "2-1")
    _wstaw(db, "Arsenal", "Chelsea", "1-1")
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) is None


def test_pusty_wynik_nie_blokuje_wypelnionego_z_tego_samego_meczu(db):
    """Przebieg `final` zapisuje mecz bez wyniku, `evening` go uzupełnia.
    Wiersz z pustym `actual_result` to brak danych, nie sprzeczność."""
    _wstaw(db, "Arsenal", "Chelsea", None)
    _wstaw(db, "Arsenal", "Chelsea", "2-1")
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) == "2-1"


def test_zle_dane_wejsciowe_nie_wywalaja(db):
    assert match_linker.wynik_z_model_log("", "Chelsea", DATA) is None
    assert match_linker.wynik_z_model_log("Arsenal", "", DATA) is None
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", None) is None
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", "nie-data") is None


def test_brak_tabeli_model_log_nie_wywala(tmp_path, monkeypatch):
    """Stare bazy i świeże SQLite nie mają tej tabeli. Kolektor jedzie
    w potoku produkcyjnym — brak tabeli musi dać None, nie wyjątek."""
    sciezka = str(tmp_path / "pusta.db")
    sqlite3.connect(sciezka).close()
    monkeypatch.setattr(match_linker, "connect", lambda: _SQLiteConn(sciezka))
    assert match_linker.wynik_z_model_log("Arsenal", "Chelsea", DATA) is None


def test_kolizja_normalizacji_nie_daje_false_positive(db):
    """Ta sama ochrona co w `link_leg`: STRICT `_norm_ascii`, zero mappingów
    z team_mappings.json (po nich „Manchester City" i „Manchester United"
    potrafią wylądować na tym samym skrócie)."""
    _wstaw(db, "Manchester United", "Liverpool", "2-1")
    assert match_linker.wynik_z_model_log("Manchester City", "Liverpool", DATA) is None
