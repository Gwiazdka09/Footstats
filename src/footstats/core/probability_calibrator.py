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

# Runtime health-gate: krzywa o rozpiętości y < tego progu jest płaska/zdegenerowana
# (np. fit na 104 Neon-próbkach → span 0.049) i niszczy sygnał — traktuj jak identity
# nawet przy CALIBRATION_ENABLED=1. Zgodne z progiem diagnostyki w maybe_refit_calibration.
_MIN_CURVE_SPAN = 0.10

# Fallback lookup: predicted_band → calibrated_prob (from empirical data 2026-05-26)
_FALLBACK_TABLE: dict[int, float] = {
    50: 0.171,
    60: 0.410,
    70: 0.392,
    80: 0.333,
}

# 08-27: okno czasowe danych treningowych kalibracji. Pomiar obciążenia pewności Groqa
# per miesiąc (n=158, tip_correct rozliczone): 2026-05 (n=9) deklaruje 77,0% vs trafia
# 22,2% (−54,8pp, z=−4,16, ISTOTNE); 2026-06 (n=101, 64% całej tabeli) deklaruje 59,2%
# vs trafia 37,6% (−21,6pp, z=−4,82, ISTOTNE) — to era SPRZED fixów Cel B (patrz komentarz
# przy _CALIBRATION_ENABLED: "41 odwróconych próbek"). 2026-07 (n=14): −5,4pp = szum.
# 2026-08 (n=34): +2,8pp = szum. Fit na całej tabeli byłby zdominowany przez czerwiec
# (64% wierszy), mimo że jest zmierzony jako obciążony. Granica 2026-07-01 odcina znane
# skażenie danych — NIE usuwać/przesuwać bez nowego pomiaru per-miesiąc.
_POCZATEK_CZYSTYCH_DANYCH = "2026-07-01"

# Fragment WHERE dzielony fizycznie między _load_calibration_data i
# _count_settled_predictions — jedna stała, żeby okna czasowego nie dało się rozjechać
# (dodać w jednym miejscu, zapomnieć w drugim). Bez tego maybe_refit_calibration liczy
# deltę (settled − n_train) między dwoma różnymi zbiorami i nigdy jej nie domyka →
# refit odpalałby się co noc w nieskończoność.
_WHERE_ROZLICZONE_OD_OKNA = "tip_correct IS NOT NULL AND match_date >= ?"


def _load_calibration_data() -> tuple[list[float], list[float]]:
    """Load (predicted, actual) pairs from DB predictions table (od _POCZATEK_CZYSTYCH_DANYCH)."""
    with _db.connect() as conn:
        rows = conn.execute(
            "SELECT ai_confidence, tip_correct FROM predictions "
            f"WHERE {_WHERE_ROZLICZONE_OD_OKNA} AND ai_confidence > 0",  # nosec B608 — stała modułowa, nie input użytkownika
            (_POCZATEK_CZYSTYCH_DANYCH,),
        ).fetchall()
    predicted = [r["ai_confidence"] / 100.0 for r in rows]
    actual = [float(r["tip_correct"]) for r in rows]
    return predicted, actual


def fit_calibrator() -> None:
    """Fit isotonic regression on historical predictions (od _POCZATEK_CZYSTYCH_DANYCH),
    save to calibration.json.

    Isotonic regression potrzebuje wielokrotnie więcej próbek niż dolny próg 20 poniżej —
    poprzedni fit na 41 (szerszych, sprzed okna) próbkach wyszedł zdegenerowany, płaska
    krzywa (patrz komentarz przy _CALIBRATION_ENABLED). Po zawężeniu okna do lipca/sierpnia
    zostaje rząd ~48 wierszy: fit się wykona (próg to tylko 20), ale to wciąż za mało —
    CALIBRATION_ENABLED ma zostać WYŁĄCZONE, dopóki próbka nie urośnie.
    """
    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        _log.warning("sklearn not available — calibrator skipped")
        return

    predicted, actual = _load_calibration_data()
    if len(predicted) < 20:
        _log.warning(
            "Too few samples (%d) for calibration (okno od %s) — isotonic regression "
            "potrzebuje wielokrotnie więcej niż ten próg; zostaw CALIBRATION_ENABLED=0",
            len(predicted), _POCZATEK_CZYSTYCH_DANYCH,
        )
        return

    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(predicted, actual)

    # Serialize: sample 50 evenly spaced points for lookup
    import numpy as np
    x_pts = np.linspace(0.40, 0.95, 56).tolist()
    y_pts = ir.predict(x_pts).tolist()

    payload = {
        "x": x_pts,
        "y": y_pts,
        "n_train": len(predicted),
        "od_daty": _POCZATEK_CZYSTYCH_DANYCH,
    }
    _CALIBRATION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _log.info("Calibrator fitted on %d samples (od %s) → %s",
               len(predicted), _POCZATEK_CZYSTYCH_DANYCH, _CALIBRATION_PATH)


def _count_settled_predictions() -> int:
    """Liczba rozliczonych predykcji od _POCZATEK_CZYSTYCH_DANYCH (ten sam zbiór/okno
    co _load_calibration_data — patrz _WHERE_ROZLICZONE_OD_OKNA)."""
    with _db.connect() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM predictions WHERE {_WHERE_ROZLICZONE_OD_OKNA}",  # nosec B608 — stała modułowa, nie input użytkownika
            (_POCZATEK_CZYSTYCH_DANYCH,),
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
    # Health-gate: płaska krzywa (rozpiętość y < _MIN_CURVE_SPAN) → identity zamiast
    # spłaszczać każdą pewność do ~base-rate. Chroni przed footgunem zdegenerowanego
    # calibration.json, gdy ktoś ustawi CALIBRATION_ENABLED=1 przedwcześnie.
    curve = _load_calibration_curve()
    if curve is not None:
        ys = curve[1]
        if ys and (max(ys) - min(ys)) < _MIN_CURVE_SPAN:
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
        # Brak pola ≠ pewność zerowa. Domyślne `0` wstawiało
        # `pewnosc_kalibrowana = 0.0` KAŻDEMU kandydatowi z `quick_picks`
        # (nie mają ani `ai_confidence`, ani `pewnosc_pct` — niosą płaskie
        # pw/pr/pp/bt/o25), przez co filtr value bet liczył im EV = −100%
        # i odrzucał komplet przy każdym uruchomieniu.
        conf = k.get("ai_confidence")
        if conf is None:
            conf = k.get("pewnosc_pct")
        if conf is None:
            continue  # nie ma czego kalibrować — niech oceni je filtr per rynek
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
