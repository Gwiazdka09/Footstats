#!/usr/bin/env python
"""
backtest_calibration.py — ścieżka A: jakość predyktora na historii (nie ROI).

Walk-forward rolling λ → prob modelu (1X2 + Over/Under) vs prob rynku (devig kursów).
Metryki: log-loss + Brier (niżej=lepiej) + krzywa kalibracji Over. Rynek = benchmark
(najlepsza możliwa). Model≈rynek → dobrze skalibrowany; model≫rynek → jest co poprawić.

Read-only, offline:  python scripts/backtest_calibration.py --min-hist 6
"""
from __future__ import annotations

import argparse
import glob
import sys
from collections import defaultdict

sys.path.insert(0, "src")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass

import pandas as pd  # noqa: E402

from footstats.core.bet_builder import probability_matrix  # noqa: E402
from footstats.core.goals_value import prob_over_25  # noqa: E402
from footstats.core.wf_harness import devig_1x2  # noqa: E402
from footstats.core.calibration_metrics import (  # noqa: E402
    log_loss, brier_multi, brier_binary, devig_two_way,
)

_HOME_ADV = 1.12


def _probs_1x2(lh, la):
    mat = probability_matrix(lh, la)
    n = len(mat)
    pw = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if h > a)
    pr = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if h == a)
    pp = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if a > h)
    s = pw + pr + pp
    return [pw / s, pr / s, pp / s]


def run(min_hist: int, shrink: float = 1.0) -> None:
    path = glob.glob("**/full_dataset.parquet", recursive=True)[0]
    df = pd.read_parquet(path)
    df = df.dropna(subset=["hg", "ag", "odds_h", "odds_d", "odds_a",
                           "odds_over25", "odds_under25"])
    df = df.sort_values("date").reset_index(drop=True)
    print(f"Dataset: {len(df)} meczów | min_hist={min_hist}\n")

    gf, ga = defaultdict(list), defaultdict(list)
    lg = defaultdict(lambda: [0.0, 0])

    # akumulatory: [suma, n] dla log-loss i Brier, model vs rynek, 1X2 i O/U
    acc = {k: [0.0, 0] for k in ("ll_m_1x2", "ll_k_1x2", "br_m_1x2", "br_k_1x2",
                                 "ll_m_ou", "ll_k_ou", "br_m_ou", "br_k_ou")}
    calib = defaultdict(lambda: [0, 0])  # bin(p_over*10) -> [over_count, n]

    for row in df.itertuples(index=False):
        key = (row.league, row.season)
        th, ta = (key[0], key[1], row.home), (key[0], key[1], row.away)
        hg, ag = int(row.hg), int(row.ag)
        actual_1x2 = 0 if hg > ag else (1 if hg == ag else 2)
        over = (hg + ag) > 2.5

        if len(gf[th]) >= min_hist and len(gf[ta]) >= min_hist:
            la_sum, la_n = lg[key]
            lavg = (la_sum / la_n / 2) if la_n else 1.35
            lh = max(sum(gf[th]) / len(gf[th]) * (sum(ga[ta]) / len(ga[ta])) / max(lavg, .3) * _HOME_ADV, .2)
            laa = max(sum(gf[ta]) / len(gf[ta]) * (sum(ga[th]) / len(ga[th])) / max(lavg, .3), .2)

            # 1X2
            pm = _probs_1x2(lh, laa)
            mk = devig_1x2(row.odds_h, row.odds_d, row.odds_a)
            if mk:
                pk = [mk["pw"] / 100, mk["pr"] / 100, mk["pp"] / 100]
                for tag, probs in (("m", pm), ("k", pk)):
                    acc[f"ll_{tag}_1x2"][0] += log_loss(probs[actual_1x2]); acc[f"ll_{tag}_1x2"][1] += 1
                    acc[f"br_{tag}_1x2"][0] += brier_multi(probs, actual_1x2); acc[f"br_{tag}_1x2"][1] += 1

            # Over/Under (shrink = kalibracja: ściągnij ku 0.5)
            p_over_m = 0.5 + (prob_over_25(lh, laa) - 0.5) * shrink
            mk_ou = devig_two_way(row.odds_over25, row.odds_under25)
            if mk_ou:
                for tag, po in (("m", p_over_m), ("k", mk_ou[0])):
                    acc[f"ll_{tag}_ou"][0] += log_loss(po if over else 1 - po); acc[f"ll_{tag}_ou"][1] += 1
                    acc[f"br_{tag}_ou"][0] += brier_binary(po, over); acc[f"br_{tag}_ou"][1] += 1
                b = min(int(p_over_m * 10), 9)
                calib[b][0] += int(over); calib[b][1] += 1

        gf[th].append(hg); ga[th].append(ag)
        gf[ta].append(ag); ga[ta].append(hg)
        lg[key][0] += hg + ag; lg[key][1] += 1

    def avg(k):
        s, n = acc[k]
        return s / n if n else float("nan")

    print(f"{'metryka':<16} {'MODEL':>9} {'RYNEK':>9}  (niżej=lepiej)")
    print("-" * 48)
    print(f"{'log-loss 1X2':<16} {avg('ll_m_1x2'):>9.4f} {avg('ll_k_1x2'):>9.4f}")
    print(f"{'Brier 1X2':<16} {avg('br_m_1x2'):>9.4f} {avg('br_k_1x2'):>9.4f}")
    print(f"{'log-loss O/U':<16} {avg('ll_m_ou'):>9.4f} {avg('ll_k_ou'):>9.4f}")
    print(f"{'Brier O/U':<16} {avg('br_m_ou'):>9.4f} {avg('br_k_ou'):>9.4f}")
    print(f"\nn(1X2)={acc['ll_m_1x2'][1]}  n(O/U)={acc['ll_m_ou'][1]}")

    print("\nKalibracja Over (model): przedział → realna częstość")
    print(f"{'pred p_over':<14} {'n':>7} {'realny over%':>13}")
    for b in range(10):
        oc, n = calib[b]
        if n:
            print(f"{b*10:>3}-{b*10+10:<9} {n:>7} {100*oc/n:>12.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-hist", type=int, default=6)
    ap.add_argument("--shrink", type=float, default=1.0,
                    help="kalibracja: p'=0.5+(p-0.5)*shrink (1.0=brak, <1 ściąga ku środkowi)")
    a = ap.parse_args()
    run(a.min_hist, a.shrink)
