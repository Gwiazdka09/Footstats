"""Operator workflow: preflight, smoke, pipeline, review."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from footstats.config import OPERATOR_STAWKA_A, OPERATOR_STAWKA_B
from footstats.operator.manifest import Capability, iter_runnable
from footstats.operator.report import write_report
from footstats.operator.review import append_review_to_coupon, review_coupons
from footstats.operator.runner import PROJECT_ROOT, RunResult, run_capability
from footstats.operator.smoke_api import run_api_check
from footstats.utils.admin_user import resolve_admin_user_id

log = logging.getLogger(__name__)

STATE_DIR = PROJECT_ROOT / "data" / "operator_state"
STATE_FILE = STATE_DIR / "latest.json"
LOG_FILE = PROJECT_ROOT / "data" / "logs" / "operator_agent.log"


class OperatorWorkflow:
    def __init__(self, user_id: int | None = None) -> None:
        self.user_id = user_id or resolve_admin_user_id()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _save_state(self, phase: str, data: dict) -> None:
        payload = {
            "phase": phase,
            "updated_at": datetime.now().isoformat(),
            "user_id": self.user_id,
            **data,
        }
        STATE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_state(self) -> dict:
        if not STATE_FILE.exists():
            return {}
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _notify(self, text: str) -> None:
        try:
            from footstats.utils.telegram_notify import send_message, telegram_dostepny

            if telegram_dostepny():
                send_message(text)
        except Exception as exc:
            log.warning("Telegram: %s", exc)

    def run_preflight(self) -> RunResult:
        cap = Capability(
            id="preflight",
            label="preflight_footstats",
            category="scripts",
            cmd=["python", "scripts/preflight_footstats.py"],
            timeout_s=120,
            critical=True,
        )
        return run_capability(cap)

    def run_smoke(self) -> list[RunResult]:
        results: list[RunResult] = []
        for cap in iter_runnable():
            if cap.api_check:
                results.append(run_api_check(cap.api_check, cap.id, cap.timeout_s))
            elif cap.cmd:
                results.append(run_capability(cap))
            else:
                results.append(
                    RunResult(cap.id, False, -1, 0.0, "", cap.skip_reason or "SKIP")
                )
        self._save_state(
            "smoke",
            {
                "smoke_ok": sum(1 for r in results if r.ok),
                "smoke_fail": sum(1 for r in results if not r.ok),
                "results": [r.to_dict() for r in results],
            },
        )
        return results

    def run_pipeline(self, dry_run: bool = False, skip_if_draft: bool = True) -> RunResult:
        from footstats.core.coupon_tracker import get_draft_today

        if skip_if_draft and get_draft_today(user_id=self.user_id):
            log.info("Draft exists today - skip pipeline")
            return RunResult("pipeline", True, 0, 0.0, "skipped: draft exists", "")

        cmd = [
            "python",
            "-m",
            "footstats.daily_agent",
            "--faza",
            "draft",
            "--stawka",
            str(OPERATOR_STAWKA_A),
            "--stawka-b",
            str(OPERATOR_STAWKA_B),
            "--waliduj",
        ]
        if dry_run:
            cmd.append("--dry-run")

        self._notify(f"Operator: start daily_agent draft (user_id={self.user_id})")
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=3600,
            )
            duration = time.monotonic() - t0
            ok = proc.returncode == 0
            tail_out = (proc.stdout or "")[-800:]
            tail_err = (proc.stderr or "")[-800:]
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n--- pipeline {datetime.now().isoformat()} ---\n")
                f.write(proc.stdout or "")
                f.write(proc.stderr or "")
            self._save_state("pipeline", {"ok": ok, "exit_code": proc.returncode})
            if ok:
                self._notify("Operator: daily_agent draft OK")
            else:
                self._notify(f"Operator: daily_agent FAIL exit={proc.returncode}")
            return RunResult("pipeline", ok, proc.returncode, duration, tail_out, tail_err)
        except subprocess.TimeoutExpired:
            return RunResult(
                "pipeline", False, -9, 3600.0, "", "Timeout 3600s", needs_cursor=True
            )

    def run_review(self, max_legs: int = 8, persist: bool = True) -> list[dict[str, Any]]:
        from footstats.core.coupon_tracker import get_active_coupons

        coupons = get_active_coupons(user_id=self.user_id)
        if not coupons:
            log.info("No active coupons for review")
            return []

        rows = [dict(c) if hasattr(c, "keys") else c for c in coupons]
        reviews = review_coupons(rows, max_legs=max_legs)
        if persist:
            for item in reviews:
                cid = item.get("coupon_id")
                if cid:
                    append_review_to_coupon(
                        int(cid), item.get("ai_review", ""), self.user_id
                    )

        summary = "\n".join(
            f"Coupon #{r['coupon_id']}: {r['legs_count']} legs"
            for r in reviews
        )
        self._notify(f"Operator: coupon review\n{summary[:1500]}")
        self._save_state("review", {"count": len(reviews)})
        return reviews

    def run_full(
        self,
        skip_smoke: bool = False,
        dry_run_pipeline: bool = False,
    ) -> tuple[Path, Path]:
        self._notify(f"Operator: start FULL (user_id={self.user_id})")
        smoke_results: list[RunResult] = []

        pf = self.run_preflight()
        smoke_results.append(pf)
        if not pf.ok:
            self._notify(f"Operator: preflight FAIL - {pf.stderr_tail[:400]}")

        if not skip_smoke:
            smoke_results.extend(self.run_smoke())

        critical_fail = any(
            not r.ok
            for r in smoke_results
            if r.capability_id
            in ("preflight", "api.health", "api.login_admin", "pytest.gate")
        )
        pipeline_result = None
        if not critical_fail:
            pipeline_result = self.run_pipeline(dry_run=dry_run_pipeline)
            smoke_results.append(pipeline_result)
        else:
            self._notify("Operator: skip pipeline - critical smoke fail")

        reviews: list[dict[str, Any]] = []
        if not critical_fail and (pipeline_result is None or pipeline_result.ok):
            reviews = self.run_review()

        extra = {"review": reviews, "user_id": self.user_id}
        json_p, md_p = write_report("full", smoke_results, extra)
        self._notify(f"Operator: done. Report: {md_p.name}")
        return json_p, md_p
