"""JSON/Markdown reports for operator runs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from footstats.operator.runner import RunResult

REPORTS_DIR = Path(__file__).resolve().parents[3] / "data" / "operator_reports"


def write_report(
    phase: str,
    smoke_results: list[RunResult],
    extra: dict | None = None,
) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    base = REPORTS_DIR / f"operator_{ts}"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "phase": phase,
        "smoke": [r.to_dict() for r in smoke_results],
        "summary": _summarize(smoke_results),
        **(extra or {}),
    }
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_to_markdown(payload), encoding="utf-8")
    return json_path, md_path


def _summarize(results: list[RunResult]) -> dict:
    ok = sum(1 for r in results if r.ok)
    fail = sum(1 for r in results if not r.ok)
    needs = [r.capability_id for r in results if r.needs_cursor]
    return {"pass": ok, "fail": fail, "needs_cursor": needs}


def _to_markdown(payload: dict) -> str:
    lines = [
        f"# Operator Report - {payload.get('phase', '?')}",
        f"**Time:** {payload.get('timestamp', '')}",
        "",
        f"- PASS: {payload['summary']['pass']}",
        f"- FAIL: {payload['summary']['fail']}",
    ]
    if payload["summary"].get("needs_cursor"):
        lines.append(f"- needs_cursor: {', '.join(payload['summary']['needs_cursor'])}")
    lines.append("")
    lines.append("## Smoke")
    lines.append("| ID | OK | exit | sec |")
    lines.append("|----|----|------|-----|")
    for row in payload.get("smoke", []):
        mark = "Y" if row["ok"] else "N"
        lines.append(
            f"| {row['capability_id']} | {mark} | {row['exit_code']} | {row['duration_s']} |"
        )
    if payload.get("review"):
        lines.extend(["", "## Review", "```", str(payload["review"])[:2000], "```"])
    return "\n".join(lines)
