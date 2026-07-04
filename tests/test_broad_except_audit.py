"""Test: broad except counts don't regress beyond baseline.

Fails when new `except Exception` or bare `except:` are added beyond the
current baseline.  To lower the baseline, narrow the exceptions in source
and update the number here.  Never raise it without a PR comment explaining
why the broad catch is justified.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "footstats"

# Current counts — regression gate, not perfection.
# Reduce over time as exceptions are narrowed.
BASELINE: dict[str, int] = {
    "ai/client.py": 2,
    "ai/post_match_analyzer.py": 2,
    "ai/rag.py": 2,
    "ai/rag_embeddings.py": 3,
    "ai/trainer.py": 3,
    "api/auth.py": 2,  # forgot-password: DB lookup + mailer graceful → ZAWSZE 200 (anty-enumeracja kont)
    "api/main.py": 3,  # startup DB init + health endpoint (5xx-proof) + Sentry init guard
    "api/routes/bankroll.py": 1,
    "api/routes/model_stats.py": 1,  # /admin/model-vs-live: błąd DB → 503 nie 500
    "api/routes/coupons.py": 3,
    "api/routes/status.py": 2,
    "core/async_utils.py": 1,
    "core/backtest.py": 3,
    "core/calibration.py": 3,
    "core/checkpoint.py": 4,
    "core/circuit_breaker.py": 1,
    "core/cloud_draft.py": 2,  # /cron/draft graceful (nigdy 500) + freshness guard (observability nie wywala draftu)
    "core/clv_tracker.py": 1,
    "core/coupon_settlement.py": 4,
    "core/coupon_tracker.py": 0,
    "core/daily_phases.py": 1,  # Superbet BB scrape — Playwright raises varied types (przeniesione z daily_agent.py)
    "core/data.py": 1,
    "core/ensemble.py": 1,
    "core/ensemble_optimizer.py": 1,
    "core/lambda_optimizer.py": 1,
    "core/poisson.py": 1,
    "core/probability_calibrator.py": 1,
    "core/processing.py": 2,
    "core/quick_picks.py": 1,
    "core/response_cache.py": 2,
    "core/weekly_picks.py": 3,
    "daily_agent.py": 0,
    "dashboard.py": 5,
    "data/context_scraper.py": 1,
    "data/historical_loader.py": 7,
    "db/migrations.py": 2,
    "evening_agent.py": 0,
    "export/pdf_font.py": 1,
    "operator/review.py": 2,
    "operator/runner.py": 1,
    "operator/smoke_api.py": 1,
    "operator/workflow.py": 1,
    "operator_agent.py": 1,
    "scrapers/api_football.py": 2,
    "scrapers/base_playwright.py": 1,
    "scrapers/bzzoiro.py": 4,
    "scrapers/enriched.py": 2,
    "scrapers/flashscore_match.py": 4,
    "scrapers/flashscore_results.py": 4,
    "scrapers/form_scraper.py": 6,
    "scrapers/kursy.py": 3,
    "scrapers/results_updater.py": 0,
    "scrapers/source_manager.py": 1,
    "scrapers/sts.py": 0,
    "ai/analyzer.py": 3,
    "ai/analyzer_helpers.py": 1,
    "scrapers/superbet.py": 0,
    "scrapers/superbet_bb.py": 4,
    "scrapers/superoferta.py": 4,
    "scrapers/understat_xg.py": 4,
    "scrapers/zawodtyper_referees.py": 1,
    "utils/admin_user.py": 1,
    "utils/cache.py": 6,
    "utils/db.py": 1,  # best-effort cleanup martwej conn z puli (Neon idle timeout)
    "utils/logging.py": 1,  # bezpieczna_funkcja decorator (wraps arbitrary fns)
    "utils/safe_http.py": 1,  # BezpiecznePobieranie.wykonaj — API client fallback (z logging.py)
    "utils/telegram_notify.py": 1,
    "weekly_report.py": 4,
}

# Exempt from audit (CLI — scheduled for refactor in Phase 10.4)
EXEMPT = {"cli.py"}


def _count_broad_excepts(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if re.match(r"^except\s*:", stripped) or re.match(r"^except\s+Exception\b", stripped):
            count += 1
    return count


def _all_py_files() -> list[Path]:
    return [
        p for p in SRC.rglob("*.py")
        if p.name not in EXEMPT and "__pycache__" not in p.parts
    ]


@pytest.mark.parametrize("rel,limit", list(BASELINE.items()))
def test_baseline_not_exceeded(rel: str, limit: int) -> None:
    path = SRC / rel
    if not path.exists():
        pytest.skip(f"{rel} not found")
    count = _count_broad_excepts(path)
    assert count <= limit, (
        f"{rel}: {count} broad except(s), baseline={limit}. "
        "Narrow to specific exceptions, then lower the baseline."
    )


def test_no_new_files_with_broad_excepts() -> None:
    """New files (not in BASELINE) must have zero broad excepts."""
    violations: list[str] = []
    for path in _all_py_files():
        rel = path.relative_to(SRC).as_posix()
        if rel in BASELINE:
            continue
        count = _count_broad_excepts(path)
        if count > 0:
            violations.append(f"{rel}: {count}")
    assert not violations, (
        "New files with broad excepts detected — add to BASELINE or narrow:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
