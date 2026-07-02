"""Admin-only: Model vs Live — diagnostyka kalibracji/selekcji na danych PROD.

Persystentny widok tego, co liczone ad-hoc w sesji: reliability (pewność→realna
trafność), ROI kuponów, selekcja tip==argmax modelu vs override. Tylko admin.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from footstats.api.auth import require_admin
from footstats.utils.db import connect as _connect

router = APIRouter(prefix="/api", tags=["admin", "model-stats"])
log = logging.getLogger(__name__)

# Pasma pewności → oczekujemy że realna trafność rośnie monotonicznie z pewnością.
_BANDS: tuple[tuple[int, int, str], ...] = (
    (0, 55, "≤55"), (55, 63, "55-63"), (63, 68, "63-68"),
    (68, 73, "68-73"), (73, 80, "73-80"), (80, 101, "80+"),
)


def _argmax_1x2(ph, pd, pa) -> str | None:
    if ph is None or pd is None or pa is None:
        return None
    probs = {"1": ph, "X": pd, "2": pa}
    return max(probs, key=lambda k: probs[k])


@router.get("/admin/model-vs-live")
def model_vs_live(_admin: int = Depends(require_admin)):
    """Zwraca reliability, ROI kuponów i rozkład selekcji vs argmax modelu (PROD)."""
    try:
        with _connect() as conn:
            preds = conn.execute(
                "SELECT ai_tip, ai_confidence, tip_correct, prob_home, prob_draw, prob_away "
                "FROM predictions WHERE tip_correct IS NOT NULL AND ai_confidence > 0"
            ).fetchall()
            coup = conn.execute(
                "SELECT status, stake_pln, payout_pln FROM coupons "
                "WHERE status IN ('WON','WIN','LOST','LOSE')"
            ).fetchall()
    except (OSError, RuntimeError, ValueError) as e:
        log.warning("model-vs-live: odczyt DB nieudany: %s", e)
        raise HTTPException(status_code=503, detail="Dane niedostępne")

    # ── Reliability: pasmo pewności → realna trafność ──
    reliability = []
    for lo, hi, label in _BANDS:
        rows = [r for r in preds if lo <= (r["ai_confidence"] or 0) < hi]
        if not rows:
            continue
        n = len(rows)
        avg_conf = round(sum(r["ai_confidence"] for r in rows) / n, 1)
        acc = round(100 * sum(int(r["tip_correct"]) for r in rows) / n, 1)
        reliability.append({
            "band": label, "n": n, "avg_conf": avg_conf,
            "real_acc": acc, "gap": round(avg_conf - acc, 1),
        })

    n_settled = len(preds)
    live_acc = round(100 * sum(int(r["tip_correct"]) for r in preds) / n_settled, 1) if n_settled else None

    # ── Selekcja: tip == argmax modelu vs override (tylko 1X2 z prob) ──
    match_ok = match_n = mism_ok = mism_n = 0
    for r in preds:
        if r["ai_tip"] not in ("1", "X", "2"):
            continue
        arg = _argmax_1x2(r["prob_home"], r["prob_draw"], r["prob_away"])
        if arg is None:
            continue
        if r["ai_tip"] == arg:
            match_n += 1
            match_ok += int(r["tip_correct"])
        else:
            mism_n += 1
            mism_ok += int(r["tip_correct"])
    selection = {
        "argmax_n": match_n,
        "argmax_acc": round(100 * match_ok / match_n, 1) if match_n else None,
        "override_n": mism_n,
        "override_acc": round(100 * mism_ok / mism_n, 1) if mism_n else None,
    }

    # ── Kupony: ROI ──
    won = sum(1 for r in coup if r["status"] in ("WON", "WIN"))
    lost = sum(1 for r in coup if r["status"] in ("LOST", "LOSE"))
    stake = sum((r["stake_pln"] or 0) for r in coup)
    payout = sum((r["payout_pln"] or 0) for r in coup)
    coupons = {
        "settled": won + lost, "won": won, "lost": lost,
        "hit_rate": round(100 * won / (won + lost), 1) if (won + lost) else None,
        "stake_pln": round(stake, 2), "payout_pln": round(payout, 2),
        "profit_pln": round(payout - stake, 2),
        "roi_pct": round(100 * (payout - stake) / stake, 1) if stake else None,
    }

    return {
        "live_acc": live_acc,
        "n_settled": n_settled,
        "reliability": reliability,
        "selection": selection,
        "coupons": coupons,
    }
