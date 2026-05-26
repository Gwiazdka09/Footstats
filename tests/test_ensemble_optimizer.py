"""Testy core/ensemble_optimizer.py — grid search convergence."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from footstats.core.ensemble_optimizer import (
    _log_loss_binary,
    _optimize_league,
    load_weights,
)


# ── _log_loss_binary ──────────────────────────────────────────────────────

def test_log_loss_perfect_prediction():
    assert _log_loss_binary([1.0], [1.0]) == pytest.approx(0.0, abs=1e-6)


def test_log_loss_worst_prediction():
    assert _log_loss_binary([1.0], [0.0]) > 10.0


def test_log_loss_good_less_than_bad():
    loss_good = _log_loss_binary([1.0, 0.0], [0.7, 0.3])
    loss_bad  = _log_loss_binary([1.0, 0.0], [0.3, 0.7])
    assert loss_good < loss_bad


def test_log_loss_empty_returns_zero():
    assert _log_loss_binary([], []) == 0.0


def test_log_loss_clips_probs():
    # p=1.0 for y=0 → clipped, no crash
    result = _log_loss_binary([0.0], [1.0])
    assert result > 0


# ── _optimize_league ──────────────────────────────────────────────────────

def test_optimize_weights_sum_to_one():
    records = [{"conf": 0.6 + 0.01 * i, "correct": float(i % 2)} for i in range(10)]
    result = _optimize_league(records)
    assert result["poisson"] + result["bzzoiro"] == pytest.approx(1.0, abs=0.01)


def test_optimize_weights_in_range():
    records = [{"conf": 0.65, "correct": 1.0} for _ in range(20)]
    result = _optimize_league(records)
    assert 0.0 <= result["poisson"] <= 1.0
    assert 0.0 <= result["bzzoiro"] <= 1.0


def test_optimize_returns_dict_with_both_keys():
    records = [{"conf": 0.55, "correct": float(i % 2)} for i in range(5)]
    result = _optimize_league(records)
    assert "poisson" in result
    assert "bzzoiro" in result


def test_optimize_bzzoiro_preferred_when_underestimating():
    # conf=0.80 but correct=1 → bzzoiro's 1.1x multiplier closer to true prob
    records = [{"conf": 0.80, "correct": 1.0} for _ in range(20)]
    result = _optimize_league(records)
    assert result["bzzoiro"] >= result["poisson"]


# ── load_weights ─────────────────────────────────────────────────────────

def test_load_weights_no_file_returns_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        fake = Path(tmpdir) / "nope.json"
        with patch("footstats.core.ensemble_optimizer._WEIGHTS_PATH", fake):
            result = load_weights()
    assert "poisson" in result and "bzzoiro" in result


def test_load_weights_reads_league():
    weights = {
        "_default": {"poisson": 0.45, "bzzoiro": 0.55},
        "Bundesliga": {"poisson": 0.60, "bzzoiro": 0.40},
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "w.json"
        p.write_text(json.dumps(weights), encoding="utf-8")
        with patch("footstats.core.ensemble_optimizer._WEIGHTS_PATH", p):
            assert load_weights("Bundesliga") == {"poisson": 0.60, "bzzoiro": 0.40}
            assert load_weights() == {"poisson": 0.45, "bzzoiro": 0.55}


def test_load_weights_unknown_league_returns_default():
    weights = {"_default": {"poisson": 0.45, "bzzoiro": 0.55}}
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "w.json"
        p.write_text(json.dumps(weights), encoding="utf-8")
        with patch("footstats.core.ensemble_optimizer._WEIGHTS_PATH", p):
            assert load_weights("LaLiga") == {"poisson": 0.45, "bzzoiro": 0.55}


def test_load_weights_corrupt_file_returns_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "bad.json"
        p.write_text("NOT JSON", encoding="utf-8")
        with patch("footstats.core.ensemble_optimizer._WEIGHTS_PATH", p):
            result = load_weights()
    assert "poisson" in result
