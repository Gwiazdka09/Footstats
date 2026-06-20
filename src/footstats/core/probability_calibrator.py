"""core/probability_calibrator.py — Isotonic Regression calibration for AI confidence."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from footstats.utils import db as _db

_log = logging.getLogger(__name__)

_CALIBRATION_PATH = Path(__file__).parents[3] / "data" / "calibration.json"

# 06-20: kalibracja WYŁĄCZONA domyślnie. `calibration.json` był zdegenerowany — fit na 41
# odwróconych próbkach (sprzed fixów Cel B) → krzywa płaska 0.286-0.35, niszczyła sygnał
# (cc(<66%)=0.286 niezależnie od wejścia). Aktywne callery: Kelly (daily_agent) + value-bet
# (daily_filters). Identity aż do re-fit na czystych, post-Cel-B danych. Włącz: CALIBRATION_ENABLED=1.
_CALIBRATION_ENABLED = os.getenv("CALIBRATION_ENABLED", "0") == "1"

# Fallback lookup: predicted_band → calibrated_prob (from empirical data 2026-05-26)
_FALLBACK_TABLE: dict[int, float] = {
    50: 0.171,
    60: 0.410,
    70: 0.392,
    80: 0.333,
}


def _load_calibration_data() -> tuple[list[float], list[float]]:
    """Load (predicted, actual) pairs from DB predictions table."""
    with _db.connect() as conn:
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


def _count_settled_predictions() -> int:
    """Liczba rozliczonych predykcji (baza treningowa kalibracji)."""
    with _db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM predictions WHERE tip_correct IS NOT NULL"
        ).fetchone()
    return int(row["n"]) if row else 0


def _last_fit_n_train() -> int:
    """n_train z ostatniego fitu (0 gdy brak pliku kalibracji)."""
    if not _CALIBRATION_PATH.exists():
        return 0
    try:
        return int(json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8")).get("n_train", 0))
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def maybe_refit_calibration(threshold: int = 30) -> bool:
    """Auto-refit kalibracji co +threshold rozliczonych predykcji (D2, decyzja usera 06-20).

    Refit AKTUALIZUJE `calibration.json`, ale NIE włącza kalibracji w produkcji —
    gate `CALIBRATION_ENABLED` zostaje pod kontrolą usera (włączy `=1` gdy krzywa zdrowa:
    monotoniczna, dość próbek). Refit tylko utrzymuje krzywą świeżą na ten moment.
    Graceful: błąd DB/sklearn → log WARNING, return False (nie blokuje pipeline).
    """
    try:
        settled = _count_settled_predictions()
        n_train = _last_fit_n_train()
        if settled - n_train < threshold:
            _log.debug("Auto-refit kalibracji pominięty: %d settled, n_train=%d (brakuje %d do +%d)",
                       settled, n_train, threshold - (settled - n_train), threshold)
            return False
        _log.info("Auto-refit kalibracji: %d settled, było n_train=%d → refit (+%d)",
                  settled, n_train, settled - n_train)
        fit_calibrator()
        # Diagnostyka zdrowia krzywej: płaska (rozpiętość y < 0.1) = wciąż zdegenerowana.
        curve = _load_calibration_curve()
        if curve:
            ys = curve[1]
            rozpietosc = max(ys) - min(ys)
            if rozpietosc < 0.1:
                _log.warning("Krzywa kalibracji wciąż PŁASKA (rozpiętość y=%.3f) — nie włączaj "
                             "CALIBRATION_ENABLED, dane mogą być wciąż zaszumione/odwrócone", rozpietosc)
            else:
                _log.info("Krzywa kalibracji: rozpiętość y=%.3f (zdrowa jeśli monotoniczna)", rozpietosc)
        return True
    except (OSError, ValueError, RuntimeError, KeyError) as e:
        _log.warning("Auto-refit kalibracji nieudany (graceful): %s", e)
        return False


def _load_calibration_curve() -> Optional[tuple[list[float], list[float]]]:
    if not _CALIBRATION_PATH.exists():
        return None
    try:
        data = json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
        return data["x"], data["y"]
    except (OSError, ValueError, KeyError):
        return None


def calibrate_confidence(confidence_pct: float) -> float:
    """
    Map raw AI confidence (0–100) to calibrated probability (0–1).

    Gate: gdy kalibracja WYŁĄCZONA (domyślnie — patrz _CALIBRATION_ENABLED) zwraca
    identity (confidence/100), bo aktualny calibration.json niszczy sygnał. Po re-fit
    na czystych danych ustaw CALIBRATION_ENABLED=1.
    """
    if not _CALIBRATION_ENABLED:
        return confidence_pct / 100.0
    return _calibrate_raw(confidence_pct)


def _calibrate_raw(confidence_pct: float) -> float:
    """Surowa kalibracja: isotonic curve z dysku lub fallback table. Mechanizm
    (testowany bezpośrednio); produkcja przechodzi przez gate `calibrate_confidence`."""
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
