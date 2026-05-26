"""core/probability_calibrator.py — Isotonic Regression calibration for AI confidence."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

_CALIBRATION_PATH = Path(__file__).parents[3] / "data" / "calibration.json"
_DB_PATH = Path(__file__).parents[3] / "data" / "footstats_backtest.db"

# Fallback lookup: predicted_band → calibrated_prob (from empirical data 2026-05-26)
_FALLBACK_TABLE: dict[int, float] = {
    50: 0.171,
    60: 0.410,
    70: 0.392,
    80: 0.333,
}


def _load_calibration_data() -> tuple[list[float], list[float]]:
    """Load (predicted, actual) pairs from DB predictions table."""
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ai_confidence, tip_correct FROM predictions "
            "WHERE tip_correct IS NOT NULL AND ai_confidence > 0"
        ).fetchall()
    predicted = [r["ai_confidence"] / 100.0 for r in rows]
    actual = [float(r["tip_correct"]) for r in rows]
    return predicted, actual


def fit_calibrator() -> None:
    """Fit isotonic regression on historical predictions, save to calibration.json."""
    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        _log.warning("sklearn not available — calibrator skipped")
        return

    predicted, actual = _load_calibration_data()
    if len(predicted) < 20:
        _log.warning("Too few samples (%d) for calibration", len(predicted))
        return

    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(predicted, actual)

    # Serialize: sample 50 evenly spaced points for lookup
    import numpy as np
    x_pts = np.linspace(0.40, 0.95, 56).tolist()
    y_pts = ir.predict(x_pts).tolist()

    payload = {"x": x_pts, "y": y_pts, "n_train": len(predicted)}
    _CALIBRATION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _log.info("Calibrator fitted on %d samples → %s", len(predicted), _CALIBRATION_PATH)


def _load_calibration_curve() -> Optional[tuple[list[float], list[float]]]:
    if not _CALIBRATION_PATH.exists():
        return None
    try:
        data = json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
        return data["x"], data["y"]
    except Exception:
        return None


def calibrate_confidence(confidence_pct: float) -> float:
    """
    Map raw AI confidence (0–100) to calibrated probability (0–1).
    Uses fitted isotonic regression curve or fallback lookup table.
    """
    p = confidence_pct / 100.0
    curve = _load_calibration_curve()
    if curve is not None:
        xs, ys = curve
        # Linear interpolation
        for i in range(len(xs) - 1):
            if xs[i] <= p <= xs[i + 1]:
                t = (p - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])
        # Extrapolation clamp
        if p <= xs[0]:
            return ys[0]
        return ys[-1]

    # Fallback: nearest band lookup
    band = (int(confidence_pct) // 10) * 10
    band = max(50, min(80, band))
    return _FALLBACK_TABLE.get(band, p)


def calibrate_candidates(kandydaci: list[dict]) -> list[dict]:
    """
    Add 'pewnosc_kalibrowana' field to each candidate.
    Does not mutate original ai_confidence so Groq reasoning is unchanged.
    """
    for k in kandydaci:
        conf = k.get("ai_confidence") or k.get("pewnosc_pct", 0)
        if isinstance(conf, float) and conf <= 1.0:
            conf = conf * 100  # already fractional
        k["pewnosc_kalibrowana"] = calibrate_confidence(float(conf))
    return kandydaci


if __name__ == "__main__":
    fit_calibrator()
    print("Calibration saved.")
    # Quick sanity check
    for pct in [55, 65, 75, 85]:
        cal = calibrate_confidence(pct)
        print(f"  {pct}% -> calibrated {cal:.1%}")
