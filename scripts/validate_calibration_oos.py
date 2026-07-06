#!/usr/bin/env python
"""
validate_calibration_oos.py — OUT-OF-SAMPLE walidacja shrinkage (ścieżka A).

Wcześniejszy shrink był in-sample. Tu: fituj k na PIERWSZYCH 60% chronologicznie,
zastosuj na OSTATNICH 40% (test). Jeśli test-log-loss spada → lever REALNY, nie overfit.

Read-only, offline:  python scripts/validate_calibration_oos.py
"""
from __future__ import annotations

import glob
import sys
from collections import defaultdict

sys.path.insert(0, "src")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass

import pandas as pd  # noqa: E402

from footstats.core.goals_value import prob_over_25  # noqa: E402
from footstats.core.calibration_metrics import log_loss, shrink_prob, devig_two_way  # noqa: E402

_HOME_ADV = 1.12
_MIN_HIST = 6


def _mean_ll(pairs, k):
    """Średni log-loss O/U po shrink k."""
    if not pairs:
        return float("nan")
    s = 0.0
    for p, over in pairs:
        pc = shrink_prob(p, k)
        s += log_loss(pc if over else 1 - pc)
    return s / len(pairs)


def run() -> None:
    path = glob.glob("**/full_dataset.parquet", recursive=True)[0]
    df = pd.read_parquet(path)
    df = df.dropna(subset=["hg", "ag", "odds_over25", "odds_under25"])
    df = df.sort_values("date").reset_index(drop=True)

    gf, ga = defaultdict(list), defaultdict(list)
    lg = defaultdict(lambda: [0.0, 0])
    pairs = []          # (p_over_model, over_bool) chronologicznie
    mkt_pairs = []      # rynek dla porównania

    for row in df.itertuples(index=False):
        key = (row.league, row.season)
        th, ta = (key[0], key[1], row.home), (key[0], key[1], row.away)
        hg, ag = int(row.hg), int(row.ag)
        over = (hg + ag) > 2.5
        if len(gf[th]) >= _MIN_HIST and len(gf[ta]) >= _MIN_HIST:
            la_sum, la_n = lg[key]
            lavg = (la_sum / la_n / 2) if la_n else 1.35
            lh = max(sum(gf[th]) / len(gf[th]) * (sum(ga[ta]) / len(ga[ta])) / max(lavg, .3) * _HOME_ADV, .2)
            laa = max(sum(gf[ta]) / len(gf[ta]) * (sum(ga[th]) / len(ga[th])) / max(lavg, .3), .2)
            pairs.append((prob_over_25(lh, laa), over))
            mk = devig_two_way(row.odds_over25, row.odds_under25)
            mkt_pairs.append((mk[0] if mk else None, over))
        gf[th].append(hg); ga[th].append(ag)
        gf[ta].append(ag); ga[ta].append(hg)
        lg[key][0] += hg + ag; lg[key][1] += 1

    split = int(len(pairs) * 0.6)
    train, test = pairs[:split], pairs[split:]
    print(f"Pary: {len(pairs)} | train {len(train)} | test {len(test)}\n")

    # fit k na train (grid)
    best_k, best_ll = 1.0, 1e9
    for i in range(2, 21):
        k = i / 20.0
        ll = _mean_ll(train, k)
        if ll < best_ll:
            best_ll, best_k = ll, k
    print(f"Najlepsze k na TRAIN: {best_k} (train log-loss {best_ll:.4f})\n")

    # zastosuj na test
    ll_test_none = _mean_ll(test, 1.0)
    ll_test_cal = _mean_ll(test, best_k)
    mkt_test = [(p, o) for p, o in mkt_pairs[split:] if p is not None]
    ll_mkt = sum(log_loss(p if o else 1 - p) for p, o in mkt_test) / len(mkt_test)

    print("=== TEST (out-of-sample, ostatnie 40%) log-loss O/U ===")
    print(f"  model bez kalibracji (k=1.0): {ll_test_none:.4f}")
    print(f"  model + shrink k={best_k}:      {ll_test_cal:.4f}")
    print(f"  RYNEK (benchmark):            {ll_mkt:.4f}")
    poprawa = 100 * (ll_test_none - ll_test_cal) / ll_test_none
    luka_przed = ll_test_none - ll_mkt
    luka_po = ll_test_cal - ll_mkt
    print(f"\n  Poprawa OOS: {poprawa:+.1f}% log-loss")
    if luka_przed > 0:
        print(f"  Luka do rynku ścięta: {100*(1-luka_po/luka_przed):.0f}% "
              f"({luka_przed:.4f} → {luka_po:.4f})")


if __name__ == "__main__":
    run()
