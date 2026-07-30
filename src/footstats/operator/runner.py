"""Subprocess runner for operator capabilities."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from footstats.operator.manifest import Capability

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class RunResult:
    capability_id: str
    ok: bool
    exit_code: int
    duration_s: float
    stdout_tail: str
    stderr_tail: str
    needs_cursor: bool = False

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "ok": self.ok,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 2),
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "needs_cursor": self.needs_cursor,
        }


def _komenda(cmd: list[str]) -> list[str]:
    """
    Podmienia gołe "python"/"python3" na `sys.executable`.

    Bez tego capability odpalała się systemowym interpreterem, a nie tym z venva —
    czyli bez zainstalowanych zależności projektu ("No module named 'rich'"),
    mimo że w bieżącym procesie wszystko działa.
    """
    if cmd and cmd[0] in ("python", "python3"):
        return [sys.executable, *cmd[1:]]
    return list(cmd)


def _env_z_pythonpath(env: dict[str, str] | None) -> dict[str, str]:
    """
    Środowisko podprocesu z gwarantowanym `src/` w PYTHONPATH.

    Capabilities odpalają `python -m footstats.<modul>`, a pakiet mieszka w `src/`.
    W obrazach Dockera PYTHONPATH=/app/src jest ustawiony, ale lokalnie (bez
    instalacji editable) już nie — podproces dostawał wtedy
    "No module named 'footstats'" i capability wyglądała na uszkodzoną,
    choć problem był wyłącznie w ścieżce.
    """
    bazowe = dict(env if env is not None else os.environ)
    src = str(PROJECT_ROOT / "src")
    obecne = bazowe.get("PYTHONPATH", "")
    if src not in obecne.split(os.pathsep):
        bazowe["PYTHONPATH"] = f"{src}{os.pathsep}{obecne}" if obecne else src
    return bazowe


def _tail(text: str, max_chars: int = 800) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return "..." + text[-max_chars:]


def run_capability(
    cap: Capability,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> RunResult:
    if not cap.cmd:
        return RunResult(
            capability_id=cap.id,
            ok=False,
            exit_code=-1,
            duration_s=0.0,
            stdout_tail="",
            stderr_tail="No cmd (use api_check)",
        )
    work = cwd or PROJECT_ROOT
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            _komenda(cap.cmd),
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=cap.timeout_s,
            env=_env_z_pythonpath(env),
        )
        duration = time.monotonic() - t0
        ok = proc.returncode == 0
        stderr = proc.stderr or ""
        needs_cursor = any(
            x in stderr.lower()
            for x in ("playwright", "timeout", "captcha", "browser")
        )
        return RunResult(
            capability_id=cap.id,
            ok=ok,
            exit_code=proc.returncode,
            duration_s=duration,
            stdout_tail=_tail(proc.stdout or ""),
            stderr_tail=_tail(stderr),
            needs_cursor=needs_cursor and not ok,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - t0
        return RunResult(
            capability_id=cap.id,
            ok=False,
            exit_code=-9,
            duration_s=duration,
            stdout_tail=_tail(exc.stdout.decode() if exc.stdout else ""),
            stderr_tail=f"Timeout after {cap.timeout_s}s",
            needs_cursor=True,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        duration = time.monotonic() - t0
        log.exception("run_capability %s", cap.id)
        return RunResult(
            capability_id=cap.id,
            ok=False,
            exit_code=-1,
            duration_s=duration,
            stdout_tail="",
            stderr_tail=str(exc),
        )
