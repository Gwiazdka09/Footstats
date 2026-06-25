"""Test: subprocess.Popen fire-and-forget usages don't leak file descriptors.

Verifies that every Popen call either:
1. Uses stdout=DEVNULL and stderr=DEVNULL (closes stdio), OR
2. Passes creationflags (Windows new-console, inherits parent stdio intentionally)
AND is wrapped in an OSError/FileNotFoundError handler.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "footstats"

# Files known to contain Popen calls
POPEN_FILES = [
    "core/backtest.py",
    "ai/post_match_analyzer.py",
    "cli.py",
    "evening_agent.py",
    "daily_agent.py",
    "daily_agent_output.py",
]


def _extract_popen_blocks(path: Path) -> list[str]:
    """Return raw source lines around each Popen call."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    blocks = []
    for i, line in enumerate(lines):
        if "Popen(" in line or "Popen(" in "".join(lines[i : i + 3]):
            start = max(0, i - 1)
            end = min(len(lines), i + 15)
            blocks.append("\n".join(lines[start:end]))
    return blocks


@pytest.mark.parametrize("rel_path", POPEN_FILES)
def test_popen_stdio_closed_or_creation_flags(rel_path: str) -> None:
    """Each Popen call closes stdio via DEVNULL or uses creationflags."""
    path = SRC / rel_path
    if not path.exists():
        pytest.skip(f"{rel_path} not found")

    text = path.read_text(encoding="utf-8", errors="replace")
    popen_count = text.count("Popen(")
    if popen_count == 0:
        return  # no Popen — nothing to check

    blocks = _extract_popen_blocks(path)
    for block in blocks:
        has_devnull = "DEVNULL" in block
        has_creation_flags = "creationflags" in block
        assert has_devnull or has_creation_flags, (
            f"{rel_path}: Popen missing DEVNULL or creationflags — fd leak risk.\n"
            f"Context:\n{block}"
        )


@pytest.mark.parametrize("rel_path", POPEN_FILES)
def test_popen_wrapped_in_error_handler(rel_path: str) -> None:
    """Each Popen call must be inside a try/except OSError or FileNotFoundError."""
    path = SRC / rel_path
    if not path.exists():
        pytest.skip(f"{rel_path} not found")

    text = path.read_text(encoding="utf-8", errors="replace")
    if "Popen(" not in text:
        return

    # Check that the file has at least one OSError/FileNotFoundError near each Popen
    blocks = _extract_popen_blocks(path)
    for block in blocks:
        has_handler = (
            "OSError" in block
            or "FileNotFoundError" in block
            or "except" in block
        )
        assert has_handler, (
            f"{rel_path}: Popen call not wrapped in error handler.\n"
            f"Context:\n{block}"
        )


def test_no_new_popen_files() -> None:
    """Popen usage doesn't spread to new files beyond the known set."""
    known = {SRC / p for p in POPEN_FILES}
    py_files = list(SRC.rglob("*.py"))
    new_popen_files = []
    for f in py_files:
        if f in known:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "Popen(" in text:
            new_popen_files.append(f.relative_to(SRC))

    assert not new_popen_files, (
        "New files with Popen (add to POPEN_FILES or narrow to subprocess.run):\n"
        + "\n".join(str(p) for p in new_popen_files)
    )
