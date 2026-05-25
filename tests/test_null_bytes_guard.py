"""test_null_bytes_guard.py — Verify no null bytes in critical modules."""

import subprocess
from pathlib import Path


def test_no_null_bytes_in_core_modules():
    """Check that core .py files have no embedded null bytes."""
    root = Path(__file__).parent.parent / "src" / "footstats"
    critical_modules = [
        "ai/analyzer.py",
        "core/async_utils.py",
        "core/response_cache.py",
    ]

    for module in critical_modules:
        fpath = root / module
        assert fpath.exists(), f"Module {module} not found"

        with open(fpath, "rb") as f:
            content = f.read()

        assert b"\x00" not in content, f"Null bytes found in {module}"


def test_python_syntax_valid():
    """Run python -m py_compile on core modules."""
    root = Path(__file__).parent.parent / "src" / "footstats"

    for pyfile in root.rglob("*.py"):
        if "__pycache__" in str(pyfile):
            continue

        result = subprocess.run(
            ["python", "-m", "py_compile", str(pyfile)],
            capture_output=True,
            timeout=5
        )
        assert result.returncode == 0, f"Syntax error in {pyfile}: {result.stderr.decode()}"
