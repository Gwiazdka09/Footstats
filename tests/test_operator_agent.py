"""Testy operator agent (mock subprocess / smoke)."""
import json
from unittest.mock import MagicMock, patch


from footstats.operator.manifest import iter_runnable
from footstats.operator.runner import RunResult, run_capability
from footstats.operator.manifest import Capability


def test_iter_runnable_excludes_interactive():
    ids = [c.id for c in iter_runnable()]
    assert "cli.interactive" not in ids


def test_run_capability_help():
    cap = Capability(
        id="test.help",
        label="help",
        category="test",
        cmd=["python", "-m", "footstats.daily_agent", "--help"],
        timeout_s=60,
    )
    r = run_capability(cap)
    assert r.exit_code == 0
    assert r.ok


def test_write_report(tmp_path, monkeypatch):
    from footstats.operator import report as rep_mod

    monkeypatch.setattr(rep_mod, "REPORTS_DIR", tmp_path)
    results = [RunResult("x", True, 0, 1.0, "ok", "")]
    j, m = rep_mod.write_report("test", results, {"extra": 1})
    assert j.exists()
    assert m.exists()
    data = json.loads(j.read_text(encoding="utf-8"))
    assert data["phase"] == "test"
    assert data["summary"]["pass"] == 1


@patch("footstats.operator.workflow.subprocess.run")
def test_workflow_pipeline_skip_draft(mock_run):
    from footstats.operator.workflow import OperatorWorkflow

    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    wf = OperatorWorkflow(user_id=1)
    with patch("footstats.core.coupon_tracker.get_draft_today", return_value={"id": 99}):
        r = wf.run_pipeline(skip_if_draft=True)
    assert r.ok
    mock_run.assert_not_called()
