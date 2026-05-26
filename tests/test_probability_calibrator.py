"""Testy core/probability_calibrator.py — kalibracja pewności AI."""
import pytest
from unittest.mock import patch


# ── calibrate_confidence — fallback table ────────────────────────────────

def test_calibrate_fallback_50():
    from footstats.core.probability_calibrator import calibrate_confidence
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        result = calibrate_confidence(50.0)
    assert result == pytest.approx(0.171)


def test_calibrate_fallback_60():
    from footstats.core.probability_calibrator import calibrate_confidence
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        result = calibrate_confidence(60.0)
    assert result == pytest.approx(0.410)


def test_calibrate_fallback_75_uses_70_band():
    from footstats.core.probability_calibrator import calibrate_confidence
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        result = calibrate_confidence(75.0)
    assert result == pytest.approx(0.392)  # band 70


def test_calibrate_fallback_clamps_below_50():
    from footstats.core.probability_calibrator import calibrate_confidence
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        result = calibrate_confidence(30.0)
    assert result == pytest.approx(0.171)  # clamped to band 50


def test_calibrate_fallback_clamps_above_80():
    from footstats.core.probability_calibrator import calibrate_confidence
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        result = calibrate_confidence(95.0)
    assert result == pytest.approx(0.333)  # clamped to band 80


# ── calibrate_confidence — interpolation curve ───────────────────────────

def test_calibrate_with_curve_interpolation():
    from footstats.core.probability_calibrator import calibrate_confidence
    xs = [0.5, 0.7, 0.9]
    ys = [0.3, 0.5, 0.8]
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=(xs, ys)):
        result = calibrate_confidence(60.0)  # p=0.6 → midpoint 0.5–0.7 → 0.4
    assert result == pytest.approx(0.4)


def test_calibrate_with_curve_clamp_below():
    from footstats.core.probability_calibrator import calibrate_confidence
    xs = [0.6, 0.8]
    ys = [0.4, 0.6]
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=(xs, ys)):
        result = calibrate_confidence(50.0)  # p=0.5 < xs[0]=0.6 → ys[0]=0.4
    assert result == pytest.approx(0.4)


def test_calibrate_with_curve_clamp_above():
    from footstats.core.probability_calibrator import calibrate_confidence
    xs = [0.6, 0.8]
    ys = [0.4, 0.6]
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=(xs, ys)):
        result = calibrate_confidence(90.0)  # p=0.9 > xs[-1]=0.8 → ys[-1]=0.6
    assert result == pytest.approx(0.6)


# ── calibrate_candidates ─────────────────────────────────────────────────

def test_calibrate_candidates_adds_field():
    from footstats.core.probability_calibrator import calibrate_candidates
    kandydaci = [{"ai_confidence": 70}]
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        result = calibrate_candidates(kandydaci)
    assert "pewnosc_kalibrowana" in result[0]


def test_calibrate_candidates_fractional_input():
    from footstats.core.probability_calibrator import calibrate_candidates
    kandydaci = [{"ai_confidence": 0.70}]  # already fractional
    with patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=None):
        result = calibrate_candidates(kandydaci)
    # 0.70 → treated as 70% → band 70 → 0.392
    assert result[0]["pewnosc_kalibrowana"] == pytest.approx(0.392)
