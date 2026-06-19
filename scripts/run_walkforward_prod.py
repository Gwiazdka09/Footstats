#!/usr/bin/env python
"""run_walkforward_prod.py — wierny walk-forward modelu prod (Cel A), offline.

Użycie:
    python scripts/run_walkforward_prod.py --liga "NED-Eredivisie"
    python scripts/run_walkforward_prod.py --max 2000
    python scripts/run_walkforward_prod.py            # wszystkie ligi, A/B 3 ramiona

UWAGA: kalibracja (load_calibration) jest DOMYŚLNIE WYŁĄCZONA — statyczny
model_calibration.json może być dopasowany na danych pokrywających okno replay
(lookahead → zawyżona trafność). Włącz świadomie flagą --with-calibration.
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
    p.add_argument("--with-calibration", action="store_true",
                   help="Włącz load_calibration() (RYZYKO lookahead — patrz docstring)")
    args = p.parse_args()

    from footstats.data.historical_loader import load_cached
    from footstats.core.wf_harness import run_ab, ModelFlags

    use_cal = args.with_calibration
    if use_cal:
        print("⚠️  KALIBRACJA WŁĄCZONA — wyniki mogą być zawyżone (lookahead). "
              "Do czystego out-of-sample uruchom bez --with-calibration.")

    df = load_cached()

    arms = {
        "baseline":     ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=use_cal),
        "dixoncoles":   ModelFlags(use_bayesian=True,  use_ensemble=True, use_calibration=use_cal),
        "poisson_only": ModelFlags(use_bayesian=False, use_ensemble=False, use_calibration=use_cal),
    }
    summary = run_ab(df, arms, league=args.liga, max_matches=args.max, min_date=args.od)

    print("\n" + "=" * 60)
    print("  A/B PODSUMOWANIE" + ("  (KALIBRACJA ON)" if use_cal else "  (out-of-sample)"))
    print("=" * 60)
    for tag, stat in summary.items():
        print(f"  {tag:<14} accuracy={stat['accuracy']}%  n={stat['n']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
