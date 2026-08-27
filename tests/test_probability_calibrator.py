"""Testy core/probability_calibrator.py — kalibracja pewności AI.

06-20: kalibracja domyślnie WYŁĄCZONA (gate `_CALIBRATION_ENABLED`, calibration.json
zdegenerowany). Mechanizm krzywej/fallbacku testowany przez `_calibrate_raw`;
`calibrate_confidence` (produkcja) testowane osobno (identity gdy off, krzywa gdy on).
"""
import json
import logging

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


def test_gate_on_plaska_krzywa_zwraca_identity():
    # Health-gate: nawet z CALIBRATION_ENABLED=1, płaska/zdegenerowana krzywa
    # (rozpiętość y < próg) → identity, NIE niszcz sygnału (obrona przed footgunem
    # zdegenerowanego calibration.json, np. fit na 104 próbkach → span 0.049).
    from footstats.core.probability_calibrator import calibrate_confidence
    xs = [0.40, 0.65, 0.95]
    ys = [0.357, 0.38, 0.406]  # rozpiętość 0.049 < 0.10 → płaska
    with patch("footstats.core.probability_calibrator._CALIBRATION_ENABLED", True), \
         patch("footstats.core.probability_calibrator._load_calibration_curve", return_value=(xs, ys)):
        assert calibrate_confidence(72.0) == pytest.approx(0.72)  # identity, nie ~0.38
        assert calibrate_confidence(50.0) == pytest.approx(0.50)


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


# ── Okno czasowe danych treningowych (08-27) ─────────────────────────────
# Maj/czerwiec 2026 to era sprzed fixów Cel B, istotnie obciążona (patrz komentarz
# przy _POCZATEK_CZYSTYCH_DANYCH w module) — fit nie może jej brać pod uwagę.

class _FakeCursor:
    """Kursor zwracający zadaną listę wierszy (fetchall) lub pierwszy z nich (fetchone)."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConnPredictions:
    """Atrapa `predictions` filtrująca wiersze WEDŁUG treści zapytania/parametrów —
    nie kanonuje odpowiedzi, dzięki temu łapie rozjazd okna między dwoma zapytaniami
    (jeśli któreś zapomni dołożyć `match_date >= ?`, test to zobaczy jako różnicę liczb)."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def execute(self, sql: str, params: tuple = ()):
        wiersze = [r for r in self._rows if r.get("tip_correct") is not None]
        if "match_date >= ?" in sql:
            data_od = params[0]
            wiersze = [r for r in wiersze if r["match_date"] >= data_od]
        if "ai_confidence > 0" in sql:
            wiersze = [r for r in wiersze if (r.get("ai_confidence") or 0) > 0]
        if "COUNT(" in sql.upper():
            return _FakeCursor([{"n": len(wiersze)}])
        return _FakeCursor(wiersze)

    def __enter__(self) -> "_FakeConnPredictions":
        return self

    def __exit__(self, *_a) -> bool:
        return False


def test_load_calibration_data_pomija_wiersz_sprzed_okna(monkeypatch):
    import footstats.core.probability_calibrator as pc

    rows = [
        {"match_date": "2026-06-15", "ai_confidence": 70, "tip_correct": 1},  # przed oknem
        {"match_date": "2026-08-15", "ai_confidence": 60, "tip_correct": 0},  # w oknie
    ]
    monkeypatch.setattr("footstats.utils.db.connect", lambda: _FakeConnPredictions(rows))
    predicted, actual = pc._load_calibration_data()
    assert predicted == pytest.approx([0.6])
    assert actual == pytest.approx([0.0])


def test_count_settled_i_load_calibration_licza_ten_sam_zbior(monkeypatch):
    """Antyregresyjny: `_count_settled_predictions` i `_load_calibration_data` muszą
    liczyć ten sam zbiór wierszy (to samo okno czasowe) — inaczej `maybe_refit_calibration`
    porównuje dwa różne zbiory i delta (settled - n_train) nigdy się nie domyka,
    co odpala refit w kółko co noc."""
    import footstats.core.probability_calibrator as pc

    rows = [
        {"match_date": "2026-05-10", "ai_confidence": 80, "tip_correct": 1},  # przed oknem
        {"match_date": "2026-06-15", "ai_confidence": 70, "tip_correct": 0},  # przed oknem
        {"match_date": "2026-07-05", "ai_confidence": 65, "tip_correct": 1},  # w oknie
        {"match_date": "2026-08-15", "ai_confidence": 60, "tip_correct": 0},  # w oknie
        {"match_date": "2026-08-20", "ai_confidence": 55, "tip_correct": None},  # nierozliczone
    ]
    monkeypatch.setattr("footstats.utils.db.connect", lambda: _FakeConnPredictions(rows))
    predicted, _actual = pc._load_calibration_data()
    n_settled = pc._count_settled_predictions()
    assert n_settled == len(predicted)
    assert n_settled == 2


def test_count_settled_pomija_wiersze_bez_pewnosci_tak_jak_loader(monkeypatch):
    """Antyregresyjny, wariant uśpiony: wiersz rozliczony, w oknie, ale z pustą
    `ai_confidence` nie może być policzony przez licznik, skoro fit go odrzuca.

    Na produkcji 27.08 oba zapytania dawały 48 (żaden rozliczony wiersz nie miał pustej
    pewności), więc rozjazd był NIEWIDOCZNY — a wystarczy jeden taki wiersz, żeby
    `settled - n_train` przestało się domykać i refit ruszył w kółko co noc. Dlatego
    `ai_confidence > 0` siedzi we wspólnej stałej `_WHERE_ROZLICZONE_OD_OKNA`, a nie
    w samym loaderze."""
    import footstats.core.probability_calibrator as pc

    rows = [
        {"match_date": "2026-08-10", "ai_confidence": 65, "tip_correct": 1},
        {"match_date": "2026-08-11", "ai_confidence": None, "tip_correct": 0},  # bez pewnosci
        {"match_date": "2026-08-12", "ai_confidence": 0, "tip_correct": 1},     # pewnosc zerowa
    ]
    monkeypatch.setattr("footstats.utils.db.connect", lambda: _FakeConnPredictions(rows))
    predicted, _ = pc._load_calibration_data()
    assert pc._count_settled_predictions() == len(predicted) == 1


def test_fit_calibrator_zapisuje_od_daty(tmp_path, monkeypatch):
    import footstats.core.probability_calibrator as pc

    plik = tmp_path / "calibration.json"
    monkeypatch.setattr(pc, "_CALIBRATION_PATH", plik)
    predicted = [0.40 + 0.02 * i for i in range(25)]
    actual = [float(i % 2) for i in range(25)]
    monkeypatch.setattr(pc, "_load_calibration_data", lambda: (predicted, actual))

    pc.fit_calibrator()

    payload = json.loads(plik.read_text(encoding="utf-8"))
    assert payload["od_daty"] == pc._POCZATEK_CZYSTYCH_DANYCH


def test_last_fit_n_train_dziala_bez_klucza_od_daty(tmp_path, monkeypatch):
    """Kompatybilność wsteczna: stary plik calibration.json bez klucza `od_daty`
    (wygenerowany przed tą zmianą) nie może wywrócić `_last_fit_n_train`."""
    import footstats.core.probability_calibrator as pc

    plik = tmp_path / "calibration.json"
    plik.write_text(json.dumps({"x": [0.5], "y": [0.3], "n_train": 41}), encoding="utf-8")
    monkeypatch.setattr(pc, "_CALIBRATION_PATH", plik)

    assert pc._last_fit_n_train() == 41


def test_fit_calibrator_za_malo_wierszy_loguje_liczbe_i_date_okna(monkeypatch, caplog):
    import footstats.core.probability_calibrator as pc

    monkeypatch.setattr(pc, "_load_calibration_data", lambda: ([0.5] * 10, [1.0] * 10))
    with caplog.at_level(logging.WARNING, logger="footstats.core.probability_calibrator"):
        pc.fit_calibrator()

    assert "10" in caplog.text
    assert pc._POCZATEK_CZYSTYCH_DANYCH in caplog.text
