"""Kalibracja musi mierzyć TĘ λ, którą naprawdę liczy produkcja.

PO CO: `run_calibration` liczyło bias przez własny, prywatny estymator
`_lambda_from_hist`, a wyliczone factory stosowane są potem w `predict_match`,
czyli do λ z zupełnie innego wzoru. Kalibracja korygowała więc obciążenie
funkcji, która w produkcji nic nie liczy.

Zmierzone 09.08.2026 na 477 meczach 6 lig (walk-forward, bez kalibracji):
    λ z `predict_match`: bias 1.0453 (gospodarze) / 0.9722 (goście)
    factory z pliku:     0.9715 / 0.9545
    po ich zastosowaniu: 1.0759 / 1.0185   ← GORZEJ niż bez nich

Czyli korekta pogarszała wynik, bo dopasowana była do cudzego błędu. To także
wyjaśnia, dlaczego rekalibracja na 19 727 meczach zamiast 1996 nie zmieniła
nic w krzywej niezawodności — mierzyła nie tę funkcję.
"""
from __future__ import annotations

import pandas as pd

from footstats.core import lambda_optimizer as lo


def _historia(n: int = 40) -> pd.DataFrame:
    mecze = []
    for i in range(n):
        mecze += [
            ("Potega", "Kopciuszek", 3, 0), ("Kopciuszek", "Potega", 0, 2),
            ("Potega", "Srednik", 2, 1), ("Srednik", "Kopciuszek", 2, 0),
        ]
    return pd.DataFrame([
        {"date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
         "league": "TEST-Liga", "home": g, "away": a, "hg": hg, "ag": ag,
         "result": "H" if hg > ag else ("D" if hg == ag else "A")}
        for i, (g, a, hg, ag) in enumerate(mecze)
    ])


def test_predict_lambdas_uzywa_produkcyjnego_predict_match(monkeypatch):
    """Sedno: bias ma pochodzić z tej samej funkcji, która liczy predykcje."""
    wolania: list[tuple] = []

    def _szpieg(g, a, df, **kw):
        wolania.append((g, a))
        return {"lambda_g": 1.7, "lambda_a": 1.1}

    monkeypatch.setattr("footstats.core.poisson.predict_match", _szpieg)

    wynik = lo._predict_lambdas(_historia(), "Potega", "Kopciuszek")

    assert wolania, "kalibracja nadal liczy lambde wlasnym wzorem"
    assert wynik == (1.7, 1.1)


def test_kalibracja_nie_stosuje_wlasnych_factorow_przy_pomiarze(monkeypatch):
    """Mierzenie z już nałożoną korektą to sprzężenie zwrotne — bias zbiegłby do 1
    niezależnie od tego, czy model jest dobry."""
    uzyte: list[dict] = []

    def _szpieg(g, a, df, **kw):
        uzyte.append(kw)
        return {"lambda_g": 1.5, "lambda_a": 1.2}

    monkeypatch.setattr("footstats.core.poisson.predict_match", _szpieg)

    lo._predict_lambdas(_historia(), "Potega", "Kopciuszek")

    assert uzyte and uzyte[0].get("use_calibration") is False


def test_brak_predykcji_zwraca_none(monkeypatch):
    """Para bez historii nie moze wnosic do biasu wartosci wymyslonej."""
    monkeypatch.setattr("footstats.core.poisson.predict_match",
                        lambda g, a, df, **kw: None)

    assert lo._predict_lambdas(_historia(), "Ktos", "Ktos2") is None
