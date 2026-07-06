"""
test_calibration_metrics.py — metryki jakości predyktora (ścieżka A: kalibracja).
log-loss + Brier = north-star zamiast ROI. devig = implikowane prob rynku (bez marży).
"""
import math

from footstats.core.calibration_metrics import (
    log_loss, brier_multi, brier_binary, devig_two_way,
)


def test_log_loss_perfect_zero():
    assert log_loss(1.0) == 0.0


def test_log_loss_half():
    assert abs(log_loss(0.5) - math.log(2)) < 1e-9


def test_log_loss_zero_clamped_finite():
    v = log_loss(0.0)
    assert v > 20 and math.isfinite(v)      # clamp eps → duże ale skończone


def test_brier_multi_perfect_zero():
    assert brier_multi([1.0, 0.0, 0.0], 0) == 0.0


def test_brier_multi_uniform():
    # [1/3,1/3,1/3], actual=0 → (1/3-1)²+(1/3)²+(1/3)² = 4/9+1/9+1/9 = 6/9
    assert abs(brier_multi([1/3, 1/3, 1/3], 0) - 6/9) < 1e-9


def test_brier_binary():
    assert brier_binary(1.0, True) == 0.0
    assert abs(brier_binary(0.5, True) - 0.25) < 1e-9
    assert abs(brier_binary(0.5, False) - 0.25) < 1e-9


def test_devig_two_way_fair():
    po, pu = devig_two_way(2.0, 2.0)
    assert abs(po - 0.5) < 1e-9 and abs(pu - 0.5) < 1e-9


def test_devig_two_way_removes_margin():
    # kursy z marżą (1.8,1.8): inv 0.556 each → suma 1.111 → normalizacja 0.5/0.5
    po, pu = devig_two_way(1.8, 1.8)
    assert abs(po - 0.5) < 1e-9
    assert abs((po + pu) - 1.0) < 1e-9


def test_devig_two_way_favorite():
    po, pu = devig_two_way(1.5, 3.0)   # inv 0.667/0.333 → suma 1.0
    assert po > pu
    assert abs((po + pu) - 1.0) < 1e-9


def test_devig_two_way_invalid_none():
    assert devig_two_way(1.0, 2.0) is None
    assert devig_two_way(None, 2.0) is None
