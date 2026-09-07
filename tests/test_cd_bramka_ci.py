"""CD nie moze wdrazac commita, ktorego CI nie przepuscilo.

STAN ZASTANY (2026-09-07). `ci.yml`, `cd.yml` i `cd-jobs.yml` to trzy osobne
workflow na tym samym triggerze `push: branches: [main]`. Zaden z CD nie mial
`needs:` ani `workflow_run` — bo GitHub Actions **nie ma jak** wyrazic `needs:`
miedzy workflow. Skutek: czerwona suita wdrazala sie dokladnie tak samo jak
zielona, a jedyna kontrola przed podmiana obrazu jobow byl smoke-import
(`test_cd_joby.py`), ktory lapie blad importu, nie blad logiki.

Ten projekt zaplacil juz za wdrozenie zlego artefaktu: 30.07-02.08 pipeline stal
TRZY DNI na uszkodzonym obrazie przy `exit=0`. Tamta dziura byla w procesie
recznym i zostala zalatana przez CD; ta jest w samym CD.

Bramka pyta `gh run list` o wynik workflow "CI" dla TEGO SHA i czeka, az bedzie
znany. `workflow_dispatch` ja omija swiadomie — reczne wdrozenie to furtka
awaryjna (rollback), a dla recznego przebiegu przebiegu CI moze w ogole nie byc.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

KORZEN = Path(__file__).resolve().parents[1]
WORKFLOWY = KORZEN / ".github" / "workflows"
CD = ("cd.yml", "cd-jobs.yml")


def _pierwszy_job(nazwa_pliku: str) -> dict:
    dane = yaml.safe_load((WORKFLOWY / nazwa_pliku).read_text(encoding="utf-8"))
    return dane["jobs"][next(iter(dane["jobs"]))]


def _bramka(nazwa_pliku: str) -> dict | None:
    for krok in _pierwszy_job(nazwa_pliku)["steps"]:
        if "Bramka" in str(krok.get("name", "")):
            return krok
    return None


@pytest.mark.parametrize("plik", CD)
def test_workflow_ma_bramke(plik):
    assert _bramka(plik) is not None, (
        f"{plik} wdraza bez sprawdzenia CI — czerwona suita pojedzie na produkcje")


@pytest.mark.parametrize("plik", CD)
def test_bramka_stoi_przed_wdrozeniem(plik):
    """Bramka po buildzie albo po deployu nie jest bramka."""
    kroki = _pierwszy_job(plik)["steps"]
    idx_bramki = next(i for i, k in enumerate(kroki) if "Bramka" in str(k.get("name", "")))
    podejrzane = [
        i for i, k in enumerate(kroki)
        if any(s in (str(k.get("name", "")) + str(k.get("uses", "")) + str(k.get("run", "")))
               for s in ("deploy-cloudrun", "build-push-action", "jobs update", "gcloud run"))
    ]
    assert podejrzane, f"{plik}: nie znalazlem kroku wdrozeniowego — test stracil sens"
    assert idx_bramki < min(podejrzane), (
        f"{plik}: bramka jest krokiem {idx_bramki}, a wdrozenie zaczyna sie na {min(podejrzane)}")


@pytest.mark.parametrize("plik", CD)
def test_bramka_pyta_o_ten_sam_commit(plik):
    """Zielone CI innego commita nic nie znaczy dla tego artefaktu."""
    tresc = _bramka(plik)["run"]
    assert "--commit" in tresc and "GITHUB_SHA" in tresc, (
        f"{plik}: bramka nie wiaze wyniku CI z konkretnym SHA")
    assert "--workflow CI" in tresc


@pytest.mark.parametrize("plik", CD)
def test_bramka_przewraca_sie_na_czerwonym_i_na_ciszy(plik):
    """Trzy stany musza konczyc sie bledem: czerwone CI, brak CI, przekroczony czas.

    Bramka, ktora przy braku odpowiedzi przepuszcza, jest gorsza niz jej brak:
    wyglada na kontrole i nia nie jest.
    """
    tresc = _bramka(plik)["run"]
    assert tresc.count("exit 1") >= 2, f"{plik}: bramka ma za malo sciezek odmowy"
    assert "exit 0" in tresc, f"{plik}: bramka nigdy nie przepuszcza"
    assert "::error::" in tresc, f"{plik}: odmowa bez adnotacji bledu w logu Actions"


@pytest.mark.parametrize("plik", CD)
def test_reczne_wdrozenie_omija_bramke_swiadomie(plik):
    """Furtka awaryjna ma byc JAWNA i zawezona do `workflow_dispatch`."""
    warunek = str(_bramka(plik).get("if", ""))
    assert "workflow_dispatch" in warunek, (
        f"{plik}: bramka bez furtki na reczne wdrozenie — rollback bylby zablokowany")
    assert "push" not in warunek, (
        f"{plik}: furtka obejmuje pushe, czyli sciezke, ktora ma byc pilnowana")


@pytest.mark.parametrize("plik", CD)
def test_bramka_ma_skonczony_czas_oczekiwania(plik):
    """Bez limitu zawieszone CI trzymaloby runnera do timeoutu GitHuba (6 h)."""
    tresc = _bramka(plik)["run"]
    assert "seq 1" in tresc and "sleep" in tresc
