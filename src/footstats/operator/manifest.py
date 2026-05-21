"""FootStats capability registry for operator smoke tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    id: str
    label: str
    category: str
    cmd: list[str] | None = None
    api_check: str | None = None
    timeout_s: int = 120
    requires_groq: bool = False
    requires_network: bool = False
    critical: bool = False
    interactive: bool = False
    skip_reason: str | None = None


def _root_cmds(module: str, *extra: str) -> list[str]:
    return ["python", "-m", module, *extra]


CAPABILITIES: list[Capability] = [
    Capability(
        id="api.health",
        label="GET /health",
        category="api",
        api_check="health",
        timeout_s=30,
        critical=True,
    ),
    Capability(
        id="api.login_admin",
        label="POST /api/auth/login (admin)",
        category="api",
        api_check="login",
        timeout_s=30,
        critical=True,
    ),
    Capability(
        id="api.matches_today",
        label="GET /api/matches/today",
        category="api",
        api_check="matches_today",
        timeout_s=60,
        critical=True,
    ),
    Capability(
        id="api.matches_analyze",
        label="POST /api/matches/analyze",
        category="api",
        api_check="matches_analyze",
        timeout_s=120,
        critical=True,
    ),
    Capability(
        id="api.coupon_kelly",
        label="POST /api/coupon/kelly",
        category="api",
        api_check="coupon_kelly",
        timeout_s=60,
        critical=True,
    ),
    Capability(
        id="api.coupon_place_dry",
        label="POST /api/coupon/place (validate only)",
        category="api",
        api_check="coupon_place_validate",
        timeout_s=60,
        critical=False,
    ),
    Capability(
        id="api.status",
        label="GET /api/status",
        category="api",
        api_check="status",
        timeout_s=30,
    ),
    Capability(
        id="api.coupons_active",
        label="GET /api/coupons/active",
        category="api",
        api_check="coupons_active",
        timeout_s=30,
    ),
    Capability(
        id="daily_agent.help",
        label="daily_agent --help",
        category="pipeline",
        cmd=_root_cmds("footstats.daily_agent", "--help"),
        timeout_s=60,
        critical=True,
    ),
    Capability(
        id="daily_agent_scheduler.help",
        label="daily_agent_scheduler --help",
        category="pipeline",
        cmd=["python", "-m", "footstats.daily_agent_scheduler", "--help"],
        timeout_s=60,
    ),
    Capability(
        id="coupon_settlement.help",
        label="coupon_settlement --help",
        category="pipeline",
        cmd=_root_cmds("footstats.core.coupon_settlement", "--help"),
        timeout_s=60,
    ),
    Capability(
        id="lambda_optimizer.help",
        label="lambda_optimizer --help",
        category="core",
        cmd=_root_cmds("footstats.core.lambda_optimizer", "--help"),
        timeout_s=60,
    ),
    Capability(
        id="post_match_analyzer.help",
        label="post_match_analyzer --help",
        category="ai",
        cmd=_root_cmds("footstats.ai.post_match_analyzer", "--help"),
        timeout_s=60,
    ),
    Capability(
        id="bankroll.help",
        label="bankroll --help",
        category="core",
        cmd=_root_cmds("footstats.core.bankroll", "--help"),
        timeout_s=60,
    ),
    Capability(
        id="backtest.help",
        label="backtest --help",
        category="core",
        cmd=_root_cmds("footstats.core.backtest", "--help"),
        timeout_s=60,
    ),
    Capability(
        id="scripts.backup_db",
        label="scripts/backup_db.py",
        category="scripts",
        cmd=["python", "scripts/backup_db.py"],
        timeout_s=120,
        critical=True,
    ),
    Capability(
        id="scripts.preflight",
        label="scripts/preflight_footstats.py",
        category="scripts",
        cmd=["python", "scripts/preflight_footstats.py"],
        timeout_s=120,
        critical=True,
    ),
    Capability(
        id="cli.interactive",
        label="cli.py (interactive)",
        category="cli",
        interactive=True,
        skip_reason="Rich Prompt manual only",
    ),
    Capability(
        id="pytest.gate",
        label="pytest gate (health, coupon_tracker, admin_user)",
        category="tests",
        cmd=[
            "python",
            "-m",
            "pytest",
            "tests/test_health.py",
            "tests/test_coupon_tracker.py",
            "tests/test_admin_user.py",
            "-q",
            "--tb=no",
        ],
        timeout_s=180,
        critical=True,
    ),
]


def iter_runnable() -> list[Capability]:
    return [c for c in CAPABILITIES if not c.interactive and not c.skip_reason]


def by_id(cap_id: str) -> Capability | None:
    for c in CAPABILITIES:
        if c.id == cap_id:
            return c
    return None
