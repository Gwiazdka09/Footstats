"""Testy core/probability_calibrator.py — kalibracja pewności AI.

06-20: kalibracja domyślnie WYŁĄCZONA (gate `_CALIBRATION_ENABLED`, calibration.json
zdegenerowany). Mechanizm krzywej/fallbacku testowany przez `_calibrate_raw`;
`calibrate_confidence` (produkcja) testowane osobno (identity gdy off, krzywa gdy on).
"""
import pytest
from unittest.mock import patch


# ── _calibrate_raw — fallback table (mechanizm) ──────────────────────────
def test_calibrate_fallback_50():
    from footstats.core.probability_calibrator import _calibrate_raw
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        assert _calibrate_raw(50.0) == pytest.approx(0.171)


def test_calibrate_fallback_60():
    from footstats.core.probability_calibrator import _calibrate_raw
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        assert _calibrate_raw(60.0) == pytest.approx(0.410)


def test_calibrate_fallback_75_uses_70_band():
    from footstats.core.probability_calibrator import _calibrate_raw
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        assert _calibrate_raw(75.0) == pytest.approx(0.392)  # band 70


def test_calibrate_fallback_clamps_below_50():
    from footstats.core.probability_calibrator import _calibrate_raw
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        assert _calibrate_raw(30.0) == pytest.approx(0.171)  # clamped to band 50


def test_calibrate_fallback_clamps_above_80():
    from footstats.core.probability_calibrator import _calibrate_raw
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        assert _calibrate_raw(95.0) == pytest.approx(0.333)  # clamped to band 80


# ── _calibrate_raw — interpolation curve (mechanizm) ─────────────────────
def test_calibrate_with_curve_interpolation():
    from footstats.core.probability_calibrator import _calibrate_raw
    xs = [0.5, 0.7, 0.9]
    ys = [0.3, 0.5, 0.8]
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=(xs, ys)):
        assert _calibrate_raw(60.0) == pytest.approx(0.4)  # p=0.6 → midpoint 0.5–0.7


def test_calibrate_with_curve_clamp_below():
    from footstats.core.probability_calibrator import _calibrate_raw
    xs, ys = [0.6, 0.8], [0.4, 0.6]
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=(xs, ys)):
        assert _calibrate_raw(50.0) == pytest.approx(0.4)  # p=0.5 < xs[0] → ys[0]


def test_calibrate_with_curve_clamp_above():
    from footstats.core.probability_calibrator import _calibrate_raw
    xs, ys = [0.6, 0.8], [0.4, 0.6]
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=(xs, ys)):
        assert _calibrate_raw(90.0) == pytest.approx(0.6)  # p=0.9 > xs[-1] → ys[-1]


# ── calibrate_confidence — GATE (produkcja) ──────────────────────────────
def test_gate_off_zwraca_identity():
    # Domyślnie wyłączona → identity (confidence/100), NIE zdegenerowana krzywa.
    from footstats.core.probability_calibrator import calibrate_confidence
    with patch("footstats.core.probability_calibrator._CALIBRATION_ENABLED", False):
        assert calibrate_confidence(72.0) == pytest.approx(0.72)
        assert calibrate_confidence(18.0) == pytest.approx(0.18)


def test_gate_on_uzywa_krzywej():
    from footstats.core.probability_calibrator import calibrate_confidence
    xs, ys = [0.5, 0.7, 0.9], [0.3, 0.5, 0.8]
    with patch("footstats.core.probability_calibrator._CALIBRATION_ENABLED", True), \
         patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=(xs, ys)):
        assert calibrate_confidence(60.0) == pytest.approx(0.4)


# ── calibrate_candidates (przechodzi przez gate) ─────────────────────────
def test_calibrate_candidates_adds_field():
    from footstats.core.probability_calibrator import calibrate_candidates
    result = calibrate_candidates([{"ai_confidence": 70}])
    assert "pewnosc_kalibrowana" in result[0]


def test_calibrate_candidates_identity_gdy_off():
    from footstats.core.probability_calibrator import calibrate_candidates
    with patch("footstats.core.probability_calibrator._CALIBRATION_ENABLED", False):
        result = calibrate_candidates([{"ai_confidence": 70}])
    assert result[0]["pewnosc_kalibrowana"] == pytest.approx(0.70)  # identity, nie 0.392
