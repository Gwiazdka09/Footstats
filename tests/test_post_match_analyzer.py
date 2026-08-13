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


# ── Nauka TAKZE z trafien ───────────────────────────────────────────────────
#
# PO CO: `_pobierz_porazki` bierze wylacznie `tip_correct = 0`, wiec baza lekcji
# jest z definicji jednostronna — produkcja 13.08: 133 lekcje z 82 porazek,
# 49 trafien nigdy nie przeanalizowanych. RAG uczy sie wylacznie tego, co poszlo
# zle, i nie potrafi odroznic dobrego procesu od szczescia. Analiza trafien
# domyka druga polowe petli.
#
# Domyslnie WYLACZONE: zapisuje do produkcyjnego `ai_feedback` i pali tokeny
# Groqa, wiec wlaczenie ma byc swiadoma decyzja, nie efekt uboczny aktualizacji.


def test_pobiera_trafienia_gdy_poproszone(db):
    _dodaj_predykcje(db, tip_correct=0, team_home="Przegrany")
    _dodaj_predykcje(db, tip_correct=1, team_home="Wygrany")
    _dodaj_predykcje(db, tip_correct=None, team_home="Nierozliczony")

    wynik = pma._pobierz_do_analizy(14, trafione=True)

    assert [r["team_home"] for r in wynik] == ["Wygrany"]


def test_pobiera_porazki_gdy_poproszone(db):
    _dodaj_predykcje(db, tip_correct=0, team_home="Przegrany")
    _dodaj_predykcje(db, tip_correct=1, team_home="Wygrany")

    wynik = pma._pobierz_do_analizy(14, trafione=False)

    assert [r["team_home"] for r in wynik] == ["Przegrany"]


def test_trafienia_tez_pomijaja_juz_przeanalizowane(db):
    mid = _dodaj_predykcje(db, tip_correct=1)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO ai_feedback (match_id, reason_for_failure) VALUES (?, ?)",
                 (mid, "juz wiadomo"))
    conn.commit()
    conn.close()

    assert pma._pobierz_do_analizy(14, trafione=True) == []


def test_domyslnie_trafienia_nie_sa_analizowane(db, groq):
    """Zmiana zachowania produkcji musi byc swiadoma — nie wlacza sie sama."""
    _dodaj_predykcje(db, tip_correct=1, team_home="Wygrany")

    stats = pma.analizuj_porazki(days_back=14)

    assert stats["analyzed"] == 0
    assert groq == [], "wolal AI o trafienie bez wyraznej zgody"


def test_flaga_wlacza_analize_trafien(db, groq):
    _dodaj_predykcje(db, tip_correct=1, team_home="Wygrany")

    stats = pma.analizuj_porazki(days_back=14, analizuj_trafienia=True)

    assert stats["analyzed"] == 1
    assert len(groq) == 1


def test_prompt_dla_trafienia_pyta_o_proces_nie_o_blad(db, groq):
    """Trafienie z zlego powodu to nadal zla decyzja — prompt musi to rozroznic."""
    _dodaj_predykcje(db, tip_correct=1, team_home="Wygrany")

    pma.analizuj_porazki(days_back=14, analizuj_trafienia=True)

    prompt = groq[0].lower()
    assert "zły typ" not in prompt, "trafienie dostalo prompt o bledzie"
    assert "szczęśc" in prompt or "proces" in prompt


def test_lekcja_z_trafienia_niesie_znacznik_wyniku(db, groq):
    """RAG musi umiec odroznic lekcje z wygranej od lekcji z porazki."""
    mid = _dodaj_predykcje(db, tip_correct=1, team_home="Wygrany")

    pma.analizuj_porazki(days_back=14, analizuj_trafienia=True)

    conn = sqlite3.connect(db)
    szczegoly = conn.execute(
        "SELECT prediction_details FROM ai_feedback WHERE match_id = ?", (mid,)
    ).fetchone()[0]
    conn.close()

    assert '"tip_correct": 1' in szczegoly.replace("'", '"')


def test_lekcja_z_porazki_tez_niesie_znacznik(db, groq):
    mid = _dodaj_predykcje(db, tip_correct=0)

    pma.analizuj_porazki(days_back=14)

    conn = sqlite3.connect(db)
    szczegoly = conn.execute(
        "SELECT prediction_details FROM ai_feedback WHERE match_id = ?", (mid,)
    ).fetchone()[0]
    conn.close()

    assert '"tip_correct": 0' in szczegoly.replace("'", '"')


def test_stara_nazwa_dalej_dziala(db):
    """`_pobierz_porazki` wolaja inne moduly — nie wolno jej urwac."""
    _dodaj_predykcje(db, tip_correct=0, team_home="Przegrany")
    _dodaj_predykcje(db, tip_correct=1, team_home="Wygrany")

    assert [r["team_home"] for r in pma._pobierz_porazki(14)] == ["Przegrany"]


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
