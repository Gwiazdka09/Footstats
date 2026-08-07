"""Każda predykcja musi wiedzieć, KTÓRY model ją wyprodukował.

DLACZEGO: do 2026-08-07 `load_cached()` wywalało się w obrazach produkcyjnych
(brak pyarrow), więc `quick_picks` cicho schodził z Poissona-DC na Bzzoiro-ML.
Wszystkie predykcje w bazie pochodzą więc od Bzzoiro-ML, mimo że projekt cały
czas mierzył je jako „nasz model". `predictions` nie miało pola, po którym dało
się je rozróżnić, przez co jedynym sposobem na czysty pomiar wyglądało
skasowanie historii — a to zabrałoby jedyny punkt odniesienia, jaki istnieje
(117 predykcji z Neona jest za blokadą quoty).

Zamiast kasować: stemplujemy źródło. Stare wiersze = `bzzoiro-ml` (migracja 10),
nowe = to, co realnie policzyło. Porównanie Poisson-DC vs Bzzoiro-ML sprowadza
się wtedy do jednego WHERE.
"""
from __future__ import annotations

import contextlib
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from footstats.core.quick_picks import szybkie_pewniaczki_2dni

POISSON = "poisson-dc"
BZZOIRO = "bzzoiro-ml"


# ─────────────────────── quick_picks stempluje wynik ───────────────────────

_NOW = datetime.now()
_SOON = _NOW + timedelta(hours=6)

_EVENT = {
    "gosp": "Arsenal",
    "gosc": "Chelsea",
    "liga": "Premier League",
    "data": _SOON.strftime("%Y-%m-%d"),
    "godzina": _SOON.strftime("%H:%M"),
    "pred_ml": {
        "percent": {"home": "60%", "draw": "20%", "away": "20%"},
        "btts": "50%",
        "over_2_5": "55%",
    },
    "odds": {"home": 1.8, "draw": 3.5, "away": 4.0},
}

_POISSON_PRED = {
    "p_wygrana": 50.0, "p_remis": 30.0, "p_przegrana": 20.0,
    "btts": 40.0, "over25": 45.0, "under25": 55.0,
}

_DF = pd.DataFrame([{"gospodarz": "A", "goscie": "B", "gole_g": 1, "gole_a": 0,
                     "data": "2026-01-01"}])


def _nic():
    """Pusty context manager — gdy historia JEST, nic nie podmieniamy."""
    return contextlib.nullcontext()


def _zrodlo(events: list) -> MagicMock:
    klient = MagicMock()
    klient._valid = True
    klient.predykcje_tygodnia.return_value = events
    return klient


def _uruchom(df_mecze):
    """`df_mecze=None` = brak historii W OGÓLE, tak jak na produkcji.

    Samo przekazanie None nie wystarcza: quick_picks próbuje wtedy `load_cached()`,
    które na maszynie dewelopera zwraca realny parquet i Poisson i tak rusza.
    Podmieniamy je na ImportError — dokładnie to, co robił pandas bez pyarrow.
    """
    mock = MagicMock()
    mock.analiza.return_value = None
    mock_klas = MagicMock()
    mock_klas.klasyfikuj.return_value = None

    brak_historii = patch(
        "footstats.data.historical_loader.load_cached",
        side_effect=ImportError("Unable to find a usable engine"),
    )
    with brak_historii if df_mecze is None else _nic(), patch(
        "footstats.core.poisson.predict_match", return_value=_POISSON_PRED
    ), patch(
        "footstats.core.fortress.HomeFortress", return_value=mock
    ), patch(
        "footstats.core.h2h.AnalizaH2H", return_value=mock
    ), patch(
        "footstats.core.fatigue.HeurystaZmeczeniaRotacji", return_value=mock
    ), patch(
        "footstats.core.classifier.KlasyfikatorMeczu", return_value=mock_klas
    ):
        wyniki = szybkie_pewniaczki_2dni(_zrodlo([_EVENT]), prog=0.0, df_mecze=df_mecze)

    assert wyniki, "quick_picks nie zwrocil zadnego meczu"
    return wyniki[0]


def test_z_historia_wynik_oznaczony_jako_poisson() -> None:
    r = _uruchom(_DF)
    assert r["poisson_blend"] is True, "test bezwartosciowy — Poisson nie wystartowal"
    assert r["model_source"] == POISSON


def test_bez_historii_wynik_oznaczony_jako_bzzoiro() -> None:
    """Dokładnie sytuacja produkcyjna sprzed poprawki pyarrow."""
    r = _uruchom(None)
    assert r["poisson_blend"] is False
    assert r["model_source"] == BZZOIRO


def test_zrodlo_zawsze_obecne() -> None:
    """Brak pola jest gorszy niż zła wartość — cicho psuje każdy filtr."""
    for df in (_DF, None):
        assert _uruchom(df).get("model_source"), "wynik bez model_source"


# ─────────────────────── save_prediction utrwala źródło ────────────────────

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
    model_source         TEXT NOT NULL DEFAULT ''
)
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
        self.rollback() if exc_type else self.commit()
        self.close()
        return False


@pytest.fixture()
def baza(tmp_path, monkeypatch):
    sciezka = str(tmp_path / "pred.db")
    conn = sqlite3.connect(sciezka)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    return sciezka


def _zapisz(sciezka, **kw) -> str:
    from footstats.core.backtest import save_prediction

    domyslne = {
        "match_date": "2026-08-07", "team_home": "PSG", "team_away": "Lyon",
        "ai_tip": "1", "ai_confidence": 70,
    }
    save_prediction(**{**domyslne, **kw})
    conn = sqlite3.connect(sciezka)
    wartosc = conn.execute("SELECT model_source FROM predictions").fetchone()[0]
    conn.close()
    return wartosc


def test_save_prediction_zapisuje_zrodlo(baza) -> None:
    assert _zapisz(baza, model_source=POISSON) == POISSON


def test_save_prediction_bez_zrodla_zostawia_puste(baza) -> None:
    """Puste znaczy „nie wiadomo" — lepsze niż zmyślony `poisson-dc`."""
    assert _zapisz(baza) == ""


# ─────────────────────── migracja oznacza starą historię ───────────────────

def _migracja(dialekt: str, wersja: int) -> list[str]:
    from footstats.db.migrations import _get_migrations_for_dialect

    for nr, _opis, sql in _get_migrations_for_dialect(dialekt):
        if nr == wersja:
            return sql
    raise AssertionError(f"brak migracji {wersja} dla {dialekt}")


@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_migracja_dodaje_kolumne_model_source(dialekt: str) -> None:
    sql = " ".join(_migracja(dialekt, 10)).lower()
    assert "alter table predictions" in sql
    assert "model_source" in sql


@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_migracja_oznacza_istniejace_wiersze_jako_bzzoiro(dialekt: str) -> None:
    """Backfill musi być W migracji, nie osobnym skryptem do zapomnienia.

    W chwili jej uruchomienia KAŻDY istniejący wiersz pochodzi sprzed poprawki
    pyarrow, czyli od Bzzoiro-ML. Później jest już za późno — nowe predykcje
    wpadają wymieszane ze starymi i nie da się ich rozdzielić.
    """
    sql = " ".join(_migracja(dialekt, 10)).lower()
    assert "update predictions" in sql
    assert BZZOIRO in sql


@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_migracja_nie_nadpisuje_juz_oznaczonych(dialekt: str) -> None:
    """Re-run migracji nie może przestemplować predykcji Poissona na Bzzoiro."""
    update = next(s for s in _migracja(dialekt, 10) if "update predictions" in s.lower())
    assert "where" in update.lower(), "backfill bez WHERE nadpisze wszystko"


# ─────────────────────── dziennik kalibracyjny też stempluje ───────────────

def test_model_log_ma_kolumne_model_source() -> None:
    """Dziennik ma być czystym strumieniem pomiarowym.

    `zrodlo` mówi tylko o fazie pipeline'u (final/evening). Bez `model_source`
    jedno cofnięcie się do fallbacku Bzzoiro-ML zmieszałoby dwa modele w jednej
    krzywej kalibracyjnej i nikt by tego nie zauważył.
    """
    zrodlo = (
        __import__("pathlib").Path("src/footstats/core/kalibracja_log.py")
        .read_text(encoding="utf-8")
    )
    assert "model_source" in zrodlo.split("CREATE TABLE IF NOT EXISTS model_log")[1]


def test_zapisz_ocene_przekazuje_model_source(monkeypatch) -> None:
    from footstats.core import kalibracja_log as kl

    zapisane: dict = {}

    class _Conn:
        def execute(self, sql, params=()):
            wstawia = "INSERT INTO model_log" in sql
            if wstawia:
                zapisane["sql"] = sql
                zapisane["params"] = params

            class _R:
                @staticmethod
                def fetchone():
                    # SELECT to dedup — musi zwrócić None, inaczej `zapisz_ocene`
                    # uzna mecz za już zapisany i w ogóle nie dojdzie do INSERT-a.
                    return {"id": 1} if wstawia else None
            return _R()

        def executescript(self, _s): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr(kl, "_connect", lambda: _Conn())
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)

    kl.zapisz_ocene({
        "data": "2026-08-07", "gospodarz": "PSG", "goscie": "Lyon",
        "pw": 50.0, "pr": 30.0, "pp": 20.0, "model_source": POISSON,
    })
    assert "model_source" in zapisane["sql"]
    assert POISSON in zapisane["params"]


def test_numeracja_migracji_bez_dziur_i_zgodna_miedzy_dialektami() -> None:
    from footstats.db.migrations import _get_migrations_for_dialect

    wersje = {
        d: [nr for nr, _, _ in _get_migrations_for_dialect(d)]
        for d in ("sqlite", "postgresql")
    }
    assert wersje["sqlite"] == wersje["postgresql"], "dialekty rozjechaly sie numeracja"
    assert wersje["sqlite"] == list(range(1, len(wersje["sqlite"]) + 1))
