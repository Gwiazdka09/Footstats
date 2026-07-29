"""test_browser_fetch.py — pobieranie stron renderowanych JS (chromium w obrazie jobs).

Kontekst: Understat od ~2026 NIE embeduje już `matchesData`/`playersData` w HTML
(sprawdzone 2026-07-29: strona drużyny wraca 200, ale zmiennych nie ma) → cały
`fetch_team_xg` zwracał None, więc 20% blend xG w `poisson.predict_match` nigdy
się nie odpalał. FBref oddaje 403 nawet z normalnym User-Agentem (Cloudflare).

Oba źródła wymagają realnej przeglądarki. Obraz `footstats-jobs` już ma
`playwright install --with-deps chromium`, więc infrastruktura istnieje.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import footstats.scrapers.browser_fetch as bf


@contextmanager
def _fake_browser(**kwargs):
    """Podstawia browser_context z base_playwright (przyjmuje headless=...)."""
    yield MagicMock()


def _patchuj_przegladarke(page):
    @contextmanager
    def _page_ctx(_browser, **kwargs):
        yield page

    return (
        patch.object(bf, "PLAYWRIGHT_OK", True),
        patch.object(bf, "browser_context", _fake_browser),
        patch.object(bf, "page_context", _page_ctx),
    )


def _uruchom(fn, page):
    p1, p2, p3 = _patchuj_przegladarke(page)
    with p1, p2, p3:
        return fn()


# ── zmienne z window ────────────────────────────────────────────────────────


def test_odczytuje_zmienne_z_window():
    """Understat trzyma dane w window.matchesData po wyrenderowaniu."""
    page = MagicMock()
    page.evaluate.side_effect = lambda expr: (
        [{"xG": {"h": 1.5}}] if "matchesData" in expr else None
    )
    wynik = _uruchom(
        lambda: bf.pobierz_zmienne_js("https://understat.com/team/Arsenal/2025",
                                      ["matchesData", "playersData"]),
        page,
    )
    assert wynik["matchesData"] == [{"xG": {"h": 1.5}}]
    assert "playersData" not in wynik  # None nie trafia do wyniku


def test_brak_playwrighta_jest_graceful():
    """Obraz API nie ma chromium — brak przeglądarki nie może wywalić pipeline'u."""
    with patch.object(bf, "PLAYWRIGHT_OK", False):
        assert bf.pobierz_zmienne_js("https://x", ["a"]) == {}
        assert bf.pobierz_html("https://x") is None


def test_wyjatek_przegladarki_jest_graceful():
    page = MagicMock()
    page.goto.side_effect = RuntimeError("navigation failed")
    assert _uruchom(lambda: bf.pobierz_zmienne_js("https://x", ["a"]), page) == {}


def test_bledna_zmienna_nie_psuje_pozostalych():
    """Jedna zmienna rzuca w evaluate → reszta i tak wraca."""
    page = MagicMock()

    def _eval(expr):
        if "zla" in expr:
            raise RuntimeError("undefined")
        return {"ok": 1}

    page.evaluate.side_effect = _eval
    wynik = _uruchom(lambda: bf.pobierz_zmienne_js("https://x", ["zla", "dobra"]), page)
    assert wynik == {"dobra": {"ok": 1}}


# ── wyrenderowany HTML ──────────────────────────────────────────────────────


def test_pobiera_wyrenderowany_html():
    page = MagicMock()
    page.content.return_value = "<html>xG 1.23</html>"
    assert _uruchom(lambda: bf.pobierz_html("https://fbref.com/x"), page) == "<html>xG 1.23</html>"


def test_html_czeka_na_selektor_gdy_podany():
    """FBref dorenderowuje tabele — bez czekania złapalibyśmy pusty szkielet."""
    page = MagicMock()
    page.content.return_value = "<html>ok</html>"
    _uruchom(lambda: bf.pobierz_html("https://fbref.com/x", czekaj_na="#stats_squads"), page)
    page.wait_for_selector.assert_called_once()
    assert page.wait_for_selector.call_args[0][0] == "#stats_squads"


def test_brak_selektora_nie_zwraca_none_tylko_html():
    """Timeout na selektorze nie może skasować treści, która i tak przyszła."""
    page = MagicMock()
    page.wait_for_selector.side_effect = RuntimeError("timeout")
    page.content.return_value = "<html>czesciowe</html>"
    assert _uruchom(
        lambda: bf.pobierz_html("https://x", czekaj_na="#nieistnieje"), page
    ) == "<html>czesciowe</html>"
