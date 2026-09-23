"""Każda akcja w workflow ma być przypięta do SHA, nie do ruchomego taga.

PO CO: tag `@v3` wskazuje na commit, który właściciel akcji może przestawić
w dowolnej chwili — przejęte repo akcji albo retarget taga wykonuje NIEPRZEJRZANY
kod w naszych jobach. W `cd.yml` i `cd-jobs.yml` ten kod biegnie z uprawnieniem
`id-token: write`, czyli może wziąć tożsamość GCP przez Workload Identity
Federation i wdrożyć cokolwiek na produkcję. `backup.yml` był przypięty do SHA
od początku — reszta plików nie, i sygnał z przeglądu PR #25 (23.09.2026) to
wypunktował przy okazji bumpów dependabota.

DLACZEGO TEST, A NIE UWAŻNOŚĆ: to jest dokładnie ten kształt błędu, który w tym
projekcie wraca — jedna reguła w kilku wejściach (`feedback_wylacznik_w_jednym_wejsciu`).
Plików workflow jest sześć i każdy nowy job dokłada kolejne `uses:`. Test WYLICZA
wejścia z plików, więc nowy plik workflow też trafia pod regułę bez ruszania testu.

JAK ODCZYTAĆ PORAŻKĘ: komunikat podaje plik, linię i akcję. Napraw tak:
`uses: właściciel/akcja@<pełny 40-znakowy SHA> # v1.2.3` — komentarz z wersją jest
obowiązkowy, bo bez niego nikt nie wie, co ten SHA znaczy, a dependabot i tak
umie aktualizować pinowane SHA-e.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KATALOG = Path(__file__).resolve().parents[1] / ".github" / "workflows"

# `uses: x` z ewentualnym `- ` przed; wartość bierzemy do spacji lub komentarza.
_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)\s*(#.*)?$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _wejscia() -> list[tuple[Path, int, str, str]]:
    """(plik, numer linii, referencja akcji, komentarz) — wyliczone z plików."""
    out: list[tuple[Path, int, str, str]] = []
    for plik in sorted(KATALOG.glob("*.yml")) + sorted(KATALOG.glob("*.yaml")):
        for nr, linia in enumerate(plik.read_text(encoding="utf-8").splitlines(), 1):
            trafienie = _USES.match(linia)
            if trafienie:
                out.append((plik, nr, trafienie.group(1), trafienie.group(2) or ""))
    return out


def test_sa_jakies_workflow_do_sprawdzenia() -> None:
    """Bez tego cała reszta przechodziłaby na pustej liście."""
    wejscia = _wejscia()
    assert len(wejscia) >= 10, (
        f"znaleziono tylko {len(wejscia)} wpisów `uses:` w {KATALOG} — "
        "regexp przestał łapać albo katalog się przeniósł"
    )


@pytest.mark.parametrize("plik,nr,ref,komentarz", _wejscia(),
                         ids=lambda w: str(w) if not isinstance(w, Path) else w.name)
def test_akcja_przypieta_do_sha(plik: Path, nr: int, ref: str, komentarz: str) -> None:
    # Akcja lokalna (`./.github/actions/...`) i obraz dockera nie mają taga do przestawienia.
    if ref.startswith("./") or ref.startswith("docker://"):
        return

    assert "@" in ref, f"{plik.name}:{nr} — `uses: {ref}` bez wersji w ogóle"
    _, wersja = ref.rsplit("@", 1)

    assert _SHA.match(wersja), (
        f"{plik.name}:{nr} — akcja `{ref}` przypięta do RUCHOMEGO taga. "
        "Retarget taga u właściciela akcji wykonuje nieprzejrzany kod w naszym jobie, "
        "a w cd.yml/cd-jobs.yml ten kod ma `id-token: write` i dostęp do tożsamości GCP. "
        "Przypnij do pełnego SHA i dopisz wersję w komentarzu."
    )
    assert komentarz.strip().startswith("#") and len(komentarz.strip()) > 1, (
        f"{plik.name}:{nr} — SHA bez komentarza z wersją. Sam SHA nikomu nic nie mówi; "
        "zapisz `# vX.Y.Z`, żeby dało się ocenić, jak stara jest ta akcja."
    )
