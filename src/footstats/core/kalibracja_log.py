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
                -- Trafnosc rynkow GOLOWYCH, liczona z tego samego `actual_result`.
                -- `tip_correct` mierzy wylacznie argmax 1X2, a to wlasnie rynki
                -- golowe sa dzis glownym wyjsciem selekcji (18 z 20 kuponow z 15.08).
                -- Bez tych dwoch kolumn `prob_over25` i `prob_btts` byly zapisywane
                -- i nigdy z niczym nie porownywane.
                over25_correct INTEGER,
                btts_correct   INTEGER,
                zrodlo         TEXT,
                -- `zrodlo` to FAZA pipeline'u (final/evening), a to jest MODEL:
                -- 'poisson-dc' albo 'bzzoiro-ml'. Bez tego dziennik miesza oceny
                -- dwoch roznych modeli w jednej krzywej kalibracyjnej, a przez
                -- brak pyarrow w obrazach prod (do 2026-08-07) dokladnie to
                -- groziloby przy pierwszym cofnieciu sie do fallbacku.
                model_source   TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_model_log_mecz
                ON model_log (team_home, team_away, match_date);
            CREATE INDEX IF NOT EXISTS idx_model_log_pending
                ON model_log (tip_correct, match_date);
        """)
        # Tabela mogla powstac przed wprowadzeniem kolumny — CREATE IF NOT EXISTS
        # jej wtedy nie doda. Osobny, idempotentny ALTER (PostgreSQL 9.6+).
        conn.execute(
            "ALTER TABLE model_log ADD COLUMN IF NOT EXISTS model_source"
            " TEXT NOT NULL DEFAULT ''"
        )
        # Ten sam powod co wyzej, tylko swiezszy: tabela zyje na produkcji od
        # tygodni (595 wierszy 24.08), wiec `CREATE IF NOT EXISTS` jej nie ruszy
        # i bez tych ALTER-ow kolumny istnialyby wylacznie w testach.
        conn.execute("ALTER TABLE model_log ADD COLUMN IF NOT EXISTS over25_correct INTEGER")
        conn.execute("ALTER TABLE model_log ADD COLUMN IF NOT EXISTS btts_correct INTEGER")


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
                 lambda_h, lambda_a, model_tip, zrodlo, model_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
            """,
            (data, str(kandydat.get("liga") or ""), home, away,
             float(pw), float(pr), float(pp),
             kandydat.get("o25"), kandydat.get("bt"),
             kandydat.get("lambda_h"), kandydat.get("lambda_a"),
             tip, zrodlo, str(kandydat.get("model_source") or "")),
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

    # Tabela moze jeszcze nie istniec: `init` odpala sie w `zapisz_partie`, czyli
    # w dziennym jobie, a rozliczanie bywa pierwszym, ktory tu zaglada. Bez tego
    # endpoint /cron/kalibracja-rozlicz dostawal `relation "model_log" does not
    # exist` i konczyl HTTP 500 (2026-08-06).
    init_kalibracja_log()

    granica = (datetime.now() - timedelta(days=dni_wstecz)).strftime("%Y-%m-%d")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, team_home, team_away, match_date, model_tip FROM model_log"
            " WHERE tip_correct IS NULL AND match_date >= ?"
            " ORDER BY match_date",
            (granica,),
        ).fetchall()
    return [dict(r) for r in rows]


def oceny_rynkow(model_tip: str, wynik: str | None) -> dict[str, int] | None:
    """Trafność modelu na TRZECH rynkach naraz, policzona z jednego wyniku.

    `actual_result` trzyma pełny wynik (`"3-1"`), a nie sam znak 1/X/2 — więc
    Over/Under i BTTS da się z niego rozliczyć dokładnie tak samo jak argmax.
    Dziennik zapisywał `prob_over25` i `prob_btts` od początku i nigdy ich z
    niczym nie porównywał; to jest brakująca druga strona.

    Zwraca None, gdy wyniku nie ma albo nie da się z niego uczciwie rozliczyć
    (dogrywka/karne). Wtedy wiersz zostaje w kolejce zamiast dostać zera —
    „nie wiemy" to nie to samo co „model się pomylił", i dotyczy to wszystkich
    trzech rynków naraz, nie tylko 1X2.
    """
    if not wynik:
        return None
    trafny = oblicz_tip_correct(model_tip, wynik)
    if trafny is None:
        return None
    over25 = oblicz_tip_correct("Over 2.5", wynik)
    btts = oblicz_tip_correct("BTTS", wynik)
    if over25 is None or btts is None:
        # Nie powinno wystapic: skoro 1X2 dalo sie rozliczyc, wynik jest poprawny.
        # Jesli jednak — wiersz zostaje w kolejce, a my sie o tym dowiadujemy,
        # zamiast zapisac polowe prawdy i uznac mecz za zmierzony.
        log.warning("Wynik '%s' rozliczyl 1X2, ale nie rynki golowe"
                    " (over25=%s, btts=%s)", wynik, over25, btts)
        return None
    return {
        "tip_correct": trafny,
        "over25_correct": over25,
        "btts_correct": btts,
    }


def zapisz_wynik(wpis_id: int, wynik: str | None, model_tip: str) -> bool:
    """Dopisuje wynik i trafność na trzech rynkach. Zwraca True gdy zapisano.

    `model_tip` jest WYMAGANY — bez niego nie da się policzyć trafności, a cichy
    zapis samego wyniku zostawiłby wiersz, który wygląda na rozliczony i nigdy
    już nie wróci do kolejki.

    Wynik nierozliczalny NIE zapisuje trafności: „nie wiemy" to nie to samo co
    „model się pomylił", a zapis zera zafałszowałby kalibrację.
    """
    oceny = oceny_rynkow(model_tip, wynik)
    if oceny is None:
        return False

    with _connect() as conn:
        conn.execute(
            "UPDATE model_log SET actual_result = ?, tip_correct = ?,"
            " over25_correct = ?, btts_correct = ? WHERE id = ?",
            (wynik, oceny["tip_correct"], oceny["over25_correct"],
             oceny["btts_correct"], wpis_id),
        )
    return True


def uzupelnij_rynki_golowe(dry_run: bool = True) -> dict:
    """Liczy trafność rynków golowych dla wierszy, które JUŻ mają wynik.

    Zmierzone 24.08: 388 z 595 wierszy ma `actual_result`, wszystkie mają
    `prob_over25` i `prob_btts`. Ocena rynków golowych nie wymaga ani jednego
    nowego meczu — wystarczy policzyć to, co leży w tabeli od tygodni. To jest
    powód, dla którego `BTTS_TWO_WAY` może wyjść z „brakuje danych" od razu,
    a nie za miesiąc.

    Domyślnie `dry_run=True`: raportuje, ilu wierszy dotknie, i nie zapisuje nic.
    """
    init_kalibracja_log()

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, model_tip, actual_result FROM model_log"
            " WHERE actual_result IS NOT NULL"
            " AND (over25_correct IS NULL OR btts_correct IS NULL)"
        ).fetchall()

    stat = {"kandydaci": len(rows), "uzupelnione": 0, "pominiete": 0}

    for r in rows:
        oceny = oceny_rynkow(r["model_tip"] or "", r["actual_result"])
        if oceny is None:
            # Dogrywka/karne albo smieciowy zapis — zostawiamy nietkniete.
            stat["pominiete"] += 1
            continue
        stat["uzupelnione"] += 1
        if dry_run:
            continue
        with _connect() as conn:
            conn.execute(
                "UPDATE model_log SET over25_correct = ?, btts_correct = ?"
                " WHERE id = ?",
                (oceny["over25_correct"], oceny["btts_correct"], r["id"]),
            )

    log.info("uzupelnij_rynki_golowe(dry_run=%s): %s", dry_run, stat)
    return stat
