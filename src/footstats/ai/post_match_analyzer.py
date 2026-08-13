"""
post_match_analyzer.py – Analiza porażek AI (Pętla Feedbacku "Kij vs Ciastko")

Dla każdego rozliczonego meczu z tip_correct=0 (porażka), który nie ma jeszcze
wpisu w ai_feedback, odpytuje Groq o przyczynę błędu i zapisuje wniosek do DB.

Użycie:
    python -m footstats.ai.post_match_analyzer          # analiza ostatnich 14 dni
    python -m footstats.ai.post_match_analyzer --dni 30 # analiza ostatnich 30 dni
    python -m footstats.ai.post_match_analyzer --dry    # tylko pokaż co by przeanalizował
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_PROMPT_ANALIZA = """
Jesteś analitykiem piłkarskim oceniającym dlaczego AI postawiła zły typ.

Mecz: {home} vs {away} ({league}, {date})
Typ AI: {tip} (pewność: {confidence}%)
Uzasadnienie AI: {reasoning}
Wynik meczu: {actual_result}
Czynniki analizowane: {factors}

W 2–3 zdaniach odpowiedz PO POLSKU:
1. Jaki był GŁÓWNY powód błędu? (np. forma, kontuzje, xG, kurs, niedoszacowanie rywala)
2. Czego AI NIE uwzględniła lub przeceniła?
3. Krótka rekomendacja na przyszłość (1 zdanie).

Odpowiedz TYLKO tekstem bez nagłówków ani wypunktowania.
""".strip()

# Trafienie z błędnego powodu to nadal błędna decyzja. Ten prompt celowo NIE
# gratuluje — pyta, czy zadziałał proces, czy dopisało szczęście. Bez tego
# rozróżnienia lekcje z wygranych utrwalałyby przypadkowe trafy jako wzorzec.
_PROMPT_ANALIZA_TRAFIENIE = """
Jesteś analitykiem piłkarskim oceniającym, dlaczego typ AI okazał się trafny.

Mecz: {home} vs {away} ({league}, {date})
Typ AI: {tip} (pewność: {confidence}%)
Uzasadnienie AI: {reasoning}
Wynik meczu: {actual_result}
Czynniki analizowane: {factors}

W 2–3 zdaniach odpowiedz PO POLSKU:
1. Czy typ obronił się PROCESEM (przewaga widoczna w danych), czy dopisało SZCZĘŚCIE
   (np. wynik wbrew przebiegu gry, gol w doliczonym czasie, czerwona kartka)?
2. Który czynnik faktycznie zadziałał, a który okazał się bez znaczenia?
3. Krótka rekomendacja: co warto powtórzyć (1 zdanie).

Bądź surowy — jeśli to był szczęśliwy traf, napisz to wprost.
Odpowiedz TYLKO tekstem bez nagłówków ani wypunktowania.
""".strip()


def _pobierz_do_analizy(days_back: int, trafione: bool) -> list[dict]:
    """Rozliczone mecze bez wpisu w ai_feedback. `trafione` wybiera stronę.

    Zapytanie było zaszyte na `tip_correct = 0`, więc baza lekcji rosła wyłącznie
    z porażek — produkcja 13.08: 133 lekcje z 82 porażek, 49 trafień nietkniętych.
    RAG uczył się czego unikać, ale nigdy co powtarzać, i nie miał jak odróżnić
    dobrego procesu od szczęścia.
    """
    from footstats.core.backtest import _connect
    cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.match_date, p.team_home, p.team_away, p.league,
                   p.ai_tip, p.ai_confidence, p.ai_reasoning,
                   p.actual_result, p.factors, p.tip_correct
            FROM predictions p
            LEFT JOIN ai_feedback f ON f.match_id = p.id
            WHERE p.tip_correct = ?
              AND p.created_at >= ?
              AND f.id IS NULL
            ORDER BY p.match_date DESC
            """,
            (1 if trafione else 0, cutoff),
        ).fetchall()
    return [dict(r) for r in rows]


def _pobierz_porazki(days_back: int) -> list[dict]:
    """Zwraca mecze tip_correct=0 bez wpisu w ai_feedback (nie przeanalizowane)."""
    return _pobierz_do_analizy(days_back, trafione=False)


def _zapisz_feedback(match_id: int, prediction_details: dict, reason: str) -> None:
    """Zapisuje analizę do tabeli ai_feedback. Auto-embeds for RAG semantic search."""
    from footstats.utils.db import connect as _connect
    with _connect() as conn:
        row = conn.execute(
            "INSERT INTO ai_feedback (match_id, prediction_details, reason_for_failure)"
            " VALUES (?, ?, ?) RETURNING id",
            (match_id, json.dumps(prediction_details, ensure_ascii=False), reason),
        ).fetchone()
        feedback_id = row["id"]

    # Auto-embed for semantic RAG (non-blocking — failure doesn't break feedback write)
    #
    # RuntimeError JEST tu konieczny: sentence_transformers rzuca go przy ładowaniu
    # modelu (brak urządzenia, nieudane pobranie wag z HuggingFace). Bez niego
    # wyjątek przelatywał przez guard i wywalał CAŁY zapis feedbacku — dokładnie
    # to, przed czym ten blok miał chronić. Złapane testem 2026-07-30.
    #
    # Poziom WARNING, nie DEBUG: gdy embedding pada, RAG przestaje się uczyć
    # i nikt tego nie zauważa. Wpis jest jeden na rekord feedbacku, więc nie spamuje.
    try:
        from footstats.ai.rag_embeddings import EmbeddingStore
        store = EmbeddingStore()
        store.upsert(feedback_id, reason)
    except (ImportError, OSError, ValueError, TypeError, RuntimeError) as e:
        log.warning("[RAG] Auto-embed nieudany dla feedback_id=%s: %s — "
                    "wniosek zapisany, ale nie trafi do wyszukiwania semantycznego",
                    feedback_id, e)


def pobierz_ostatnie_wnioski(n: int = 3) -> list[str]:
    """
    Zwraca n ostatnich wniosków z ai_feedback — każdy ZE ZNACZNIKIEM wyniku.

    Znacznik jest obowiązkowy, odkąd baza lekcji zawiera też trafienia
    (13.08.2026). Bez niego wniosek „typ obronił się procesem" trafiał do
    promptu nieodróżnialny od porażki, a `analyzer.py` podpisywał cały blok
    nagłówkiem o błędach — więc model uczył się omijać to, co zadziałało.
    """
    from footstats.core.backtest import _connect
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT f.reason_for_failure, p.team_home, p.team_away,
                   p.match_date, p.tip_correct
            FROM ai_feedback f
            JOIN predictions p ON p.id = f.match_id
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
    return [
        f"[{r['match_date'][:10]}] {r['team_home']} vs {r['team_away']}"
        f" ({'TRAFIONY' if r['tip_correct'] else 'CHYBIONY'}):"
        f" {r['reason_for_failure']}"
        for r in rows
    ]


def analizuj_porazki(
    days_back: int = 14,
    dry_run: bool = False,
    analizuj_trafienia: bool = False,
) -> dict:
    """
    Główna funkcja. Analizuje nieprzetworzone rozliczenia i zapisuje wnioski.
    Zwraca {"analyzed": N, "skipped": M, "errors": K}.

    `analizuj_trafienia` domyślnie WYŁĄCZONE: włączenie pisze do produkcyjnego
    `ai_feedback` i pali tokeny Groqa, więc ma być świadomą decyzją, a nie
    efektem ubocznym aktualizacji.
    """
    from footstats.ai.client import zapytaj_ai

    porazki = _pobierz_porazki(days_back)
    trafienia = _pobierz_do_analizy(days_back, trafione=True) if analizuj_trafienia else []
    do_analizy = porazki + trafienia
    stats = {"analyzed": 0, "skipped": 0, "errors": 0}

    if not do_analizy:
        print("[PostMatchAnalyzer] Brak nowych rozliczeń do przeanalizowania.")
        return stats

    print(f"[PostMatchAnalyzer] Do analizy: {len(porazki)} porażek"
          f" + {len(trafienia)} trafień")

    for p in do_analizy:
        trafiony = bool(p.get("tip_correct"))
        etykieta_wyniku = "TRAFIONY" if trafiony else "chybiony"
        label = (f"{p['team_home']} vs {p['team_away']} "
                 f"({p['match_date'][:10]}, {etykieta_wyniku})")
        if dry_run:
            print(f"  [DRY] {label} — tip={p['ai_tip']} wynik={p['actual_result']}")
            stats["analyzed"] += 1
            continue

        szablon = _PROMPT_ANALIZA_TRAFIENIE if trafiony else _PROMPT_ANALIZA
        prompt = szablon.format(
            home=p["team_home"],
            away=p["team_away"],
            league=p.get("league", "?"),
            date=p["match_date"][:10],
            tip=p["ai_tip"],
            confidence=p["ai_confidence"],
            reasoning=p.get("ai_reasoning", "brak"),
            actual_result=p["actual_result"],
            factors=p.get("factors", "[]"),
        )

        try:
            reason = zapytaj_ai(prompt, max_tokens=300)
            reason = reason.strip()

            prediction_details = {
                "tip":        p["ai_tip"],
                "confidence": p["ai_confidence"],
                "odds":       None,
                "result":     p["actual_result"],
                # Bez tego RAG dostaje wymieszane lekcje z wygranych i przegranych
                # i nie ma jak ich odróżnić — wniosek „to zadziałało" czytałby
                # tak samo jak „tego unikaj".
                "tip_correct": 1 if trafiony else 0,
            }
            _zapisz_feedback(p["id"], prediction_details, reason)
            print(f"  [OK] {label} → {reason[:80]}…")
            stats["analyzed"] += 1
        except (ValueError, KeyError, TypeError, OSError) as e:
            log.error("Błąd analizy ID=%s: %s", p["id"], e)
            print(f"  [ERR] {label} → {e}")
            stats["errors"] += 1

    print(
        f"\n[PostMatchAnalyzer] Przeanalizowano: {stats['analyzed']} | "
        f"Pominięto: {stats['skipped']} | Błędy: {stats['errors']}"
    )

    # Automatyczna aktualizacja Visual Brain
    if stats['analyzed'] > 0 and not dry_run:
        try:
            print("[PostMatchAnalyzer] Aktualizacja Visual Brain...")
            import subprocess
            import sys
            # Znajdź ścieżkę do skryptu wizualizacji (niezależnie od cwd)
            script_path = Path(__file__).resolve().parents[3] / 'scripts' / 'visualize_brain.py'
            if script_path.exists():
                subprocess.Popen([sys.executable, str(script_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("  [OK] Visual Brain zaktualizowany w tle.")
        except OSError as e:
            print(f"  [ERR] Nie udało się zaktualizować Visual Brain: {e}")

    return stats


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.WARNING)

    from footstats.core.backtest import init_db
    init_db()

    parser = argparse.ArgumentParser(description="FootStats Post-Match Analyzer")
    parser.add_argument("--dry",  action="store_true", help="Tylko pokaż bez zapisu")
    parser.add_argument("--dni",  type=int, default=14, help="Dni wstecz (domyślnie 14)")
    parser.add_argument("--trafienia", action="store_true",
                        help="Analizuj TAKŻE trafione typy (proces vs szczęście). "
                             "Pisze do ai_feedback i zużywa tokeny Groqa.")
    args = parser.parse_args()

    analizuj_porazki(days_back=args.dni, dry_run=args.dry,
                     analizuj_trafienia=args.trafienia)
