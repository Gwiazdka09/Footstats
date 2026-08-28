"""Jedyna definicja tabel bazowych.

DLACZEGO TO ISTNIEJE (zmierzone 28.08). Tabele bazowe powstawały w DWÓCH
miejscach naraz, na tej samej bazie:

    api/main._init_db()       8 tabel; `predictions` BEZ prob_home/prob_draw/
                              prob_away/settle_attempts/odds_verified
    core/backtest.init_db()   2 tabele; `predictions` Z tymi kolumnami, ale
                              z `REFERENCES coupons(id)` przy braku `coupons`

`utils.db.connect()` jest wyłącznie Postgresem, więc obie pisały do TEJ SAMEJ
bazy. Na pustej bazie wygrywała ta, która wykonała się pierwsza — a wykonuje się
różna w zależności od obrazu: `api/main` nie jest importowany w obrazie jobs,
gdzie `backtest.init_db()` woła dziewięć miejsc (evening_agent, ai/rag,
post_match_analyzer, results_updater ×2, coupon_settlement ×2 i sam backtest).

Nie wybuchło dotąd z dwóch powodów naraz: produkcyjna baza już istnieje, a na
Postgresie migracje mają `ADD COLUMN IF NOT EXISTS`. Oba są przypadkowe.

ZAKRES. Ten moduł trzyma schemat BAZOWY — to, co musi istnieć, zanim ruszą
migracje. Kolumny i tabele dokładane później (`users`, `odds_snapshots`,
`user_id`, `clv_closing_odds`, …) należą do `db/migrations.py` i tam zostają;
`_exec_statements` toleruje „kolumna już istnieje", więc nakładanie się obu
źródeł jest bezpieczne w obu dialektach.

Składnia jest POSTGRESOWA (`SERIAL`, `BYTEA`) — taka była w obu poprzednich
kopiach i taka jedzie na produkcję.
"""
from __future__ import annotations

SCHEMAT_BAZOWY = """
    CREATE TABLE IF NOT EXISTS coupons (
        id               SERIAL PRIMARY KEY,
        created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        phase            TEXT NOT NULL DEFAULT '',
        status           TEXT NOT NULL DEFAULT 'DRAFT',
        kupon_type       TEXT NOT NULL DEFAULT '',
        legs_json        TEXT NOT NULL DEFAULT '[]',
        total_odds       REAL,
        stake_pln        REAL,
        payout_pln       REAL,
        roi_pct          REAL,
        groq_reasoning   TEXT,
        decision_score   INTEGER,
        match_date_first TEXT,
        -- Dokladane tez migracjami 9 i user_id — sa TUTAJ z tego samego powodu
        -- co prob_* w `predictions`: swieza baza ma je miec od razu.
        -- `user_id` celowo BEZ klucza obcego: `users` powstaje dopiero migracja 1,
        -- czyli PO schemacie bazowym.
        bookmaker        TEXT,
        user_id          INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_coupon_status  ON coupons(status);
    CREATE INDEX IF NOT EXISTS idx_coupon_created ON coupons(created_at);
    CREATE INDEX IF NOT EXISTS idx_coupon_user    ON coupons(user_id);

    CREATE TABLE IF NOT EXISTS predictions (
        id                   SERIAL PRIMARY KEY,
        created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        match_date           TEXT NOT NULL,
        team_home            TEXT NOT NULL,
        team_away            TEXT NOT NULL,
        league               TEXT NOT NULL DEFAULT '',
        ai_tip               TEXT NOT NULL DEFAULT '',
        ai_confidence        INTEGER NOT NULL DEFAULT 0 CHECK(ai_confidence BETWEEN 0 AND 100),
        ai_reasoning         TEXT NOT NULL DEFAULT '',
        odds                 REAL,
        actual_result        TEXT,
        tip_correct          INTEGER CHECK(tip_correct IN (0, 1)),
        kupon_type           TEXT DEFAULT '',
        kodeks_rules_checked TEXT NOT NULL DEFAULT '[]',
        prompt_version       TEXT NOT NULL DEFAULT '',
        factors              TEXT NOT NULL DEFAULT '[]',
        match_stats          TEXT,
        coupon_id            INTEGER REFERENCES coupons(id),
        -- Ktory model policzyl te predykcje: 'poisson-dc' albo 'bzzoiro-ml'.
        -- Puste = nie wiadomo (predykcja sprzed wprowadzenia stempla).
        -- Migracja 10 uzupelnia stare wiersze.
        model_source         TEXT NOT NULL DEFAULT '',
        -- Ponizsze trzy dokladaly tez migracje 8/12/13 — sa TUTAJ, bo swieza baza
        -- ma je miec od razu, a nie dopiero po przejsciu migracji. Powtorzenie
        -- jest nieszkodliwe: `_exec_statements` toleruje "kolumna juz istnieje".
        prob_home            REAL,
        prob_draw            REAL,
        prob_away            REAL,
        -- Ile razy probowalismy juz sciagnac wynik. Po MAX_PROB_ROZLICZENIA
        -- nieudanych probach rekord wypada z nadrabiania zaleglosci.
        settle_attempts      INTEGER DEFAULT 0,
        -- Czy kurs przeszedl anty-halucynacyjna weryfikacje (KROK 4).
        -- Zapis dzieje sie w KROKU 3, wiec swiezy wiersz ma tu 0 i trzyma kurs
        -- zaproponowany przez Groqa — nie nadaje sie do ROI ani CLV.
        odds_verified        INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_match_date  ON predictions(match_date);
    CREATE INDEX IF NOT EXISTS idx_tip_correct ON predictions(tip_correct);
    CREATE INDEX IF NOT EXISTS idx_kupon_type  ON predictions(kupon_type);
    CREATE INDEX IF NOT EXISTS idx_league      ON predictions(league);

    CREATE TABLE IF NOT EXISTS ai_feedback (
        id                  SERIAL PRIMARY KEY,
        match_id            INTEGER NOT NULL REFERENCES predictions(id),
        prediction_details  TEXT NOT NULL DEFAULT '{}',
        reason_for_failure  TEXT NOT NULL DEFAULT '',
        created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_ai_feedback_match ON ai_feedback(match_id);
    CREATE INDEX IF NOT EXISTS idx_ai_feedback_date  ON ai_feedback(created_at);

    CREATE TABLE IF NOT EXISTS ai_feedback_embeddings (
        feedback_id INTEGER PRIMARY KEY REFERENCES ai_feedback(id) ON DELETE CASCADE,
        embedding   BYTEA NOT NULL,
        model_name  TEXT NOT NULL,
        dim         INTEGER NOT NULL,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS bankroll_state (
        id         INTEGER PRIMARY KEY CHECK (id = 1),
        balance    REAL NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS bankroll_history (
        id          SERIAL PRIMARY KEY,
        timestamp   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        change_pln  REAL NOT NULL,
        new_balance REAL NOT NULL,
        type        TEXT NOT NULL,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS bot_settings (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS wf_results (
        id         SERIAL PRIMARY KEY,
        run_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        league     TEXT NOT NULL,
        match_date TEXT NOT NULL,
        home       TEXT NOT NULL,
        away       TEXT NOT NULL,
        actual_hg  INTEGER,
        actual_ag  INTEGER,
        actual_res TEXT,
        pred_res   TEXT,
        pred_conf  REAL,
        pred_tip   TEXT,
        lambda_h   REAL,
        lambda_a   REAL,
        form_h     REAL,
        form_a     REAL,
        elo_diff   REAL,
        correct    INTEGER,
        market     TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_wf_league  ON wf_results(league);
    CREATE INDEX IF NOT EXISTS idx_wf_correct ON wf_results(correct)
"""


def utworz_schemat_bazowy(conn) -> None:
    """Zakłada tabele bazowe, jeśli ich nie ma. Bezpieczne przy wielokrotnym wywołaniu."""
    conn.executescript(SCHEMAT_BAZOWY)
