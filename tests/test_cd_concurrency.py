"""Wdrożenia nie mogą iść równolegle — `concurrency` w obu workflow CD.

19.10 trzy merge'e w ciągu minuty odpaliły trzy RÓWNOLEGŁE wdrożenia API na
Cloud Run. Rewizją produkcyjną zostaje ten deploy, który skończy się OSTATNI,
a nie ten z najnowszego commita — produkcja może cicho zostać na starszym kodzie.

Lekarstwo to blok `concurrency` z grupą i `cancel-in-progress: false`:
  * jedna grupa na workflow → wdrożenia idą po kolei,
  * bez anulowania trwającego biegu → nie zostaje półwdrożony serwis.

Grupy API i jobów muszą być RÓŻNE — mogą iść równolegle względem siebie.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

KATALOG_WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows"
WORKFLOW_CD = ("cd.yml", "cd-jobs.yml")


def _wczytaj_workflow(nazwa: str) -> dict[str, Any]:
    """Parsuje plik workflow; PyYAML zamienia klucz `on` na `True`, więc go nie czytamy."""
    tekst = (KATALOG_WORKFLOW / nazwa).read_text(encoding="utf-8")
    dane = yaml.safe_load(tekst)
    assert isinstance(dane, dict), f"{nazwa}: plik YAML nie jest mapą na poziomie głównym"
    return dane


def test_cd_api_ma_blok_concurrency_bez_anulowania() -> None:
    """Wdrożenie API ma grupę i NIE anuluje trwającego biegu."""
    # Arrange
    dane = _wczytaj_workflow("cd.yml")

    # Act
    concurrency = dane.get("concurrency")

    # Assert
    assert isinstance(concurrency, dict), (
        "cd.yml: brak bloku `concurrency` na poziomie workflow — "
        "równoległe wdrożenia API mogą zostawić starszą rewizję"
    )
    assert concurrency.get("group"), "cd.yml: `concurrency.group` jest pusta"
    assert concurrency.get("cancel-in-progress") is False, (
        "cd.yml: `cancel-in-progress` musi być False — przerwany deploy "
        "zostawia półwdrożony serwis"
    )


def test_cd_jobs_ma_blok_concurrency_bez_anulowania() -> None:
    """Wdrożenie jobów też idzie po kolei i nie anuluje trwającego biegu."""
    # Arrange
    dane = _wczytaj_workflow("cd-jobs.yml")

    # Act
    concurrency = dane.get("concurrency")

    # Assert
    assert isinstance(concurrency, dict), (
        "cd-jobs.yml: brak bloku `concurrency` na poziomie workflow"
    )
    assert concurrency.get("group"), "cd-jobs.yml: `concurrency.group` jest pusta"
    assert concurrency.get("cancel-in-progress") is False, (
        "cd-jobs.yml: `cancel-in-progress` musi być False"
    )


def test_grupy_api_i_jobow_sa_rozne() -> None:
    """API i joby mają osobne grupy — nie blokują się nawzajem."""
    # Arrange
    grupy = {
        nazwa: _wczytaj_workflow(nazwa)["concurrency"]["group"]
        for nazwa in WORKFLOW_CD
    }

    # Act
    unikalne = set(grupy.values())

    # Assert
    assert len(unikalne) == len(WORKFLOW_CD), (
        f"Grupy concurrency CD się powtarzają: {grupy} — "
        "API i joby muszą mieć różne grupy"
    )
