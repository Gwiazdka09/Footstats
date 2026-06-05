"""core/ensemble_optimizer.py — Per-league ensemble weight optimization (grid search, log-loss)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from footstats.utils import db as _db

_log = logging.getLogger(__name__)

_WEIGHTS_PATH = Path(__file__).parents[3] / "data" / "ensemble_weights.json"

# Default if no per-league data
_DEFAULT_WEIGHTS = {"poisson": 0.45, "bzzoiro": 0.55}
# Minimum settled predictions per league to trust the optimized weights
_MIN_SAMPLES = 15


def _log_loss_binary(y_true: list[float], y_pred: list[float], eps: float = 1e-9) -> float:
    """Binary log-loss."""
    total = 0.0
    for y, p in zip(y_true, y_pred):
        p = max(eps, min(1 - eps, p))
        total -= y * np.log(p) + (1 - y) * np.log(1 - p)
    return total / max(len(y_true), 1)


def _load_predictions_by_league(conn) -> dict[str, list[dict]]:
    """Load settled predictions grouped by league."""
    rows = conn.execute(
        """
        SELECT league, ai_confidence, tip_correct
        FROM predictions
        WHERE tip_correct IS NOT NULL
          AND ai_confidence > 0
          AND league != ''
        """
    ).fetchall()
    by_league: dict[str, list[dict]] = {}
    for r in rows:
        lg = r["league"]
        by_league.setdefault(lg, []).append({
            "conf": r["ai_confidence"] / 100.0,
            "correct": float(r["tip_correct"]),
        })
    return by_league


def _optimize_league(records: list[dict]) -> dict[str, float]:
    """
    Grid-search optimal weights [w_p, w_b] for one league.

    Since we don't store separate Poisson/Bzzoiro probs, we use:
    - p_poisson ≈ conf * 0.9   (Poisson tends to underestimate)
    - p_bzzoiro ≈ conf * 1.1   (Bzzoiro slightly overestimates)
    and find the weight that minimizes log-loss on ensemble confidence.

    This is a proxy optimization; replace p_poisson/p_bzzoiro with real stored
    values when available in the predictions table.
    """
    y_true = [r["correct"] for r in records]
    conf = np.array([r["conf"] for r in records])

    # Proxy: slightly perturb to simulate two models
    p_poisson = np.clip(conf * 0.90, 0.05, 0.95)
    p_bzzoiro = np.clip(conf * 1.10, 0.05, 0.95)

    best_loss = float("inf")
    best_wp = 0.45

    for wp in np.arange(0.0, 1.01, 0.05):
        wb = 1.0 - wp
        p_ens = wp * p_poisson + wb * p_bzzoiro
        loss = _log_loss_binary(y_true, p_ens.tolist())
        if loss < best_loss:
            best_loss = loss
            best_wp = float(wp)

    return {"poisson": round(best_wp, 2), "bzzoiro": round(1.0 - best_wp, 2)}


def optimize_all_leagues() -> dict[str, dict]:
    """
    Compute optimal weights per league. Returns mapping:
    {league_name: {"poisson": w1, "bzzoiro": w2}}
    """
    with _db.connect() as conn:
        by_league = _load_predictions_by_league(conn)

    results: dict[str, dict] = {"_default": _DEFAULT_WEIGHTS}
    for league, records in by_league.items():
        if len(records) < _MIN_SAMPLES:
            _log.debug("League %s: only %d samples, using default", league, len(records))
            continue
        weights = _optimize_league(records)
        results[league] = weights
        _log.info("League %s: w_poisson=%.2f, w_bzzoiro=%.2f (n=%d)",
                  league, weights["poisson"], weights["bzzoiro"], len(records))

    _WEIGHTS_PATH.parent.mkdir(exist_ok=True)
    _WEIGHTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    _log.info("Ensemble weights saved to %s", _WEIGHTS_PATH)
    return results


def load_weights(league: Optional[str] = None) -> dict[str, float]:
    """Load per-league weights from file, fall back to default."""
    if not _WEIGHTS_PATH.exists():
        return _DEFAULT_WEIGHTS
    try:
        data = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _DEFAULT_WEIGHTS
    if league and league in data:
        return data[league]
    return data.get("_default", _DEFAULT_WEIGHTS)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    weights = optimize_all_leagues()
    print(f"Optimized weights for {len(weights) - 1} leagues:")
    for lg, w in weights.items():
        if lg != "_default":
            print(f"  {lg}: Poisson={w['poisson']:.2f}, Bzzoiro={w['bzzoiro']:.2f}")
