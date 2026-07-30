"""test_post_match_analyzer.py — petla feedbacku "Kij vs Ciastko".

PO CO: modul mial 0% pokrycia, a chodzi CODZIENNIE z `daily_agent.py:486`
i zasila prompt Groqa (`ai/analyzer.py:171` i `:652`). Czyli nieprzetestowany
kod decydowal, czego model uczy sie o wlasnych bledach.

Uwaga na dwa efekty uboczne, ktore trzeba tu zablokowac:
  * `analizuj_porazki` odpala `subprocess.Popen(visualize_brain.py)` — bez mocka
    test uruchamialby proces w tle,
  * `_zapisz_feedback` probuje auto-embedowac do RAG; brak modelu ma NIE psuc
    zapisu feedbacku (embedding jest nice-to-have).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

import footstats.ai.post_match_analyzer as pma

_SCHEMA = """
CREATE TABLE predictions (
    id            INTEGER PRIMARY KEY,
    created_at    TEXT NOT NULL,
    match_date    TEXT NOT NULL,
    team_home     TEXT NOT NULL,
    team_away     TEXT NOT NULL,
    league        TEXT DEFAULT '',
    ai_tip        TEXT DEFAULT '',
    ai_confidence INTEGER DEFAULT 0,
    ai_reasoning  TEXT DEFAULT '',
    actual_result TEXT,
    tip_correct   INTEGER,
    factors       TEXT DEFAULT '[]'
);
CREATE TABLE ai_feedback (
    id                 INTEGER PRIMARY KEY,
    match_id           INTEGER NOT NULL,
    prediction_details TEXT NOT NULL DEFAULT '{}',
    reason_for_failure TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class _SQLiteConn:
    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()):
        return self._raw.execute(sql, params)

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


def _dodaj_predykcje(db: str, **nadpisz) -> int:
    pola = {
        "created_at": datetime.now().isoformat(),
        "match_date": "2026-07-20T18:00:00",
        "team_home": "Legia", "team_away": "Lech", "league": "POL-Ekstraklasa",
        "ai_tip": "1", "ai_confidence": 72, "ai_reasoning": "forma domowa",
        "actual_result": "0:2", "tip_correct": 0, "factors": '["forma"]',
    }
    pola.update(nadpisz)
    conn = sqlite3.connect(db)
    kursor = conn.execute(
        f"INSERT INTO predictions ({','.join(pola)}) "
        f"VALUES ({','.join('?' * len(pola))})",
        tuple(pola.values()),
    )
    conn.commit()
    rowid = kursor.lastrowid
    conn.close()
    return rowid


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Baza SQLite podstawiona pod OBIE sciezki polaczen modulu."""
    sciezka = str(tmp_path / "pma.db")
    conn = sqlite3.connect(sciezka)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

    import footstats.core.backtest as bt
    import footstats.utils.db as dbmod
    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(dbmod, "connect", lambda *a, **k: _SQLiteConn(sciezka))
    # Visual Brain odpala sie na koncu analizy — nie chcemy procesu w tle.
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: None)

    # Atrapa embeddingu: prawdziwy EmbeddingStore ciagnie model z HuggingFace
    # (wolne + guard sieciowy). Awaria embeddingu ma wlasny, osobny test.
    class _AtrapaStore:
        def upsert(self, *a, **k) -> bool:
            return True

    monkeypatch.setattr("footstats.ai.rag_embeddings.EmbeddingStore",
                        lambda *a, **k: _AtrapaStore())
    return sciezka


@pytest.fixture
def groq(monkeypatch):
    """Podstawia zapytaj_ai; zwraca liste zadanych promptow."""
    prompty: list[str] = []

    def _fake(prompt: str, **kw) -> str:
        prompty.append(prompt)
        return "  Model przecenil forme domowa.  "

    import footstats.ai.client as client
    monkeypatch.setattr(client, "zapytaj_ai", _fake)
    return prompty


# ── _pobierz_porazki ────────────────────────────────────────────────────────

def test_bierze_tylko_porazki(db):
    _dodaj_predykcje(db, tip_correct=0, team_home="Przegrany")
    _dodaj_predykcje(db, tip_correct=1, team_home="Wygrany")
    _dodaj_predykcje(db, tip_correct=None, team_home="Nierozliczony")

    wynik = pma._pobierz_porazki(14)
    assert [r["team_home"] for r in wynik] == ["Przegrany"]


def test_pomija_juz_przeanalizowane(db):
    mid = _dodaj_predykcje(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO ai_feedback (match_id, reason_for_failure) VALUES (?, ?)",
                 (mid, "juz wiadomo"))
    conn.commit()
    conn.close()

    assert pma._pobierz_porazki(14) == []


def test_respektuje_okno_czasowe(db):
    stara = (datetime.now() - timedelta(days=40)).isoformat()
    _dodaj_predykcje(db, created_at=stara, team_home="Stara")
    _dodaj_predykcje(db, team_home="Swieza")

    assert [r["team_home"] for r in pma._pobierz_porazki(14)] == ["Swieza"]
    assert {r["team_home"] for r in pma._pobierz_porazki(60)} == {"Stara", "Swieza"}


# ── pobierz_ostatnie_wnioski ────────────────────────────────────────────────

def test_wnioski_formatowane_z_data_i_druzynami(db):
    mid = _dodaj_predykcje(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO ai_feedback (match_id, reason_for_failure) VALUES (?, ?)",
                 (mid, "przecenienie gospodarza"))
    conn.commit()
    conn.close()

    wnioski = pma.pobierz_ostatnie_wnioski(5)
    assert len(wnioski) == 1
    assert "2026-07-20" in wnioski[0]
    assert "Legia vs Lech" in wnioski[0]
    assert "przecenienie gospodarza" in wnioski[0]


def test_wnioski_respektuja_limit(db):
    # Predykcje najpierw, feedback potem — _dodaj_predykcje otwiera wlasne
    # polaczenie i commituje, wiec trzymanie drugiego otwartego blokuje baze.
    idki = [_dodaj_predykcje(db, team_home=f"Dom{i}") for i in range(5)]

    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO ai_feedback (match_id, reason_for_failure) VALUES (?, ?)",
        [(mid, f"powod {i}") for i, mid in enumerate(idki)],
    )
    conn.commit()
    conn.close()

    assert len(pma.pobierz_ostatnie_wnioski(2)) == 2


# ── analizuj_porazki ────────────────────────────────────────────────────────

def test_brak_porazek_nie_wola_ai(db, groq):
    stats = pma.analizuj_porazki(days_back=14)
    assert stats == {"analyzed": 0, "skipped": 0, "errors": 0}
    assert groq == [], "zapytano Groqa mimo braku porazek — to pali kredyty"


def test_dry_run_nie_zapisuje_i_nie_wola_ai(db, groq):
    _dodaj_predykcje(db)
    stats = pma.analizuj_porazki(days_back=14, dry_run=True)

    assert stats["analyzed"] == 1
    assert groq == [], "dry-run odpytal Groqa"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM ai_feedback").fetchone()[0] == 0
    conn.close()


def test_zapisuje_wniosek_i_przycina_biale_znaki(db, groq):
    mid = _dodaj_predykcje(db)
    stats = pma.analizuj_porazki(days_back=14)

    assert stats == {"analyzed": 1, "skipped": 0, "errors": 0}
    conn = sqlite3.connect(db)
    wiersz = conn.execute(
        "SELECT match_id, reason_for_failure, prediction_details FROM ai_feedback"
    ).fetchone()
    conn.close()
    assert wiersz[0] == mid
    assert wiersz[1] == "Model przecenil forme domowa."   # bez spacji z brzegow
    assert '"tip": "1"' in wiersz[2] and '"result": "0:2"' in wiersz[2]


def test_prompt_zawiera_dane_meczu(db, groq):
    _dodaj_predykcje(db)
    pma.analizuj_porazki(days_back=14)

    prompt = groq[0]
    for oczekiwane in ("Legia", "Lech", "POL-Ekstraklasa", "0:2", "72"):
        assert oczekiwane in prompt, f"prompt bez {oczekiwane!r}"


def test_blad_ai_liczony_jako_error_i_nie_przerywa_petli(db, monkeypatch):
    _dodaj_predykcje(db, team_home="Pierwszy")
    _dodaj_predykcje(db, team_home="Drugi")

    wolania = {"n": 0}

    def _kapryśne(prompt: str, **kw) -> str:
        wolania["n"] += 1
        if wolania["n"] == 1:
            raise ValueError("Groq padl")
        return "wniosek"

    import footstats.ai.client as client
    monkeypatch.setattr(client, "zapytaj_ai", _kapryśne)

    stats = pma.analizuj_porazki(days_back=14)
    assert stats["errors"] == 1
    assert stats["analyzed"] == 1, "petla przerwala sie po pierwszym bledzie"


def test_awaria_embeddingu_nie_psuje_zapisu(db, monkeypatch):
    """Embedding to nice-to-have — jego blad nie moze zgubic wniosku."""
    def _wybuch(*a, **k):
        raise OSError("brak modelu")

    monkeypatch.setattr("footstats.ai.rag_embeddings.EmbeddingStore", _wybuch)
    mid = _dodaj_predykcje(db)

    pma._zapisz_feedback(mid, {"tip": "1"}, "powod")

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM ai_feedback").fetchone()[0] == 1
    conn.close()
