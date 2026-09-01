"""Predykcja zapisuje się PRZED weryfikacją kursów — musi być oznaczona.

Kontekst (zmierzone na produkcji 14.08.2026): `predictions` to zapis PROPOZYCJI
Groqa, nie tego, co system faktycznie zagrał. Kolejność w `daily_agent` to
KROK 3 (analiza Groqa, w środku zapis do `predictions`) → KROK 4 (weryfikacja
kursów, anty-halucynacja). Weryfikacja podmienia kurs na rzeczywisty i wyrzuca
nogi bez pokrycia, ale robi to na słowniku w pamięci — do bazy nigdy nie wraca.

Skutki na prodzie: ten sam kurs 52.58 na trzech różnych meczach tego samego dnia,
Over 2.5 po 52.58 i Under 2.5 po 1.05. 48 ze 133 rozliczonych predykcji miało
kurs, którego filtr longshotów (1.2–4.0) by nie przepuścił. Tymi kursami karmią
się raporty ROI, pasma kursów i CLV.

Fix: kolumna `odds_verified` + uzgodnienie po KROKU 4 — noga, która przeżyła,
dostaje rzeczywisty kurs i znacznik; reszta zostaje z zerem i wypada z raportów.
"""
from __future__ import annotations

import sqlite3

import pytest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    match_date           TEXT NOT NULL DEFAULT '',
    team_home            TEXT NOT NULL DEFAULT '',
    team_away            TEXT NOT NULL DEFAULT '',
    league               TEXT NOT NULL DEFAULT '',
    ai_tip               TEXT NOT NULL DEFAULT '',
    ai_confidence        INTEGER NOT NULL DEFAULT 0,
    ai_reasoning         TEXT NOT NULL DEFAULT '',
    odds                 REAL,
    actual_result        TEXT,
    tip_correct          INTEGER,
    kupon_type           TEXT DEFAULT '',
    kodeks_rules_checked TEXT NOT NULL DEFAULT '[]',
    prompt_version       TEXT NOT NULL DEFAULT '',
    factors              TEXT NOT NULL DEFAULT '[]',
    match_stats          TEXT,
    coupon_id            INTEGER,
    prob_home            REAL,
    prob_draw            REAL,
    prob_away            REAL,
    model_source         TEXT NOT NULL DEFAULT '',
    settle_attempts      INTEGER DEFAULT 0,
    -- Migracja 13: czy kurs przeszedl KROK 4 (anty-halucynacja).
    odds_verified        INTEGER DEFAULT 0
);
"""


class _SQLiteConn:
    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()):
        return self._raw.execute(sql, params)

    def executemany(self, sql: str, seq):
        return self._raw.executemany(sql, seq)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    def __enter__(self) -> "_SQLiteConn":
        return self

    def __exit__(self, exc_type, *_) -> bool:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


@pytest.fixture(autouse=True)
def baza(tmp_path, monkeypatch):
    sciezka = str(tmp_path / "backtest.db")
    conn = sqlite3.connect(sciezka)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    yield sciezka


def _wiersze(sciezka):
    c = sqlite3.connect(sciezka)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute("SELECT * FROM predictions").fetchall()]
    finally:
        c.close()


def _zapisz(home="Legia", away="Wisła", tip="1", odds=52.58, data="2026-08-20"):
    from footstats.core.backtest import save_prediction
    _id, _ = save_prediction(match_date=data, team_home=home, team_away=away,
                             ai_tip=tip, ai_confidence=55, odds=odds)
    return _id


def _noga(home="Legia", away="Wisła", tip="1", odds=1.85, data="2026-08-20"):
    return {"team_home": home, "team_away": away, "match_date": data,
            "ai_tip": tip, "odds": odds}


# ── schemat ────────────────────────────────────────────────────────────────

def test_swiezy_zapis_jest_niezweryfikowany(baza):
    """Zapis z KROKU 3 to propozycja — domyślnie NIE zweryfikowana."""
    _zapisz()
    assert _wiersze(baza)[0]["odds_verified"] == 0


# ── uzgodnienie po weryfikacji ─────────────────────────────────────────────

def test_oznacz_zweryfikowane_podmienia_kurs_i_znacznik(baza):
    """Noga, która przeżyła KROK 4, dostaje RZECZYWISTY kurs z Bzzoiro."""
    from footstats.core.backtest import oznacz_zweryfikowane
    _zapisz(odds=52.58)                      # halucynacja Groqa
    assert oznacz_zweryfikowane([_noga(odds=1.85)]) == 1
    row = _wiersze(baza)[0]
    assert row["odds"] == pytest.approx(1.85)
    assert row["odds_verified"] == 1


def test_noga_odrzucona_zostaje_niezweryfikowana(baza):
    """Typ wyrzucony przez filtr longshotów NIE może udawać zagranego."""
    from footstats.core.backtest import oznacz_zweryfikowane
    _zapisz(home="Legia", away="Wisła", tip="1", odds=52.58)
    _zapisz(home="Lech", away="Pogoń", tip="2", odds=2.10)
    oznacz_zweryfikowane([_noga(home="Lech", away="Pogoń", tip="2", odds=2.05)])
    stan = {(r["team_home"], r["odds_verified"]) for r in _wiersze(baza)}
    assert ("Legia", 0) in stan
    assert ("Lech", 1) in stan


def test_pusta_lista_nic_nie_rusza(baza):
    """Dzień bez ocalałych nóg nie może oznaczać czegokolwiek."""
    from footstats.core.backtest import oznacz_zweryfikowane
    _zapisz()
    assert oznacz_zweryfikowane([]) == 0
    assert _wiersze(baza)[0]["odds_verified"] == 0


def test_niedopasowana_noga_nie_oznacza_nic(baza):
    """Rozjazd nazw = 0 dopasowań — wołający ma z tego zrobić WARNING."""
    from footstats.core.backtest import oznacz_zweryfikowane
    _zapisz(home="Legia Warszawa")
    assert oznacz_zweryfikowane([_noga(home="Legia")]) == 0
    assert _wiersze(baza)[0]["odds_verified"] == 0


def test_brak_kursu_w_nodze_nie_kasuje_istniejacego(baza):
    """Noga bez kursu nie może wyzerować tego, co już zapisane."""
    from footstats.core.backtest import oznacz_zweryfikowane
    _zapisz(odds=2.20)
    oznacz_zweryfikowane([_noga(odds=None)])
    row = _wiersze(baza)[0]
    assert row["odds"] == pytest.approx(2.20)
    assert row["odds_verified"] == 0


def test_kurs_nieparsowalny_jest_pomijany(baza):
    """Śmieć w kursie nie może trafić do bazy jako liczba."""
    from footstats.core.backtest import oznacz_zweryfikowane
    _zapisz(odds=2.20)
    assert oznacz_zweryfikowane([_noga(odds="—")]) == 0
    assert _wiersze(baza)[0]["odds"] == pytest.approx(2.20)


def test_wielokrotne_wywolanie_jest_idempotentne(baza):
    """Powtórka uzgodnienia (retry joba) nie psuje już poprawnych danych."""
    from footstats.core.backtest import oznacz_zweryfikowane
    _zapisz(odds=52.58)
    oznacz_zweryfikowane([_noga(odds=1.85)])
    oznacz_zweryfikowane([_noga(odds=1.85)])
    row = _wiersze(baza)[0]
    assert row["odds"] == pytest.approx(1.85)
    assert row["odds_verified"] == 1


def test_oznacza_tylko_wskazany_typ_na_tym_samym_meczu(baza):
    """Ten sam mecz bywa w kilku typach — weryfikacja dotyczy typu, nie meczu."""
    from footstats.core.backtest import oznacz_zweryfikowane
    _zapisz(tip="1", odds=52.58)
    _zapisz(tip="Over 2.5", odds=52.58)
    oznacz_zweryfikowane([_noga(tip="Over 2.5", odds=1.92)])
    stan = {r["ai_tip"]: (r["odds"], r["odds_verified"]) for r in _wiersze(baza)}
    assert stan["Over 2.5"] == (pytest.approx(1.92), 1)
    assert stan["1"] == (pytest.approx(52.58), 0)
