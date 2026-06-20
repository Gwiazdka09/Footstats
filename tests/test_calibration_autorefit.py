"""D2 — auto-refit kalibracji co +30 settled predykcji (maybe_refit_calibration)."""
from unittest.mock import patch
import footstats.core.probability_calibrator as pc


def test_refit_gdy_delta_powyzej_progu():
    # 80 settled, ostatni fit n_train=41 → delta 39 ≥ 30 → refit.
    with patch.object(pc, "_count_settled_predictions", return_value=80), \
         patch.object(pc, "_last_fit_n_train", return_value=41), \
         patch.object(pc, "fit_calibrator") as fit, \
         patch.object(pc, "_load_calibration_curve", return_value=([0.4, 0.9], [0.3, 0.7])):
        assert pc.maybe_refit_calibration(threshold=30) is True
        fit.assert_called_once()


def test_brak_refit_gdy_delta_ponizej_progu():
    # 58 settled, n_train=41 → delta 17 < 30 → brak refitu.
    with patch.object(pc, "_count_settled_predictions", return_value=58), \
         patch.object(pc, "_last_fit_n_train", return_value=41), \
         patch.object(pc, "fit_calibrator") as fit:
        assert pc.maybe_refit_calibration(threshold=30) is False
        fit.assert_not_called()


def test_refit_gdy_brak_pliku_kalibracji():
    # n_train=0 (brak pliku) + 35 settled → refit.
    with patch.object(pc, "_count_settled_predictions", return_value=35), \
         patch.object(pc, "_last_fit_n_train", return_value=0), \
         patch.object(pc, "fit_calibrator") as fit, \
         patch.object(pc, "_load_calibration_curve", return_value=([0.4, 0.9], [0.3, 0.7])):
        assert pc.maybe_refit_calibration(threshold=30) is True
        fit.assert_called_once()


def test_graceful_przy_bledzie_db():
    # Błąd liczenia → False, bez wyjątku (nie blokuje evening).
    with patch.object(pc, "_count_settled_predictions", side_effect=RuntimeError("db down")), \
         patch.object(pc, "fit_calibrator") as fit:
        assert pc.maybe_refit_calibration() is False
        fit.assert_not_called()


def test_ostrzega_gdy_krzywa_plaska():
    # Po reficie krzywa płaska (rozpiętość <0.1) → refit się wykonał (True) ale z warningiem.
    with patch.object(pc, "_count_settled_predictions", return_value=100), \
         patch.object(pc, "_last_fit_n_train", return_value=41), \
         patch.object(pc, "fit_calibrator"), \
         patch.object(pc, "_load_calibration_curve", return_value=([0.4, 0.9], [0.286, 0.35])):
        assert pc.maybe_refit_calibration(threshold=30) is True
