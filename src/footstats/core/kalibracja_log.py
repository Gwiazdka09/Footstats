"""kalibracja_log.py — dziennik KAŻDEJ oceny modelu, nie tylko obstawialnej.

PO CO ISTNIEJE: pipeline zapisuje do `predictions` wyłącznie to, co wyprodukował
Groq — czyli dopiero PO filtrze wartości. Log produkcyjny z 2026-08-05:

    kandydaci=46 → blacklista lig → 3 → filtr EV/Kelly → 0 → zero predykcji

To nie awaria, tylko konsekwencja architektury: predykcja zapisuje się dopiero
wtedy, gdy nadaje się do OBSTAWIENIA. Kalibracja potrzebuje czegoś innego —
wszystkich przewidywań modelu wraz z wynikami, niezależnie od opłacalności.
Bez tego model nigdy się nie dowie, czy jego prawdopodobieństwa są trafne, bo
widzi wyłącznie rzadkie przypadki, które przeszły filtr.

DLACZEGO OSOBNA TABELA, a nie kolejny `kupon_type` w `predictions`:
20 zapytań w 10 modułach liczy z `predictions` skuteczność selekcji i ŻADNE nie
filtruje po `kupon_type`. Dopisanie tam wierszy kalibracyjnych zafałszowałoby
każdą z tych metryk — w tym te, na których opierają się decyzje o progach.

Rozdzielone są więc dwie rzeczy, dotąd sklejone:
  * SELEKCJA DO OBSTAWIANIA — zostaje ostra (tylko dodatnie EV);
  * TEN DZIENNIK — zapisuje wszystko, zero wpływu na kupony.
"""
from __future__ import annotations

import logging

import psycopg2

from footstats.utils.betting import oblicz_tip_correct
from footstats.utils.db import connect as _connect

# Awarie, ktore dziennik ma PRZEZYC: baza (psycopg2 + RuntimeError z puli),
# dysk/siec (OSError) oraz smiec w kandydacie (ValueError/TypeError/KeyError).
_AWARIE_BAZY = (psycopg2.Error, RuntimeError, OSError)
_AWARIE_DANYCH = (ValueError, TypeError, KeyError)
# Zapis POJEDYNCZEJ oceny moze paść z obu powodow naraz: smiec w kandydacie
# albo padnieta baza w trakcie partii. Test `awaria_bazy_nie_zatrzymuje_pipeline`
# wylapal, ze sam `_AWARIE_DANYCH` przepuszcza RuntimeError z puli polaczen.
_AWARIE_ZAPISU = _AWARIE_DANYCH + _AWARIE_BAZY

log = logging.getLogger(__name__)


def init_kalibracja_log() -> None:
    """Tworzy tabelę jeśli nie istnieje. Bezpieczne przy wielokrotnym wywołaniu."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS model_log (
                id             SERIAL PRIMARY KEY,
                created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                match_date     TEXT NOT NULL,
                league         TEXT,
                team_home      TEXT NOT NULL,
                team_away      TEXT NOT NULL,
                prob_home      REAL,
                prob_draw      REAL,
                prob_away      REAL,
                prob_over25    REAL,
                prob_btts      REAL,
                lambda_h       REAL,
                lambda_a       REAL,
                model_tip      TEXT,
                actual_result  TEXT,
                tip_correct    INTEGER,
                zrodlo         TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_model_log_mecz
                ON model_log (team_home, team_away, match_date);
            CREATE INDEX IF NOT EXISTS idx_model_log_pending
                ON model_log (tip_correct, match_date);
        """)


def _argmax_1x2(pw: float, pr: float, pp: float) -> str:
    """Typ modelu = argmax JEGO WŁASNYCH prawdopodobieństw, nie wybór Groq.

    Dzięki temu dziennik mierzy model, a nie warstwę selekcji nad nim.
    """
    if pw >= pr and pw >= pp:
        return "1"
    return "X" if pr >= pp else "2"


def zapisz_ocene(kandydat: dict, zrodlo: str = "final") -> int | None:
    """Zapisuje jedną ocenę modelu. Zwraca id albo None gdy wiersz bezużyteczny.

    Odrzuca kandydatów bez prawdopodobieństw (nie ma czego kalibrować), bez nazw
    drużyn i bez daty (nie da się później dopasować wyniku).
    """
    home = str(kandydat.get("gospodarz") or "").strip()
    away = str(kandydat.get("goscie") or "").strip()
    data = str(kandydat.get("data") or "").strip()[:10]
    pw, pr, pp = kandydat.get("pw"), kandydat.get("pr"), kandydat.get("pp")

    if not home or not away or not data:
        return None
    if pw is None or pr is None or pp is None:
        return None

    tip = _argmax_1x2(float(pw), float(pr), float(pp))

    with _connect() as conn:
        istnieje = conn.execute(
            "SELECT id FROM model_log"
            " WHERE team_home = ? AND team_away = ? AND match_date = ? LIMIT 1",
            (home, away, data),
        ).fetchone()
        if istnieje:
            # Job final i evening oceniają ten sam mecz — bez dedupu kalibracja
            # liczyłaby go dwukrotnie i zawyżała pewność.
            return istnieje["id"]

        row = conn.execute(
            """
            INSERT INTO model_log
                (match_date, league, team_home, team_away,
                 prob_home, prob_draw, prob_away, prob_over25, prob_btts,
                 lambda_h, lambda_a, model_tip, zrodlo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
            """,
            (data, str(kandydat.get("liga") or ""), home, away,
             float(pw), float(pr), float(pp),
             kandydat.get("o25"), kandydat.get("bt"),
             kandydat.get("lambda_h"), kandydat.get("lambda_a"),
             tip, zrodlo),
        ).fetchone()
        return row["id"] if row else None


def zapisz_partie(kandydaci: list[dict], zrodlo: str = "final") -> int:
    """Zapisuje całą listę. Zwraca liczbę faktycznie zapisanych.

    Dziennik to OBSERWACJA, nie warunek działania — jego awaria nie może zabić
    generowania kuponów, więc wyjątek jest logowany i połykany.
    """
    if not kandydaci:
        return 0
    try:
        init_kalibracja_log()
    except _AWARIE_BAZY as e:
        log.warning("kalibracja_log: init nieudany: %s", e)
        return 0

    zapisane = 0
    for k in kandydaci:
        try:
            if zapisz_ocene(k, zrodlo) is not None:
                zapisane += 1
        except _AWARIE_ZAPISU as e:
            # Jeden zepsuty kandydat nie moze zablokowac zapisu pozostalych.
            log.warning("kalibracja_log: pomijam kandydata (%s): %s", k.get("gospodarz"), e)
    return zapisane


def pobierz_nierozliczone(dni_wstecz: int = 14) -> list[dict]:
    """Oceny bez wyniku z ostatnich `dni_wstecz` dni.

    Okno szersze niż w `update_pending` (2 dni), bo dziennik nie ściga się
    z rozliczaniem kuponów — może nadrabiać zaległości spokojnie.
    """
    from datetime import datetime, timedelta

    granica = (datetime.now() - timedelta(days=dni_wstecz)).strftime("%Y-%m-%d")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, team_home, team_away, match_date, model_tip FROM model_log"
            " WHERE tip_correct IS NULL AND match_date >= ?"
            " ORDER BY match_date",
            (granica,),
        ).fetchall()
    return [dict(r) for r in rows]


def zapisz_wynik(wpis_id: int, wynik: str | None, model_tip: str) -> bool:
    """Dopisuje wynik i trafność. Zwraca True gdy zapisano.

    `model_tip` jest WYMAGANY — bez niego nie da się policzyć trafności, a cichy
    zapis samego wyniku zostawiłby wiersz, który wygląda na rozliczony i nigdy
    już nie wróci do kolejki.

    Wynik nierozliczalny NIE zapisuje trafności: „nie wiemy" to nie to samo co
    „model się pomylił", a zapis zera zafałszowałby kalibrację.
    """
    if not wynik:
        return False
    trafny = oblicz_tip_correct(model_tip, wynik)
    if trafny is None:
        return False

    with _connect() as conn:
        conn.execute(
            "UPDATE model_log SET actual_result = ?, tip_correct = ? WHERE id = ?",
            (wynik, trafny, wpis_id),
        )
    return True
