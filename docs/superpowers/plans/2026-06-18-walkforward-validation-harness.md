# Walk-Forward Validation Harness (Cel A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zbudować wierny produkcyjnie walk-forward harness, który replayuje statystyczny model FootStats (classic `predict_match` + Dixon-Coles `predict_match_bayesian` + `ensemble_probs` z devig kursów historycznych) na 14 634 meczach offline, raportuje trafność + kalibrację per pasmo + tabelę A/B, bez kluczy API i bez zapisu do prod Neon.

**Architecture:** Nowy moduł `core/wf_harness.py` (adapter schematu, devig, predict_one, pętla no-lookahead, raport) + `core/wf_db.py` (osobny zapis SQLite, NIE Neon). Drobna modyfikacja `core/poisson.py` — flagi `use_xg`/`use_calibration` by wyłączyć kontaminację `datetime.now()` w replay historycznym. CLI `scripts/run_walkforward_prod.py`. Stary `walkforward.py` zostaje jako legacy (model-zabawka), nie ruszamy.

**Tech Stack:** Python 3, pandas, numpy, scipy.stats, sqlite3, pytest. Dane: `footstats.data.historical_loader.load_cached()`.

---

## Kontekst kluczowy (przeczytaj przed startem)

**Schematy kolumn:**
- `load_cached()` zwraca DataFrame z kolumnami: `date, league, season, home, away, hg, ag, result, hs, as_, hst, ast, hc, ac, hy, ay, odds_h, odds_d, odds_a, odds_over25, odds_under25, total_goals, over25, btts`. `result` ∈ {`H`,`D`,`A`}.
- Produkcyjne `predict_match` / `predict_match_bayesian` oczekują kolumn: `gospodarz, goscie, gole_g, gole_a`. → potrzebny adapter.

**Produkcyjne wiring (z `quick_picks.py:212-228`) — odtwarzamy wiernie:**
```python
_pred_p = predict_match(g, a, df_mecze, heurystyka_g=..., h2h_g=..., fortress_g=..., klasyfikacja=...)
_p_pois = {"pw": _pred_p["p_wygrana"], "pr": _pred_p["p_remis"], "pp": _pred_p["p_przegrana"]}
_p_bzz  = {"pw": ..., "pr": ..., "pp": ...}   # w prod: z kursów Bzzoiro; u nas: devig kursów historycznych
_bl = ensemble_probs(_p_pois, _p_bzz, liga=liga)   # klucze pw/pr/pp/bt/o25
```
`predict_match` zwraca m.in.: `p_wygrana, p_remis, p_przegrana, over25, btts` (procenty 0-100), `lambda_g, lambda_a`.
`predict_match_bayesian` zwraca: `pw, pr, pa, lambda_g, lambda_a` (ułamki 0-1; uwaga `pa` = away win = nasze `pp`).
`ensemble_probs(p_poisson, p_bzzoiro, wagi=None, liga=None)` — ważona średnia po wspólnych kluczach; domyślne wagi per-liga (Poisson/Bzzoiro ~0.45/0.55, A2 70/30 dla części lig).

**Gotchy do neutralizacji w replay (KRYTYCZNE — inaczej lookahead):**
- `poisson.py:199-222` xG blend używa `datetime.now().year` jako sezon → dla meczu z 2015 sięga po xG sezonu bieżącego. Wyłączyć flagą `use_xg=False`.
- `poisson.py:187-194` `load_calibration()` mnoży λ globalnym współczynnikiem z pliku. Flaga `use_calibration` (domyślnie zostawiamy jak prod = True, ale flagowalne dla A/B).
- Enrichmenty live (importance/heurystyka/h2h/fortress/klasyfikacja) NIE są odtwarzalne historycznie → przekazujemy `None` (predict_match defaultuje do neutralnych 1.0).

**Izolacja DB:** `utils/db.connect` to teraz czyste PostgreSQL/Neon. Harness NIE wolno go używać do zapisu. Własny sqlite3 → `data/walkforward.db`.

**No-lookahead:** dla meczu w dacie `d`, historia = wszystkie mecze z `date < d` (po filtrze ligi). Min. historia drużyny: skip jeśli `predict_match` zwróci `None`.

**Metryka główna:** trafność 1X2 (tip = argmax{pw,pr,pp}, mapowanie `1→H, X→D, 2→A`). Drugorzędna: Over 2.5.

---

## File Structure

- Create: `src/footstats/core/wf_db.py` — sqlite3 writer/reader do `data/walkforward.db` (tabela `wf_runs`). Jedna odpowiedzialność: persystencja wyników backtestu, odseparowana od Neon.
- Create: `src/footstats/core/wf_harness.py` — adapter schematu, devig, predict_one, run loop, raport (accuracy + kalibracja + A/B). Czysty rdzeń obliczeniowy.
- Modify: `src/footstats/core/poisson.py` — dodać parametry `use_xg: bool = True`, `use_calibration: bool = True` do `predict_match` (wstecznie kompatybilne).
- Create: `scripts/run_walkforward_prod.py` — CLI (argumenty: `--liga`, `--max`, `--od`, `--bayesian`, `--no-ensemble`, `--no-calibration`).
- Test: `tests/test_wf_db.py`, `tests/test_wf_harness.py`, dopisek do `tests/test_poisson.py`.

---

## Task 1: Flagi `use_xg` / `use_calibration` w `predict_match`

**Files:**
- Modify: `src/footstats/core/poisson.py:56-69` (sygnatura) oraz bloki `187-194` (calibration) i `199-222` (xG).
- Test: `tests/test_poisson.py`

- [ ] **Step 1: Write the failing test**

Dopisz na końcu `tests/test_poisson.py`:

```python
def test_predict_match_use_xg_flag_disables_now_based_xg(df_mecze_fixture):
    """use_xg=False musi pominąć blok xG (datetime.now) — wynik deterministyczny w replay historycznym."""
    from footstats.core.poisson import predict_match
    g, a = df_mecze_fixture["gospodarz"].iloc[0], df_mecze_fixture["goscie"].iloc[0]

    pred_xg_off = predict_match(g, a, df_mecze_fixture, use_xg=False, use_calibration=False)
    assert pred_xg_off is not None
    # Powtórzenie daje identyczny wynik (brak zależności od now()/cache)
    pred_again = predict_match(g, a, df_mecze_fixture, use_xg=False, use_calibration=False)
    assert pred_xg_off["lambda_g"] == pred_again["lambda_g"]
    assert pred_xg_off["lambda_a"] == pred_again["lambda_a"]
```

Jeśli w pliku brak fixture `df_mecze_fixture`, dodaj go (minimalny, ≥4 mecze, kolumny `gospodarz, goscie, gole_g, gole_a, data`):

```python
import pandas as pd
import pytest

@pytest.fixture
def df_mecze_fixture():
    rows = []
    for i in range(8):
        rows.append({"gospodarz": "Alfa", "goscie": "Beta", "gole_g": 2, "gole_a": 1,
                     "data": f"2020-01-{i+1:02d}"})
        rows.append({"gospodarz": "Beta", "goscie": "Alfa", "gole_g": 0, "gole_a": 1,
                     "data": f"2020-02-{i+1:02d}"})
    return pd.DataFrame(rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_poisson.py::test_predict_match_use_xg_flag_disables_now_based_xg -v`
Expected: FAIL — `predict_match() got an unexpected keyword argument 'use_xg'`.

- [ ] **Step 3: Modify predict_match signature + guards**

W `src/footstats/core/poisson.py` zmień sygnaturę (linie 56-69), dodając dwa parametry na końcu przed `)`:

```python
def predict_match(
    g: str, a: str,
    df_mecze: pd.DataFrame,
    importance_g: dict = None,
    importance_a: dict = None,
    heurystyka_g: dict = None,
    heurystyka_a: dict = None,
    h2h_g: dict = None,
    h2h_a: dict = None,
    fortress_g: dict = None,
    first_leg_g=None, first_leg_a=None,
    stage: str = "REGULAR_SEASON",
    klasyfikacja: dict = None,
    use_xg: bool = True,
    use_calibration: bool = True,
) -> dict | None:
```

Owiń blok kalibracji (obecne linie ~187-194) warunkiem:

```python
    # ── Kalibracja modelu (walk-forward bias correction) ─────────────
    if use_calibration:
        try:
            from footstats.core.lambda_optimizer import load_calibration
            _cal_h, _cal_a = load_calibration()
            lambda_g *= _cal_h
            lambda_a *= _cal_a
        except (ImportError, OSError, ValueError):
            pass  # Brak pliku kalibracji → działaj z domyślnymi lambdami

        lambda_g = max(0.05, lambda_g)
        lambda_a = max(0.05, lambda_a)
```

Owiń blok xG (obecne linie ~199-225) warunkiem:

```python
    # ── xG blend (Understat cache-only, no live request) ─────────────
    if use_xg:
        try:
            from footstats.scrapers.understat_xg import _cache_get, _to_slug
            from datetime import datetime as _dt
            _season = _dt.now().year if _dt.now().month >= 7 else _dt.now().year - 1
            xg_h = _cache_get(_to_slug(g), _season) or {}
            xg_a = _cache_get(_to_slug(a), _season) or {}
            _XG_W = 0.20

            h_xgf, h_xga = xg_h.get("xg_for_avg"), xg_h.get("xga_avg")
            a_xgf, a_xga = xg_a.get("xg_for_avg"), xg_a.get("xga_avg")

            if h_xgf and h_xgf > 0:
                xg_lambda_g = (h_xgf + a_xga) / 2 if (a_xga and a_xga > 0) else h_xgf
                lambda_g = round((1 - _XG_W) * lambda_g + _XG_W * xg_lambda_g, 4)
            if a_xgf and a_xgf > 0:
                xg_lambda_a = (a_xgf + h_xga) / 2 if (h_xga and h_xga > 0) else a_xgf
                lambda_a = round((1 - _XG_W) * lambda_a + _XG_W * xg_lambda_a, 4)
        except (ImportError, AttributeError, OSError, ValueError, KeyError):
            pass  # xG cache niedostępny → czyste lambdy Poissona

        lambda_g = max(0.05, lambda_g)
        lambda_a = max(0.05, lambda_a)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_poisson.py::test_predict_match_use_xg_flag_disables_now_based_xg -v`
Expected: PASS.

- [ ] **Step 5: Run full poisson suite (regresja wstecznej kompatybilności)**

Run: `pytest tests/test_poisson.py tests/test_poisson_xg.py -v`
Expected: wszystkie PASS (domyślne `use_xg=True`/`use_calibration=True` = stare zachowanie).

- [ ] **Step 6: Commit**

```bash
git add src/footstats/core/poisson.py tests/test_poisson.py
git commit -m "feat: flagi use_xg/use_calibration w predict_match (replay offline bez lookahead)"
```

---

## Task 2: Adapter schematu historical → prod

**Files:**
- Create: `src/footstats/core/wf_harness.py`
- Test: `tests/test_wf_harness.py`

- [ ] **Step 1: Write the failing test**

Utwórz `tests/test_wf_harness.py`:

```python
import pandas as pd
import pytest

from footstats.core.wf_harness import adapt_to_prod_schema


def test_adapt_to_prod_schema_maps_columns():
    df = pd.DataFrame([
        {"date": "2020-01-01", "league": "NED-Eredivisie", "home": "Ajax",
         "away": "PSV", "hg": 2, "ag": 1, "result": "H"},
    ])
    out = adapt_to_prod_schema(df)
    assert {"gospodarz", "goscie", "gole_g", "gole_a", "data"}.issubset(out.columns)
    assert out["gospodarz"].iloc[0] == "Ajax"
    assert out["goscie"].iloc[0] == "PSV"
    assert out["gole_g"].iloc[0] == 2
    assert out["gole_a"].iloc[0] == 1


def test_adapt_to_prod_schema_does_not_mutate_input():
    df = pd.DataFrame([{"date": "2020-01-01", "league": "X", "home": "A",
                        "away": "B", "hg": 1, "ag": 0, "result": "H"}])
    cols_before = list(df.columns)
    adapt_to_prod_schema(df)
    assert list(df.columns) == cols_before  # bez mutacji


def test_adapt_to_prod_schema_missing_column_raises():
    df = pd.DataFrame([{"home": "A", "away": "B"}])  # brak hg/ag
    with pytest.raises(ValueError, match="brak"):
        adapt_to_prod_schema(df)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wf_harness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'footstats.core.wf_harness'`.

- [ ] **Step 3: Write minimal implementation**

Utwórz `src/footstats/core/wf_harness.py`:

```python
"""core/wf_harness.py — wierny produkcyjnie walk-forward harness (Cel A).

Replay statystycznego modelu (predict_match + Dixon-Coles + ensemble z devig
kursów historycznych) na danych z historical_loader. Offline, bez Neon, bez API.
"""
from __future__ import annotations

import pandas as pd

_COL_MAP = {"home": "gospodarz", "away": "goscie", "hg": "gole_g", "ag": "gole_a"}
_REQUIRED = ("home", "away", "hg", "ag")


def adapt_to_prod_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Mapuje kolumny historical_loader → schema oczekiwana przez predict_match.

    Zwraca NOWY DataFrame (bez mutacji wejścia). Zachowuje date→data, league.
    """
    brak = [c for c in _REQUIRED if c not in df.columns]
    if brak:
        raise ValueError(f"adapt_to_prod_schema: brak wymaganych kolumn: {brak}")

    out = df.rename(columns=_COL_MAP).copy()
    if "date" in out.columns:
        out["data"] = out["date"]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wf_harness.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/footstats/core/wf_harness.py tests/test_wf_harness.py
git commit -m "feat: adapter schematu historical->prod w wf_harness"
```

---

## Task 3: Devig kursów historycznych → p_bzzoiro

**Files:**
- Modify: `src/footstats/core/wf_harness.py`
- Test: `tests/test_wf_harness.py`

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_wf_harness.py`:

```python
from footstats.core.wf_harness import devig_1x2


def test_devig_1x2_sums_to_100():
    p = devig_1x2(odds_h=1.57, odds_d=3.9, odds_a=7.5)
    assert p is not None
    total = p["pw"] + p["pr"] + p["pp"]
    assert abs(total - 100.0) < 0.01  # procenty, marża usunięta


def test_devig_1x2_favorite_has_highest_prob():
    p = devig_1x2(odds_h=1.57, odds_d=3.9, odds_a=7.5)
    assert p["pw"] > p["pr"] > p["pp"]


def test_devig_1x2_none_on_missing_odds():
    assert devig_1x2(odds_h=None, odds_d=3.9, odds_a=7.5) is None
    assert devig_1x2(odds_h=float("nan"), odds_d=3.9, odds_a=7.5) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wf_harness.py::test_devig_1x2_sums_to_100 -v`
Expected: FAIL — `ImportError: cannot import name 'devig_1x2'`.

- [ ] **Step 3: Write minimal implementation**

Dopisz do `src/footstats/core/wf_harness.py` (import na górze: `import math`):

```python
import math


def devig_1x2(odds_h, odds_d, odds_a) -> dict | None:
    """Z kursów 1X2 liczy prawdopodobieństwa implikowane bez marży (procenty 0-100).

    Metoda proporcjonalna (basic devig): p_i = (1/odds_i) / Σ(1/odds_j).
    Zwraca {pw, pr, pp} lub None gdy któryś kurs brakuje/nieprawidłowy.
    """
    vals = [odds_h, odds_d, odds_a]
    for o in vals:
        if o is None or (isinstance(o, float) and math.isnan(o)) or o is False or o <= 1.0:
            return None
    inv = [1.0 / o for o in vals]
    s = sum(inv)
    if s <= 0:
        return None
    return {
        "pw": round(inv[0] / s * 100, 1),
        "pr": round(inv[1] / s * 100, 1),
        "pp": round(inv[2] / s * 100, 1),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wf_harness.py -v`
Expected: wszystkie PASS.

- [ ] **Step 5: Commit**

```bash
git add src/footstats/core/wf_harness.py tests/test_wf_harness.py
git commit -m "feat: devig kursów 1X2 -> p_bzzoiro w wf_harness"
```

---

## Task 4: `predict_one` — złożenie classic + bayesian + ensemble

**Files:**
- Modify: `src/footstats/core/wf_harness.py`
- Test: `tests/test_wf_harness.py`

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_wf_harness.py`:

```python
from footstats.core.wf_harness import predict_one, ModelFlags


def _hist_prod():
    """Historia w schemacie prod: dwie drużyny, dużo meczów (>OSTATNIE_N)."""
    rows = []
    for i in range(15):
        rows.append({"gospodarz": "Alfa", "goscie": "Beta", "gole_g": 2, "gole_a": 0,
                     "data": f"2019-{(i % 12) + 1:02d}-01", "league": "TEST"})
        rows.append({"gospodarz": "Beta", "goscie": "Alfa", "gole_g": 1, "gole_a": 1,
                     "data": f"2019-{(i % 12) + 1:02d}-15", "league": "TEST"})
    import pandas as pd
    return pd.DataFrame(rows)


def test_predict_one_baseline_returns_tip_and_conf():
    flags = ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=False)
    res = predict_one("Alfa", "Beta", _hist_prod(), league="TEST",
                      odds_h=1.8, odds_d=3.5, odds_a=4.2, flags=flags)
    assert res is not None
    assert res["tip"] in ("1", "X", "2")
    assert 0.0 <= res["conf"] <= 1.0
    assert abs(res["pw"] + res["pr"] + res["pp"] - 100.0) < 0.5


def test_predict_one_bayesian_arm_runs():
    flags = ModelFlags(use_bayesian=True, use_ensemble=True, use_calibration=False)
    res = predict_one("Alfa", "Beta", _hist_prod(), league="TEST",
                      odds_h=1.8, odds_d=3.5, odds_a=4.2, flags=flags)
    assert res is not None
    assert res["tip"] in ("1", "X", "2")


def test_predict_one_no_odds_falls_back_to_poisson_only():
    flags = ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=False)
    res = predict_one("Alfa", "Beta", _hist_prod(), league="TEST",
                      odds_h=None, odds_d=None, odds_a=None, flags=flags)
    assert res is not None
    assert res["no_odds"] is True


def test_predict_one_returns_none_when_no_history():
    import pandas as pd
    empty = pd.DataFrame(columns=["gospodarz", "goscie", "gole_g", "gole_a", "data", "league"])
    flags = ModelFlags()
    assert predict_one("X", "Y", empty, league="TEST",
                       odds_h=2.0, odds_d=3.0, odds_a=3.5, flags=flags) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wf_harness.py::test_predict_one_baseline_returns_tip_and_conf -v`
Expected: FAIL — `ImportError: cannot import name 'predict_one'`.

- [ ] **Step 3: Write minimal implementation**

Dopisz do `src/footstats/core/wf_harness.py` (importy na górze):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelFlags:
    """Przełączniki warstw modelu do A/B. Domyślne = ścieżka produkcyjna."""
    use_bayesian: bool = False      # dołącz Dixon-Coles jako ramię modelu
    use_ensemble: bool = True       # blenduj z devig kursów (jak prod)
    use_calibration: bool = True    # load_calibration() w predict_match
    w_bayesian: float = 0.5         # waga ramienia bayesian w blendzie modelu


def _weighted_blend(a: dict, b: dict, wa: float, wb: float) -> dict:
    """Ważona średnia dwóch dictów {pw,pr,pp} (procenty). Renormalizacja do 100."""
    tot = wa + wb
    out = {k: (a[k] * wa + b[k] * wb) / tot for k in ("pw", "pr", "pp")}
    s = sum(out.values()) or 1.0
    return {k: round(v / s * 100, 4) for k, v in out.items()}


def predict_one(g, a, hist_prod, league, odds_h, odds_d, odds_a, flags) -> dict | None:
    """Pełna predykcja jednego meczu — wiernie wg produkcji.

    classic predict_match (xG OFF — replay) ⊕ opcjonalnie Dixon-Coles ⊕ devig kursów.
    Zwraca {tip, conf, pw, pr, pp, no_odds} (procenty) lub None gdy brak historii.
    """
    from footstats.core.poisson import predict_match
    from footstats.core.ensemble import ensemble_probs

    pred = predict_match(
        g, a, hist_prod,
        use_xg=False,                       # KRYTYCZNE: brak datetime.now() w replay
        use_calibration=flags.use_calibration,
    )
    if not pred:
        return None

    p_model = {"pw": pred["p_wygrana"], "pr": pred["p_remis"], "pp": pred["p_przegrana"]}

    # Ramię Dixon-Coles (opcjonalne)
    if flags.use_bayesian:
        from footstats.core.poisson_bayesian import predict_match_bayesian
        bay = predict_match_bayesian(g, a, hist_prod)
        if bay:
            p_bay = {"pw": bay["pw"] * 100, "pr": bay["pr"] * 100, "pp": bay["pa"] * 100}
            p_model = _weighted_blend(p_model, p_bay, 1.0 - flags.w_bayesian, flags.w_bayesian)

    # Ensemble z kursami (devig) — jak prod (poisson ⊕ bzzoiro)
    p_bzz = devig_1x2(odds_h, odds_d, odds_a)
    no_odds = p_bzz is None
    if flags.use_ensemble and p_bzz is not None:
        p_final = ensemble_probs(p_model, p_bzz, liga=league)
    else:
        p_final = p_model

    tip_map = {"pw": "1", "pr": "X", "pp": "2"}
    best_key = max(("pw", "pr", "pp"), key=lambda k: p_final[k])
    return {
        "tip": tip_map[best_key],
        "conf": round(p_final[best_key] / 100.0, 4),
        "pw": round(p_final["pw"], 1),
        "pr": round(p_final["pr"], 1),
        "pp": round(p_final["pp"], 1),
        "no_odds": no_odds,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wf_harness.py -v`
Expected: wszystkie PASS.

- [ ] **Step 5: Commit**

```bash
git add src/footstats/core/wf_harness.py tests/test_wf_harness.py
git commit -m "feat: predict_one (classic+bayesian+ensemble) w wf_harness"
```

---

## Task 5: `wf_db.py` — osobny zapis SQLite (NIE Neon)

**Files:**
- Create: `src/footstats/core/wf_db.py`
- Test: `tests/test_wf_db.py`

- [ ] **Step 1: Write the failing test**

Utwórz `tests/test_wf_db.py`:

```python
import sqlite3
from pathlib import Path

from footstats.core.wf_db import init_db, save_run, load_run


def test_save_and_load_run(tmp_path):
    db = tmp_path / "wf_test.db"
    init_db(db)
    rows = [
        {"run_tag": "baseline", "league": "TEST", "match_date": "2020-01-01",
         "home": "A", "away": "B", "actual_res": "H", "pred_tip": "1",
         "pred_conf": 0.62, "correct": 1, "no_odds": 0},
        {"run_tag": "baseline", "league": "TEST", "match_date": "2020-01-02",
         "home": "C", "away": "D", "actual_res": "A", "pred_tip": "1",
         "pred_conf": 0.55, "correct": 0, "no_odds": 0},
    ]
    save_run(db, rows)
    loaded = load_run(db, "baseline")
    assert len(loaded) == 2
    assert loaded[0]["home"] == "A"


def test_init_db_is_sqlite_not_neon(tmp_path):
    """Guard: harness pisze do pliku SQLite, nie do Neon."""
    db = tmp_path / "wf_test.db"
    init_db(db)
    assert db.exists()
    con = sqlite3.connect(db)
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    con.close()
    assert "wf_runs" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wf_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'footstats.core.wf_db'`.

- [ ] **Step 3: Write minimal implementation**

Utwórz `src/footstats/core/wf_db.py`:

```python
"""core/wf_db.py — persystencja wyników walk-forward do SQLite (offline).

ŚWIADOMIE odseparowane od footstats.utils.db (Neon prod) — backtest nie może
zanieczyszczać produkcji. Domyślny plik: data/walkforward.db.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "walkforward.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wf_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    run_tag    TEXT NOT NULL,
    league     TEXT,
    match_date TEXT,
    home       TEXT,
    away       TEXT,
    actual_res TEXT,
    pred_tip   TEXT,
    pred_conf  REAL,
    correct    INTEGER,
    no_odds    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_wf_runs_tag ON wf_runs(run_tag);
"""

_COLS = ("run_tag", "league", "match_date", "home", "away",
         "actual_res", "pred_tip", "pred_conf", "correct", "no_odds")


def init_db(db_path: Path | str = DEFAULT_DB) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


def save_run(db_path: Path | str, rows: list[dict]) -> int:
    con = sqlite3.connect(Path(db_path))
    try:
        con.executemany(
            f"INSERT INTO wf_runs ({','.join(_COLS)}) "
            f"VALUES ({','.join('?' * len(_COLS))})",
            [tuple(r.get(c) for c in _COLS) for r in rows],
        )
        con.commit()
        return len(rows)
    finally:
        con.close()


def load_run(db_path: Path | str, run_tag: str) -> list[dict]:
    con = sqlite3.connect(Path(db_path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute("SELECT * FROM wf_runs WHERE run_tag = ? ORDER BY id", (run_tag,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wf_db.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/footstats/core/wf_db.py tests/test_wf_db.py
git commit -m "feat: wf_db sqlite writer odseparowany od Neon"
```

---

## Task 6: Pętla walk-forward + raport (accuracy + kalibracja)

**Files:**
- Modify: `src/footstats/core/wf_harness.py`
- Test: `tests/test_wf_harness.py`

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_wf_harness.py`:

```python
from footstats.core.wf_harness import run_walkforward, report


def _hist_df_english(n_pairs=60):
    """DataFrame w schemacie historical_loader (English) z kursami."""
    import pandas as pd
    rows = []
    teams = ["Alfa", "Beta", "Gama", "Delta"]
    d = 1
    for i in range(n_pairs):
        h = teams[i % 4]
        a = teams[(i + 1) % 4]
        rows.append({
            "date": pd.Timestamp("2019-01-01") + pd.Timedelta(days=i * 3),
            "league": "TEST", "home": h, "away": a,
            "hg": (i % 3), "ag": (i % 2), "result": "H" if (i % 3) > (i % 2) else "A",
            "odds_h": 1.9, "odds_d": 3.4, "odds_a": 4.0,
        })
    return pd.DataFrame(rows)


def test_run_walkforward_produces_records():
    df = _hist_df_english()
    flags = ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=False)
    out = run_walkforward(df, league="TEST", flags=flags, run_tag="t", verbose=False)
    assert len(out) > 0
    assert set(["tip", "correct", "pred_conf", "match_date"]).issubset(out.columns)
    # no-lookahead: pierwsze ~20% pominięte (start od historii)
    assert out["match_date"].min() > str(df["date"].min())[:10]


def test_report_has_accuracy_and_calibration():
    df = _hist_df_english()
    flags = ModelFlags(use_calibration=False)
    out = run_walkforward(df, league="TEST", flags=flags, run_tag="t", verbose=False)
    txt = report(out)
    assert "Accuracy 1X2" in txt
    assert "pasmo pewno" in txt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wf_harness.py::test_run_walkforward_produces_records -v`
Expected: FAIL — `ImportError: cannot import name 'run_walkforward'`.

- [ ] **Step 3: Write minimal implementation**

Dopisz do `src/footstats/core/wf_harness.py`:

```python
def run_walkforward(df, league=None, flags=None, run_tag="run",
                    max_matches=None, min_date=None, verbose=True):
    """Pętla walk-forward (no-lookahead) na danych historical_loader (schema English).

    Dla każdego meczu: historia = mecze z date < match.date (po filtrze ligi),
    zaadaptowana do schematu prod; predict_one; porównanie z wynikiem.
    Zwraca DataFrame rekordów (kolumny m.in. tip, correct, pred_conf, match_date).
    """
    flags = flags or ModelFlags()

    work = df if league is None else df[df["league"] == league]
    work = work.sort_values("date").reset_index(drop=True)

    if min_date:
        work = work[work["date"] >= pd.Timestamp(min_date)].reset_index(drop=True)
    else:
        start = max(50, len(work) // 5)   # start od ~20% by mieć historię
        work = work.iloc[start:].reset_index(drop=True)
    if max_matches:
        work = work.head(max_matches)

    if verbose:
        print(f"[WF] liga={league or 'wszystkie'} | meczów={len(work):,} | tag={run_tag}")

    records = []
    for _, row in work.iterrows():
        hist = df[df["date"] < row["date"]]
        if league:
            hist = hist[hist["league"] == league]
        if len(hist) < 4:
            continue
        hist_prod = adapt_to_prod_schema(hist)

        res = predict_one(
            row["home"], row["away"], hist_prod, league=row.get("league"),
            odds_h=row.get("odds_h"), odds_d=row.get("odds_d"), odds_a=row.get("odds_a"),
            flags=flags,
        )
        if res is None:
            continue

        actual = row.get("result", "")
        if actual not in ("H", "D", "A"):
            continue
        tip_to_res = {"1": "H", "X": "D", "2": "A"}
        correct = 1 if tip_to_res[res["tip"]] == actual else 0

        records.append({
            "run_tag": run_tag,
            "league": row.get("league", ""),
            "match_date": str(row["date"])[:10],
            "home": row["home"], "away": row["away"],
            "actual_res": actual,
            "tip": res["tip"], "pred_tip": res["tip"],
            "pred_conf": res["conf"],
            "correct": correct,
            "no_odds": 1 if res["no_odds"] else 0,
        })

    out = pd.DataFrame(records)
    if verbose and len(out):
        acc = out["correct"].mean() * 100
        print(f"[WF] Accuracy 1X2: {acc:.1f}% (n={len(out)})")
    return out


def report(out: pd.DataFrame) -> str:
    """Raport tekstowy: accuracy globalnie/per liga + kalibracja per pasmo pewności."""
    if out is None or len(out) == 0:
        return "Brak rekordów do raportu."

    linie = ["=" * 60, "  WALK-FORWARD (prod model) — FootStats", "=" * 60]
    acc = out["correct"].mean() * 100
    linie.append(f"  Accuracy 1X2: {acc:.1f}% (n={len(out)})")
    no_odds = int(out["no_odds"].sum()) if "no_odds" in out.columns else 0
    linie.append(f"  Mecze bez kursów (Poisson-only): {no_odds}")

    linie.append("\n  Per liga:")
    for liga, grp in out.groupby("league"):
        linie.append(f"    {liga}: {grp['correct'].mean()*100:.1f}% (n={len(grp)})")

    linie.append("\n  Kalibracja per pasmo pewności (1X2):")
    for lo, hi in [(0.33, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 1.01)]:
        sub = out[(out["pred_conf"] >= lo) & (out["pred_conf"] < hi)]
        if len(sub) >= 5:
            linie.append(f"    {lo:.0%}-{hi:.0%}: {sub['correct'].mean()*100:.1f}% (n={len(sub)})")
    linie.append("=" * 60)
    return "\n".join(linie)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wf_harness.py -v`
Expected: wszystkie PASS.

- [ ] **Step 5: Commit**

```bash
git add src/footstats/core/wf_harness.py tests/test_wf_harness.py
git commit -m "feat: pętla walk-forward + raport (accuracy + kalibracja per pasmo)"
```

---

## Task 7: CLI + A/B + zapis do wf_db

**Files:**
- Create: `scripts/run_walkforward_prod.py`
- Modify: `src/footstats/core/wf_harness.py` (funkcja `run_ab` łącząca run + zapis + raport porównawczy)
- Test: `tests/test_wf_harness.py`

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_wf_harness.py`:

```python
from footstats.core.wf_harness import run_ab


def test_run_ab_compares_arms(tmp_path):
    df = _hist_df_english()
    db = tmp_path / "ab.db"
    arms = {
        "baseline": ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=False),
        "dixoncoles": ModelFlags(use_bayesian=True, use_ensemble=True, use_calibration=False),
    }
    summary = run_ab(df, arms, league="TEST", db_path=db, verbose=False)
    assert set(summary.keys()) == {"baseline", "dixoncoles"}
    for tag, stat in summary.items():
        assert "accuracy" in stat and "n" in stat
        assert stat["n"] > 0
    # zapis do osobnej sqlite
    from footstats.core.wf_db import load_run
    assert len(load_run(db, "baseline")) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wf_harness.py::test_run_ab_compares_arms -v`
Expected: FAIL — `ImportError: cannot import name 'run_ab'`.

- [ ] **Step 3: Write minimal implementation**

Dopisz do `src/footstats/core/wf_harness.py` (import na górze: `from footstats.core import wf_db`):

```python
from footstats.core import wf_db


def run_ab(df, arms: dict, league=None, db_path=None, max_matches=None,
           min_date=None, verbose=True) -> dict:
    """Uruchamia wiele ramion (tag -> ModelFlags), zapisuje do wf_db, zwraca podsumowanie.

    Zwraca {tag: {"accuracy": float, "n": int}}.
    """
    db_path = db_path or wf_db.DEFAULT_DB
    wf_db.init_db(db_path)

    summary = {}
    for tag, flags in arms.items():
        out = run_walkforward(df, league=league, flags=flags, run_tag=tag,
                              max_matches=max_matches, min_date=min_date, verbose=verbose)
        if len(out):
            wf_db.save_run(db_path, out.to_dict("records"))
            summary[tag] = {"accuracy": round(out["correct"].mean() * 100, 1), "n": len(out)}
            if verbose:
                print(report(out))
        else:
            summary[tag] = {"accuracy": None, "n": 0}
    return summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wf_harness.py::test_run_ab_compares_arms -v`
Expected: PASS.

- [ ] **Step 5: Create CLI**

Utwórz `scripts/run_walkforward_prod.py`:

```python
#!/usr/bin/env python
"""run_walkforward_prod.py — wierny walk-forward modelu prod (Cel A), offline.

Użycie:
    python scripts/run_walkforward_prod.py --liga "NED-Eredivisie"
    python scripts/run_walkforward_prod.py --max 2000 --bayesian
    python scripts/run_walkforward_prod.py            # wszystkie ligi, A/B baseline vs dixoncoles
"""
import argparse
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
warnings.filterwarnings("ignore")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass


def main():
    p = argparse.ArgumentParser(description="FootStats walk-forward (prod model, offline)")
    p.add_argument("--liga", default=None, help="Filtruj ligę (domyślnie wszystkie)")
    p.add_argument("--max", type=int, default=None, help="Max meczów")
    p.add_argument("--od", default=None, help="Od daty YYYY-MM-DD")
    p.add_argument("--no-calibration", action="store_true", help="Wyłącz load_calibration()")
    args = p.parse_args()

    from footstats.data.historical_loader import load_cached
    from footstats.core.wf_harness import run_ab, ModelFlags

    df = load_cached()
    use_cal = not args.no_calibration

    arms = {
        "baseline":   ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=use_cal),
        "dixoncoles": ModelFlags(use_bayesian=True,  use_ensemble=True, use_calibration=use_cal),
        "poisson_only": ModelFlags(use_bayesian=False, use_ensemble=False, use_calibration=use_cal),
    }
    summary = run_ab(df, arms, league=args.liga, max_matches=args.max, min_date=args.od)

    print("\n" + "=" * 60)
    print("  A/B PODSUMOWANIE")
    print("=" * 60)
    for tag, stat in summary.items():
        print(f"  {tag:<14} accuracy={stat['accuracy']}%  n={stat['n']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Smoke-test CLI na małej próbce**

Run: `python scripts/run_walkforward_prod.py --liga "NED-Eredivisie" --max 300 --no-calibration`
Expected: wypisuje raporty per ramię + tabelę A/B z `accuracy` i `n` > 0; plik `data/walkforward.db` powstaje; brak połączeń do Neon.

- [ ] **Step 7: Commit**

```bash
git add src/footstats/core/wf_harness.py scripts/run_walkforward_prod.py tests/test_wf_harness.py
git commit -m "feat: A/B walk-forward + CLI run_walkforward_prod (Cel A kompletny)"
```

---

## Task 8: Pełen przebieg + weryfikacja kalibracji (analiza, nie kod)

**Files:** brak zmian kodu — uruchomienie i interpretacja.

- [ ] **Step 1: Pełen przebieg na wszystkich ligach**

Run: `python scripts/run_walkforward_prod.py --no-calibration`
Expected: A/B na ~11k meczów (po odjęciu startowych 20% + braków historii). Zapis do `data/walkforward.db`.

- [ ] **Step 2: Sprawdź kalibrację**

W raporcie każdego ramienia odczytaj sekcję "Kalibracja per pasmo pewności":
- Jeśli trafność ROŚNIE z pasmem (33-45% < 45-55% < ... < 65%+) → kalibracja zdrowa.
- Jeśli wysokie pasmo < niskie → **nadal odwrócona** → przejście do Celu B (polowanie na bug kalibracji) jako następny spec.

- [ ] **Step 3: Werdykt A/B**

Porównaj `accuracy` ramion `baseline` vs `dixoncoles` vs `poisson_only`:
- `dixoncoles > baseline` → Dixon-Coles podnosi trafność → kandydat do wpięcia w prod (osobny spec).
- `baseline > poisson_only` → ensemble z kursami pomaga (potwierdza wagi 70/30).
- Zapisz wnioski do `STATUS.md` / `TODO.md` (sekcja walidacji λ).

- [ ] **Step 4: Commit wniosków**

```bash
git add STATUS.md TODO.md
git commit -m "docs: wyniki walk-forward A/B (kalibracja + Dixon-Coles werdykt)"
```

---

## Self-Review (wypełnione)

**Spec coverage:**
- Adapter schematu → Task 2. ✅
- Devig kursów → p_bzzoiro → Task 3. ✅
- Produkcyjny predykt (classic+bayesian+ensemble) → Task 4. ✅
- Flagi A/B + neutralizacja xG/now() lookahead → Task 1 + Task 4 (ModelFlags) + Task 7. ✅
- Output: accuracy global/per-liga + kalibracja per pasmo → Task 6. ✅
- Zapis do osobnej backtest DB (nie Neon) → Task 5. ✅
- Tor 2 (calibration_monitor) → pasywny, bez kodu (spec sekcja 4). ✅
- Kryterium "czy kalibracja nadal odwrócona" → Task 8 Step 2. ✅
- Obsługa błędów (brak historii/kursów/result/None) → Task 4 + Task 6. ✅
- Testy ≥80% nowego kodu → Tasks 2-7 (unit + integration). ✅

**Placeholder scan:** brak TBD/TODO/„handle edge cases" — każdy krok ma pełny kod. ✅

**Type consistency:** `ModelFlags` (use_bayesian/use_ensemble/use_calibration/w_bayesian) spójne w Task 4/6/7. `predict_one` zwraca {tip,conf,pw,pr,pp,no_odds} — używane spójnie w run_walkforward. `wf_db` kolumny `_COLS` spójne z rekordami `run_walkforward` (run_tag,league,match_date,home,away,actual_res,pred_tip,pred_conf,correct,no_odds). ✅

**Uwaga wykonawcza:** `predict_match_bayesian` zwraca klucz `pa` (away win) — w `predict_one` mapowane na `pp`. Nie pomylić z `pp`.
