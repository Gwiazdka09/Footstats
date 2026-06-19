"""core/wf_harness.py — wierny produkcyjnie walk-forward harness (Cel A).

Replay statystycznego modelu (predict_match + Dixon-Coles + ensemble z devig
kursów historycznych) na danych z historical_loader. Offline, bez Neon, bez API.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from footstats.core import wf_db

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

    # Ramię Dixon-Coles (opcjonalne) — wspólna funkcja z prod (parytet)
    if flags.use_bayesian:
        from footstats.core.poisson_bayesian import blend_dixon_coles
        p_model = blend_dixon_coles(p_model, g, a, hist_prod, w_bayesian=flags.w_bayesian)

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


def run_walkforward(df, league=None, flags=None, run_tag="run",
                    max_matches=None, min_date=None, verbose=True):
    """Pętla walk-forward (no-lookahead) na danych historical_loader (schema English).

    Dla każdego meczu: historia = mecze z date < match.date (po filtrze ligi),
    zaadaptowana do schematu prod; predict_one; porównanie z wynikiem.
    Zwraca DataFrame rekordów (kolumny m.in. tip, correct, pred_conf, match_date).

    Optymalizacja O(n^2) -> O(n*k): baza historii (po filtrze ligi) liczona
    i adaptowana RAZ przed pętlą; granica historii per mecz wyznaczana przez
    `np.searchsorted` na posortowanych datach (prefiks) — zachowuje to samo
    członkostwo i tę samą kolejność wierszy co oryginalny per-mecz skan,
    co gwarantuje bit-identyczny wynik (model jest wrażliwy na porządek —
    `poisson.py` używa `.tail(N)` po pozycji).
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

    # Baza historii (po filtrze ligi) — liczona i adaptowana RAZ, nie per mecz.
    base = df if league is None else df[df["league"] == league]
    base = base.sort_values("date", kind="stable").reset_index(drop=True)
    base_prod = adapt_to_prod_schema(base)
    dates = base["date"].to_numpy()

    records = []
    for _, row in work.iterrows():
        idx = int(np.searchsorted(dates, np.datetime64(row["date"]), side="left"))
        if idx < 4:
            continue
        hist_prod = base_prod.iloc[:idx]

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
