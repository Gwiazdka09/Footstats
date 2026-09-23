"""Front na Vercelu ma mieć te same nagłówki bezpieczeństwa co kopia z Cloud Run.

ZNALEZISKO (audyt bezpieczeństwa 24.09.2026): cała praca nad nagłówkami (B5, 23.08)
siedziała w `api/main.py`, czyli obejmowała WYŁĄCZNIE kopię SPA serwowaną przez
Cloud Run. Użytkownicy wchodzą na `bot-opal-nu.vercel.app`, a stamtąd wracało
tylko `Strict-Transport-Security` — domyślny nagłówek Vercela. Zmierzone
`curl -sI`: zero CSP, zero `X-Frame-Options`, zero `X-Content-Type-Options`,
zero `Referrer-Policy`.

Skutek: produkcyjny front dawał się osadzić w cudzej ramce (clickjacking na
kreatorze kuponu i formularzu logowania), a przeglądarka zgadywała typy
zasobów. Ochrona wyglądała na wdrożoną, bo TEST na nią przechodził — tyle że
mierzył drugą, mniej używaną ścieżkę. Ten sam kształt co „zielone testy, martwa
produkcja".

DLACZEGO CSP TYLKO RAPORTUJE: front na Vercelu woła API na innej domenie
(`footstats-api-...run.app`), więc `connect-src 'self'` z wersji Cloud Run
zablokowałby każde żądanie i wygasił aplikację. Polityka dla Vercela musi tę
domenę dopuścić, a że nikt jeszcze nie zmierzył, co jeszcze front ładuje,
startuje w trybie raportującym — z adresem raportu, więc tym razem faktycznie
mierzy (patrz `test_csp_raportowanie.py`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]
VERCEL = KORZEN / "vercel.json"

# Adres API, do którego front faktycznie strzela — odczytany z produkcyjnego
# pakietu (`/assets/index-*.js` na Vercelu), nie zgadnięty.
API_PROD = "https://footstats-api-949240532526.europe-west1.run.app"

WYMAGANE = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def _naglowki() -> dict[str, str]:
    dane = json.loads(VERCEL.read_text(encoding="utf-8"))
    wpisy = dane.get("headers", [])
    assert wpisy, "vercel.json nie ma sekcji `headers` — front leci bez ochrony"
    plaskie: dict[str, str] = {}
    for wpis in wpisy:
        for h in wpis.get("headers", []):
            plaskie[h["key"]] = h["value"]
    return plaskie


@pytest.mark.parametrize("klucz,wartosc", sorted(WYMAGANE.items()))
def test_naglowek_obecny(klucz: str, wartosc: str) -> None:
    assert _naglowki().get(klucz) == wartosc


def test_csp_dopuszcza_api_bo_inaczej_aplikacja_umiera() -> None:
    """Front i API są na różnych domenach — bez tego wpisu CSP ubija logowanie."""
    csp = _naglowki().get("Content-Security-Policy-Report-Only", "")
    assert API_PROD in csp, "CSP nie dopuszcza domeny API — każde żądanie by padło"
    assert "connect-src" in csp


def test_csp_ma_gdzie_raportowac() -> None:
    """Tryb raportujący bez adresu raportu to dekoracja — lekcja z wersji API."""
    csp = _naglowki().get("Content-Security-Policy-Report-Only", "")
    assert f"report-uri {API_PROD}/api/csp-report" in csp


def test_csp_blokuje_ramki_i_obce_skrypty() -> None:
    csp = _naglowki().get("Content-Security-Policy-Report-Only", "")
    assert "frame-ancestors 'none'" in csp
    assert "script-src 'self'" in csp
    assert "object-src 'none'" in csp


def test_polityka_nie_jest_wymuszana_zanim_cokolwiek_zmierzymy() -> None:
    """Zabezpieczenie przed pochopnym zaciśnięciem: wymuszona CSP, która psuje
    front, daje białą stronę u wszystkich naraz. Najpierw raporty, potem decyzja
    właściciela projektu — i wtedy ten test się zmienia razem z nią.
    """
    assert "Content-Security-Policy" not in _naglowki(), (
        "CSP wymuszana na Vercelu — jeśli to świadoma decyzja po przejrzeniu "
        "raportów, zaktualizuj ten test razem z nią"
    )
