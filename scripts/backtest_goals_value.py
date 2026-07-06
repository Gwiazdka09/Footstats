#!/usr/bin/env python
"""
backtest_goals_value.py — walk-forward ROI value-bettingu na Over/Under 2.5.

Pivot (docs/PREDICTION_ROADMAP.md): gole zamiast 1X2, value zamiast win-rate.
Rolling per-drużyna gole strzelone/stracone (w obrębie liga+sezon) → λ Poissona →
P(Over 2.5) → stawiaj TYLKO gdy P×kurs − 1 > próg. ROI vs kursy z parquet.

Read-only, offline. Użycie:
    python scripts/backtest_goals_value.py
    python scripts/backtest_goals_value.py --margin 0.08 --min-hist 6
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

from footstats.core.goals_value import prob_over_25, is_value  # noqa: E402

_HOME_ADV = 1.12  # gospodarz strzela nieco więcej (klub)


def _lambdas(gf_h, ga_h, gf_a, ga_a, league_avg):
    """λ_gosp/λ_gość = atak×obrona_rywala / średnia_ligi (Dixon-Coles ratio form)."""
    la = max(league_avg, 0.3)
    lh = gf_h * ga_a / la * _HOME_ADV
    laa = gf_a * ga_h / la
    return max(lh, 0.2), max(laa, 0.2)


def run(margin: float, min_hist: int, mode: str = "goals") -> None:
    path = glob.glob("**/full_dataset.parquet", recursive=True)[0]
    df = pd.read_parquet(path)
    need = ["hg", "ag", "odds_over25", "odds_under25"]
    if mode == "shots":
        need += ["hst", "ast"]
    df = df.dropna(subset=need)
    df = df.sort_values("date").reset_index(drop=True)
    print(f"Dataset: {len(df)} meczów | tryb={mode} margin={margin} min_hist={min_hist}\n")

    # stan rolling per (liga, sezon)
    gf = defaultdict(list)   # (liga,sezon,team) -> gole strzelone
    ga = defaultdict(list)   # -> gole stracone
    sf = defaultdict(list)   # -> strzały celne oddane
    sa = defaultdict(list)   # -> strzały celne przeciw
    lg_goals = defaultdict(lambda: [0.0, 0])  # -> [suma_goli, mecze]
    lg_sot = defaultdict(lambda: [0.0, 0.0])  # -> [suma_goli, suma_sot] (konwersja)

    stats = {k: {"n": 0, "wins": 0, "ret": 0.0} for k in ("over_val", "under_val", "base_over")}

    for row in df.itertuples(index=False):
        key = (row.league, row.season)
        th, ta = (key[0], key[1], row.home), (key[0], key[1], row.away)
        tot = int(row.hg) + int(row.ag)
        over = tot > 2.5

        # baseline: zawsze Over (pokazuje marżę booka)
        stats["base_over"]["n"] += 1
        if over:
            stats["base_over"]["wins"] += 1
            stats["base_over"]["ret"] += float(row.odds_over25) - 1
        else:
            stats["base_over"]["ret"] -= 1

        # predykcja tylko gdy dość historii obu drużyn
        if len(gf[th]) >= min_hist and len(gf[ta]) >= min_hist:
            la_sum, la_n = lg_goals[key]
            league_avg = (la_sum / la_n / 2) if la_n else 1.35  # gole/drużyna/mecz
            if mode == "shots":
                # xG proxy: strzały celne × konwersja (gole/SoT ligi)
                g_sum, s_sum = lg_sot[key]
                conv = (g_sum / s_sum) if s_sum > 0 else 0.30
                gf_h = sum(sf[th]) / len(sf[th]) * conv
                ga_h = sum(sa[th]) / len(sa[th]) * conv
                gf_a = sum(sf[ta]) / len(sf[ta]) * conv
                ga_a = sum(sa[ta]) / len(sa[ta]) * conv
            else:
                gf_h = sum(gf[th]) / len(gf[th]); ga_h = sum(ga[th]) / len(ga[th])
                gf_a = sum(gf[ta]) / len(gf[ta]); ga_a = sum(ga[ta]) / len(ga[ta])
            lh, laa = _lambdas(gf_h, ga_h, gf_a, ga_a, league_avg)
            p_over = prob_over_25(lh, laa)
            p_under = 1 - p_over

            if is_value(p_over, float(row.odds_over25), margin):
                stats["over_val"]["n"] += 1
                if over:
                    stats["over_val"]["wins"] += 1
                    stats["over_val"]["ret"] += float(row.odds_over25) - 1
                else:
                    stats["over_val"]["ret"] -= 1
            if is_value(p_under, float(row.odds_under25), margin):
                stats["under_val"]["n"] += 1
                if not over:
                    stats["under_val"]["wins"] += 1
                    stats["under_val"]["ret"] += float(row.odds_under25) - 1
                else:
                    stats["under_val"]["ret"] -= 1

        # update historii PO predykcji (bez lookahead)
        gf[th].append(row.hg); ga[th].append(row.ag)
        gf[ta].append(row.ag); ga[ta].append(row.hg)
        lg_goals[key][0] += tot; lg_goals[key][1] += 1
        if mode == "shots":
            sf[th].append(row.hst); sa[th].append(row.ast)
            sf[ta].append(row.ast); sa[ta].append(row.hst)
            lg_sot[key][0] += tot; lg_sot[key][1] += float(row.hst) + float(row.ast)

    print(f"{'strategia':<12} {'zakłady':>8} {'trafność':>9} {'ROI':>8} {'zysk(u)':>9}")
    print("-" * 50)
    for k, label in (("base_over", "Over (baza)"), ("over_val", "Over value"),
                     ("under_val", "Under value")):
        s = stats[k]
        if not s["n"]:
            print(f"{label:<12} {'0':>8}  (brak)")
            continue
        hit = 100 * s["wins"] / s["n"]
        roi = 100 * s["ret"] / s["n"]
        print(f"{label:<12} {s['n']:>8} {hit:>8.1f}% {roi:>7.1f}% {s['ret']:>+9.1f}")

    tot_val = stats["over_val"]["ret"] + stats["under_val"]["ret"]
    tot_n = stats["over_val"]["n"] + stats["under_val"]["n"]
    if tot_n:
        print("-" * 50)
        print(f"{'VALUE razem':<12} {tot_n:>8} {'':>9} {100*tot_val/tot_n:>7.1f}% {tot_val:>+9.1f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, default=0.05, help="próg edge (EV na jednostkę)")
    ap.add_argument("--min-hist", type=int, default=5, help="min meczów historii drużyny")
    ap.add_argument("--mode", choices=("goals", "shots"), default="goals",
                    help="źródło λ: gole vs strzały celne (xG proxy)")
    a = ap.parse_args()
    run(a.margin, a.min_hist, a.mode)
