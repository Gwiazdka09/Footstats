"""
rag.py – Pattern-based RAG dla FootStats

Szuka w backtest DB historycznych predykcji z podobnymi czynnikami
i zwraca skuteczność jako kontekst dla Groq.

Eksportuje:
    pobierz_rag_kontekst(w: dict) -> str
        Dla wpisu z wyniki[] zwraca string "PATENT+TWIERDZA->1: 7/8(87%)"
        Zwraca "" gdy brak danych lub za mało próbek.
"""

import logging
import time as _time
from datetime import datetime, timedelta

from footstats.core.backtest import _connect, init_db

logger = logging.getLogger(__name__)

# ── Ekstrakcja czynników z pred dict ─────────────────────────────────────

_STRONG_STATUSES = {"HIGH_STAKES_TOP", "FINAL_TOP", "HIGH_STAKES_BOTTOM", "FINAL_RELEGATION"}
_STATUS_SHORT    = {
    "HIGH_STAKES_TOP":    "TOP",
    "FINAL_TOP":          "FINAL_TOP",
    "HIGH_STAKES_BOTTOM": "RELEGATION",
    "FINAL_RELEGATION":   "FINAL_REL",
}


def wyciagnij_faktory(pred: dict) -> list[str]:
    """
    Wyciąga listę czynników z bloku pred (z predict_match()).
    Przykład: ["PATENT", "TWIERDZA", "TOP"]
    """
    if not pred:
        return []

    h2h_g      = pred.get("h2h_g",      {}) or {}
    heur_g     = pred.get("heur_g",     {}) or {}
    heur_a     = pred.get("heur_a",     {}) or {}
    fortress_g = pred.get("fortress_g", {}) or {}
    imp_g      = pred.get("imp_g",      {}) or {}
    imp_a      = pred.get("imp_a",      {}) or {}

    faktory: list[str] = []

    if h2h_g.get("patent"):
        faktory.append("PATENT")
    if h2h_g.get("zemsta"):
        faktory.append("ZEMSTA")
    if fortress_g.get("fortress"):
        faktory.append("TWIERDZA")
    if heur_g.get("rotacja") or heur_a.get("rotacja"):
        faktory.append("ROTACJA")
    if heur_g.get("zmeczenie") or heur_a.get("zmeczenie"):
        faktory.append("ZMECZENIE")

    for imp in (imp_g, imp_a):
        s = imp.get("status", "NORMAL")
        if s in _STRONG_STATUSES:
            faktory.append(_STATUS_SHORT.get(s, s))

    return faktory


# ── Zapytanie do DB ───────────────────────────────────────────────────────

def pobierz_rag_wzorce(
    factors: list[str],
    ai_tip:  str | None = None,
    min_n:   int = 3,
    dni:     int = 180,
) -> str:
    """
    Dla podanej listy czynników i tipu zwraca historyczną skuteczność z backtestera.
    Zwraca "" gdy brak danych lub za mało próbek.

    Przykład zwrotu: "PATENT+TWIERDZA->1: 7/8(87%) | PATENT->1: 12/16(75%)"
    Maks 5 zapytań na wywołanie, wykonywanych jako jeden UNION ALL batch.
    """
    if not factors:
        return ""

    try:
        init_db()
        date_from = (datetime.now() - timedelta(days=dni)).strftime("%Y-%m-%d")

        # Zbierz specyfikacje zapytań (max 5)
        specs: list[tuple[str, list[str], str | None]] = []
        combo = factors[:3]
        if len(combo) >= 2 and ai_tip:
            specs.append(("+".join(combo), combo, ai_tip))
        seen: set[str] = set()
        for f in factors[:4]:
            if ai_tip:
                key = f"{f}->{ai_tip}"
                if key not in seen:
                    seen.add(key)
                    specs.append((f, [f], ai_tip))

        if not specs:
            return ""

        # Batch wszystkich zapytań jako UNION ALL
        parts: list[str] = []
        params: list = []
        for _label, factor_list, tip in specs:
            exists_parts = [
                "EXISTS (SELECT 1 FROM json_each(factors) WHERE value = ?)"
                for _ in factor_list
            ]
            tip_clause = "AND ai_tip = ?" if tip else ""
            parts.append(
                f"SELECT COUNT(*) AS n, COALESCE(SUM(tip_correct), 0) AS hits "  # nosec B608 — stałe klauzule + ? placeholdery, wartości w params
                f"FROM predictions "
                f"WHERE match_date >= ? AND tip_correct IS NOT NULL "
                f"AND {' AND '.join(exists_parts)} {tip_clause}"
            )
            params.extend([date_from] + factor_list + ([tip] if tip else []))

        t0 = _time.monotonic()
        with _connect() as conn:
            # Security: parts zawierają tylko parametryzowane ? placeholdery, brak user input w SQL
            rows = conn.execute(" UNION ALL ".join(parts), params).fetchall()
        elapsed = _time.monotonic() - t0
        logger.debug("[RAG] Batch %d queries in %.3fs", len(specs), elapsed)

        wyniki: list[str] = []
        for (label, _, tip), row in zip(specs, rows):
            n, hits = row["n"] or 0, int(row["hits"] or 0)
            if n >= min_n:
                acc = round(hits / n * 100)
                wyniki.append(f"{label}->{tip}: {hits}/{n}({acc}%)")

        return " | ".join(wyniki[:3])

    except Exception:  # noqa: broad-except — DB/query errors, return empty string as fallback
        return ""


# ── Główna funkcja (API dla analyzer.py) ─────────────────────────────────

def pobierz_rag_kontekst(w: dict) -> str:
    """
    Dla wpisu z wyniki[] (quick_picks / weekly_picks) zwraca string RAG.
    Działa tylko dla meczów POISSON (mają pełny pred dict).
    Zwraca "" gdy brak danych, za mało próbek lub inny błąd.
    """
    if w.get("metoda") != "POISSON":
        return ""

    pred = w.get("pred") or {}
    faktory = wyciagnij_faktory(pred)
    if not faktory:
        return ""

    # Dominant tip z prawdopodobieństw
    pw  = pred.get("p_wygrana",   0) or 0
    pr  = pred.get("p_remis",     0) or 0
    pp  = pred.get("p_przegrana", 0) or 0
    if pw >= pr and pw >= pp:
        tip = "1"
    elif pp >= pr:
        tip = "2"
    else:
        tip = "X"

    return pobierz_rag_wzorce(faktory, tip)


# ── Semantic RAG: Semantic search over ai_feedback lessons ─────────────────

def retrieve_relevant_lessons(query_context: str, k: int = 5, min_score: float = 0.35) -> list[dict]:
    """
    Semantic search over ai_feedback lessons using embeddings.
    Returns top-k lessons matching query_context by cosine similarity.

    Args:
        query_context: Description of current coupon/match context
        k: Number of results (default 5)
        min_score: Minimum cosine similarity threshold (default 0.35)

    Returns:
        List of dicts: [{reason_for_failure, match_id, score, created_at}, ...]
        Empty list if no matches or embeddings table empty.
    """
    try:
        from footstats.ai.rag_embeddings import EmbeddingStore
        from footstats.core.backtest import _connect
        import logging

        logger = logging.getLogger(__name__)

        if not query_context or not query_context.strip():
            return []

        # Embed query
        store = EmbeddingStore()
        query_vec = store.embed_text(query_context)

        # Semantic top-k search
        results = store.cosine_top_k(query_vec, k=k, min_score=min_score)
        if not results:
            return []

        # Fetch full records from ai_feedback
        feedback_ids = [fid for fid, score in results]
        lessons: list[dict] = []

        score_map = dict(results)
        placeholders = ",".join("?" * len(feedback_ids))
        with _connect() as conn:
            rows = conn.execute(
                f"SELECT id, match_id, reason_for_failure, created_at FROM ai_feedback WHERE id IN ({placeholders})",  # nosec B608 — placeholders='?,?' (param), wartości w feedback_ids
                feedback_ids,
            ).fetchall()
        for row in rows:
            lessons.append({
                "id": row["id"],
                "match_id": row["match_id"],
                "reason_for_failure": row["reason_for_failure"],
                "score": score_map.get(row["id"], 0.0),
                "created_at": row["created_at"],
            })

        logger.debug(f"[RAG] Retrieved {len(lessons)} lessons (top-{k}, min_score={min_score})")
        return lessons

    except (OSError, ValueError, TypeError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"[RAG] Semantic retrieval failed: {e}")
        return []
