"""Reset przycisku musi zostać w `@layer base` — inaczej wraca bug app-wide.

STAN ZASTANY (do 17.08.2026): `button { color: inherit; background: transparent }`
stał POZA warstwami. W Tailwindzie v4 utility siedzą w `@layer utilities`,
a reguła spoza warstw bije KAŻDĄ regułę z warstwy — niezależnie od specyficzności.
Skutek: `text-*` i `bg-*` nie stosowały się do żadnego przycisku w aplikacji.

Zmierzone w przeglądarce PRZED poprawką (Playwright, styl wyliczony):
    <button class="text-rose-400">   → rgb(248,250,252)   (zignorowane)
    <button class="bg-emerald-500">  → rgba(0,0,0,0)      (zignorowane)
    <span   class="text-rose-400">   → oklch(0.712 …)     (działa)

Najbardziej bolało tam, gdzie nikt nie zauważył: przycisk rejestracji
(`bg-indigo-500`) był PRZEZROCZYSTY, a przycisk usunięcia konta (`bg-rose-500`)
nie miał czerwieni ostrzegawczej.

Ten test pilnuje samej struktury pliku, bo pełny dowód wymaga przeglądarki,
a ta nie chodzi w CI. Tanio i wystarczy, żeby regresja nie przeszła po cichu.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parents[1] / "src" / "footstats" / "gui" / "src" / "index.css"


def _tresc() -> str:
    return CSS.read_text(encoding="utf-8")


def _w_warstwie(tekst: str, pozycja: int) -> bool:
    """Czy dana pozycja leży wewnątrz bloku `@layer ... { ... }`."""
    przed = tekst[:pozycja]
    ostatnia = przed.rfind("@layer")
    if ostatnia < 0:
        return False
    fragment = przed[ostatnia:]
    return fragment.count("{") - fragment.count("}") > 0


def test_plik_css_istnieje():
    assert CSS.exists(), f"brak {CSS} — test nic nie sprawdza"


def test_reset_przycisku_jest_w_layer_base():
    tekst = _tresc()
    dopasowania = [m for m in re.finditer(r"(?m)^\s*button\s*\{", tekst)]
    assert dopasowania, "nie znaleziono resetu `button {` — zmienil sie ksztalt pliku"
    for m in dopasowania:
        assert _w_warstwie(tekst, m.start()), (
            "reset `button {` stoi POZA @layer — w Tailwind v4 bije wszystkie"
            " klasy text-*/bg-* na przyciskach w calej aplikacji"
        )


def test_reset_dalej_robi_swoje():
    """Przeniesienie do warstwy nie może zgubić samego resetu."""
    tekst = _tresc()
    m = re.search(r"(?m)^\s*button\s*\{[^}]*\}", tekst)
    assert m
    blok = m.group()
    for wlasciwosc in ("background", "border", "font", "color", "cursor"):
        assert wlasciwosc in blok, f"reset zgubil `{wlasciwosc}`"


@pytest.mark.parametrize("selektor", ["\\.btn-primary", "\\.btn-see-all"])
def test_wlasne_klasy_przyciskow_zostaja_poza_warstwami(selektor):
    """`.btn-primary` MA wygrywać z utility — to celowe, nie przeoczenie.

    Gdyby ktoś „dla porządku" wciągnął je do `@layer base`, gradient akcentu
    przegrałby z pierwszą lepszą klasą `bg-*` i przyciski główne straciłyby wygląd.
    """
    tekst = _tresc()
    m = re.search(rf"(?m)^\s*{selektor}\s*\{{", tekst)
    if not m:
        pytest.skip(f"brak klasy {selektor} w index.css")
    assert not _w_warstwie(tekst, m.start()), (
        f"{selektor} trafilo do @layer — przegra teraz z klasami utility"
    )
