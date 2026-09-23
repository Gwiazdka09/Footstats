"""Bramka `/cron/*` ma mieszkać w JEDNYM miejscu.

STAN PRZED (audyt 24.09.2026): ten sam warunek stał w pięciu kopiach — cztery
w `routes/coupons.py`, jedna w `routes/status.py`. Wszystkie były poprawne, więc
to nie było znalezisko bezpieczeństwa, tylko UKŁAD, w którym znalezisko musi
kiedyś powstać:

    oczekiwany = os.getenv("CRON_SECRET", "")
    if not oczekiwany or not hmac.compare_digest(podany, oczekiwany):
        raise HTTPException(401)

Człon `not oczekiwany` jest tu krytyczny — `hmac.compare_digest("", "")` zwraca
True, więc deploy bez zmiennej otwierałby endpoint dla każdego, kto wyśle pusty
nagłówek. W tym projekcie poprawka rozsiana po kilku wejściach pominęła jedno
już trzy razy: `kupon_key` (21.09, piąte wejście wywróciło produkcję), wyłącznik
w jednym wejściu, `None.get` w czterech konsumentach. Bramka autoryzacji to
najgorsze możliwe miejsce na czwarty raz.

Ten test nie sprawdza, czy warunek jest poprawny — od tego jest
`test_cron_endpoints_auth.py`. Sprawdza, że jest JEDEN.
"""
from __future__ import annotations

import re
from pathlib import Path

KATALOG_API = Path(__file__).resolve().parents[1] / "src" / "footstats" / "api"
MODUL_BRAMKI = KATALOG_API / "cron_auth.py"


def _pliki_poza_bramka() -> list[Path]:
    return sorted(
        p for p in KATALOG_API.rglob("*.py")
        if "__pycache__" not in p.parts and p != MODUL_BRAMKI
    )


def test_modul_bramki_istnieje() -> None:
    assert MODUL_BRAMKI.exists(), (
        "brak `api/cron_auth.py` — bramka /cron/* ma mieć jedno źródło prawdy"
    )


def test_tylko_bramka_czyta_cron_secret() -> None:
    """`os.getenv("CRON_SECRET")` poza modułem bramki = nowa kopia reguły."""
    winne = {
        p.name: [nr for nr, linia in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if re.search(r"""CRON_SECRET["']\s*[,)]""", linia)]
        for p in _pliki_poza_bramka()
    }
    winne = {k: v for k, v in winne.items() if v}
    assert not winne, (
        f"CRON_SECRET czytany poza `cron_auth.py`: {winne}. "
        "Użyj wspólnej bramki — pięć kopii tego warunku to czekanie, aż jedna "
        "zostanie pominięta przy poprawce."
    )


def test_tylko_bramka_porownuje_sekret() -> None:
    winne = {
        p.name: [nr for nr, linia in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if "compare_digest" in linia and "cron" in p.read_text(encoding="utf-8").lower()]
        for p in _pliki_poza_bramka() if "routes" in p.parts
    }
    winne = {k: v for k, v in winne.items() if v}
    assert not winne, f"porównanie sekretu poza bramką: {winne}"


def test_bramka_odrzuca_pusty_sekret(monkeypatch) -> None:
    """Kontrola pozytywna na samej bramce — bez niej ten plik pilnowałby tylko
    kształtu kodu, a nie zachowania.

    Scenariusz: deploy bez `CRON_SECRET` w środowisku. `compare_digest("", "")`
    to True, więc naiwna wersja wpuszcza pusty nagłówek.
    """
    import pytest
    from fastapi import HTTPException
    from footstats.api.cron_auth import sprawdz_cron_secret

    monkeypatch.delenv("CRON_SECRET", raising=False)
    with pytest.raises(HTTPException) as exc:
        sprawdz_cron_secret("")
    assert exc.value.status_code == 401

    monkeypatch.setenv("CRON_SECRET", "prawidlowy")
    with pytest.raises(HTTPException):
        sprawdz_cron_secret("zly")
    sprawdz_cron_secret("prawidlowy")          # nie podnosi
