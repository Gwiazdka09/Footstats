# -*- coding: utf-8 -*-
"""
Operator Agent � FootStats orchestrator.

Usage:
    python -m footstats.operator_agent --faza full
    python -m footstats.operator_agent --only smoke
    python -m footstats.operator_agent --only review
    python -m footstats.operator_agent --only pipeline [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("footstats.operator")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="FootStats Operator Agent")
    parser.add_argument(
        "--faza",
        choices=["full", "preflight", "smoke", "pipeline", "review"],
        default="full",
        help="Workflow phase (default: full)",
    )
    parser.add_argument(
        "--only",
        choices=["smoke", "review", "pipeline", "preflight"],
        help="Run single phase (overrides --faza)",
    )
    parser.add_argument("--skip-smoke", action="store_true", help="Skip smoke in full run")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="daily_agent with --dry-run (no DB/Telegram writes)",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Override user_id (default: resolve Admin_JG)",
    )
    parser.add_argument("--max-legs", type=int, default=8, help="Max legs per coupon in review")
    args = parser.parse_args()

    from footstats.operator.workflow import OperatorWorkflow

    phase = args.only or args.faza
    wf = OperatorWorkflow(user_id=args.user_id)

    if phase == "preflight":
        r = wf.run_preflight()
        print("PASS" if r.ok else "FAIL", r.stderr_tail or r.stdout_tail)
        return 0 if r.ok else 1

    if phase == "smoke":
        results = wf.run_smoke()
        for r in results:
            status = "OK" if r.ok else "FAIL"
            print(f"  [{status}] {r.capability_id} ({r.duration_s:.1f}s)")
        fail = sum(1 for r in results if not r.ok)
        return 0 if fail == 0 else 1

    if phase == "pipeline":
        r = wf.run_pipeline(dry_run=args.dry_run)
        print("PASS" if r.ok else "FAIL", r.stderr_tail[:500])
        return 0 if r.ok else 1

    if phase == "review":
        reviews = wf.run_review(max_legs=args.max_legs)
        print(f"Review: {len(reviews)} coupons")
        return 0

    json_p, md_p = wf.run_full(skip_smoke=args.skip_smoke, dry_run_pipeline=args.dry_run)
    print(f"Report: {md_p}")
    try:
        rep = json.loads(json_p.read_text(encoding="utf-8"))
        if rep.get("summary", {}).get("fail", 0) > 0:
            return 1
    except (OSError, ValueError, KeyError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
