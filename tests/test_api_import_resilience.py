"""Import api.main musi przeżyć martwą DB (incydent: Neon quota-block 18-20.07).

Init DB w main.py jest best-effort (try/except) — brak bazy przy imporcie
nie może wywalać kolekcji pytest ani startu kontenera.
"""
import os
import subprocess
import sys


def test_api_import_survives_dead_db():
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:9/db?connect_timeout=1",
    }
    r = subprocess.run(
        [sys.executable, "-c", "import footstats.api.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
