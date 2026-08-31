"""Hook `guard_live_ops` — blokada lokalnego odpalenia LIVE pipeline'u.

Hook nie mial ZADNEGO testu, mimo ze jest bramka przed podwojnymi kuponami
na Telegramie i zapisem do prod DB.

Znalezione 31.08 przy probie odpalenia fazy final lokalnie: furtka opisana
w komunikacie bledu ("dodaj FOOTSTATS_ALLOW_LIVE=1 przed komenda") NIE
DZIALALA. Hook czytal `os.environ` WLASNEGO procesu, a prefiks `VAR=1 cmd`
zyje wylacznie w powloce uruchamianej pozniej — do hooka nie docieral.

Skutek: komunikat obiecywal wyjscie, ktorego nie bylo. Kto go posluchal,
dostawal te sama blokade drugi raz i nie mial zadnej sciezki dalej.
To nie jest luzowanie reguly — to dociagniecie kodu do jego wlasnej umowy.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "guard_live_ops.py"

BLOKADA = 2
PRZEPUSC = 0


def _odpal(command: str, env_extra: dict | None = None) -> int:
    """Uruchamia hook tak, jak robi to Claude Code: payload JSON na stdin."""
    import os

    srodowisko = dict(os.environ)
    srodowisko.pop("FOOTSTATS_ALLOW_LIVE", None)
    srodowisko.update(env_extra or {})

    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True, text=True, env=srodowisko, timeout=30,
    )
    return proc.returncode


# ── co ma byc blokowane ─────────────────────────────────────────────────────

@pytest.mark.parametrize("komenda", [
    "python -m footstats.daily_agent --faza final",
    "python -m footstats.daily_agent --faza=final --dry-run",
    "python src/footstats/daily_agent.py --faza final",
    "python -m footstats.evening_agent",
])
def test_live_pipeline_jest_blokowany(komenda):
    assert _odpal(komenda) == BLOKADA


# ── co ma przechodzic ───────────────────────────────────────────────────────

@pytest.mark.parametrize("komenda", [
    "python -m footstats.daily_agent --faza draft",
    "pytest tests/test_evening_agent.py -v",
    "git status",
])
def test_bezpieczne_komendy_przechodza(komenda):
    assert _odpal(komenda) == PRZEPUSC


# ── furtka ──────────────────────────────────────────────────────────────────

def test_furtka_dziala_jako_prefiks_komendy():
    """Dokladnie ta forma, ktora podaje komunikat bledu."""
    assert _odpal(
        "FOOTSTATS_ALLOW_LIVE=1 python -m footstats.daily_agent --faza final"
    ) == PRZEPUSC


def test_furtka_dziala_ze_srodowiska_procesu():
    """Stara sciezka zostaje — kto ma zmienna w profilu, ma dzialac dalej."""
    assert _odpal(
        "python -m footstats.daily_agent --faza final",
        env_extra={"FOOTSTATS_ALLOW_LIVE": "1"},
    ) == PRZEPUSC


def test_furtka_z_innymi_zmiennymi_obok():
    assert _odpal(
        "FOOTSTATS_ALLOW_LIVE=1 DATABASE_URL='' python -m footstats.daily_agent --faza final"
    ) == PRZEPUSC


def test_inna_wartosc_NIE_otwiera_furtki():
    """Tylko `=1`. Inaczej literowka albo `=0` cicho zdejmowalyby blokade."""
    assert _odpal(
        "FOOTSTATS_ALLOW_LIVE=0 python -m footstats.daily_agent --faza final"
    ) == BLOKADA


def test_wzmianka_w_tekscie_NIE_otwiera_furtki():
    """Nazwa zmiennej w echo/komentarzu to nie jest swiadomy override."""
    assert _odpal(
        "echo 'ustaw MOJE_FOOTSTATS_ALLOW_LIVE=1 potem' && "
        "python -m footstats.daily_agent --faza final"
    ) == BLOKADA


# ── odpornosc ───────────────────────────────────────────────────────────────

def test_niepoprawny_payload_nie_blokuje():
    """Fail-open: hook, ktory nie umie sparsowac wejscia, nie ma prawa
    zatrzymywac calej pracy falszywym alarmem."""
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input="to nie jest json",
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == PRZEPUSC
