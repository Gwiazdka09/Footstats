"""Odpowiedź 500 nie ma prawa nieść treści wyjątku.

ZNALEZISKO (audyt bezpieczeństwa 24.09.2026): 17 miejsc w `api/routes` robiło
`raise HTTPException(status_code=500, detail=str(e))`. Wyjątek pochodzi tam
z psycopg2, a jego `str()` to gotowy opis wnętrza bazy — nazwa relacji i
kolumny, fragment zapytania z pozycją błędu, czasem wartość, która go wywołała:

    relation "coupons" does not exist
    LINE 1: SELECT user_id, stake_pln FROM coupons WHERE id = 42

Dla atakującego to darmowy zwiad (OWASP API8): mapa schematu bez jednego
udanego wstrzyknięcia i potwierdzenie, które parametry docierają do SQL-a.
Reguła projektu mówi wprost: „Error messages don't leak sensitive data".

CZEGO TEN TEST NIE ROBI: nie zabrania `detail` w ogóle. Komunikaty pisane przez
nas — „Kupon nie istnieje", „Brak uprawnień do tego kuponu" — są celowe i
potrzebne. Zakaz dotyczy WSTAWIANIA OBIEKTU WYJĄTKU w odpowiedź.

DLACZEGO TEST, A NIE PRZEGLĄD: to jedna reguła w kilkunastu wejściach w trzech
plikach, a każdy nowy endpoint dokłada kolejne. Test WYLICZA wystąpienia
z kodu, więc nowy `except` trafia pod regułę bez ruszania testu — ten sam
wzorzec, który uratował przypinanie akcji do SHA.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KATALOG_API = Path(__file__).resolve().parents[1] / "src" / "footstats" / "api"

# `detail=str(e)`, `detail=f"... {e}"`, `detail=repr(e)`, `detail=str(exc)` —
# wszystkie postaci wstawienia wyjątku do odpowiedzi.
_WYCIEK = re.compile(
    r"detail\s*=\s*(?:str|repr)\(\s*(?:e|exc|err|error|ex)\s*\)"
    r"|detail\s*=\s*f[\"'][^\"']*\{\s*(?:e|exc|err|error|ex)[\s!:}]"
)


def _pliki() -> list[Path]:
    return sorted(p for p in KATALOG_API.rglob("*.py") if "__pycache__" not in p.parts)


def test_sa_pliki_do_sprawdzenia() -> None:
    """Pusta lista przepuściłaby wszystko po cichu."""
    assert len(_pliki()) >= 5, f"tylko {len(_pliki())} plików w {KATALOG_API}"


@pytest.mark.parametrize("plik", _pliki(), ids=lambda p: p.name)
def test_odpowiedz_nie_niesie_tresci_wyjatku(plik: Path) -> None:
    trafienia = [
        (nr, linia.strip())
        for nr, linia in enumerate(plik.read_text(encoding="utf-8").splitlines(), 1)
        if _WYCIEK.search(linia)
    ]
    assert not trafienia, (
        f"{plik.name}: treść wyjątku trafia do klienta w liniach "
        f"{[nr for nr, _ in trafienia]}. psycopg2 opisuje w niej schemat bazy i "
        "fragment zapytania. Zaloguj wyjątek (`_log.error(..., exc_info=True)`) "
        "i oddaj klientowi komunikat bez szczegółów."
    )


def test_regexp_lapie_znany_ksztalt() -> None:
    """Kontrola pozytywna — bez niej zielony wynik nie znaczyłby nic.

    Test na strażniku, bo strażnik oparty o regexp już raz w tym projekcie
    przepuścił piątą kopię tej samej pomyłki (`kupon_key`, 21.09).
    """
    assert _WYCIEK.search('raise HTTPException(status_code=500, detail=str(e))')
    assert _WYCIEK.search('raise HTTPException(500, detail=f"blad: {e}")')
    assert _WYCIEK.search('raise HTTPException(500, detail=repr(exc))')
    # A tego łapać NIE MA prawa — to nasz własny komunikat.
    assert not _WYCIEK.search('raise HTTPException(404, detail="Kupon nie istnieje")')
    assert not _WYCIEK.search('raise HTTPException(400, detail=f"Nieznany sort {sort}")')
