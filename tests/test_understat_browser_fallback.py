"""test_understat_browser_fallback.py — xG ratowane przeglądarką gdy HTML jest pusty.

Stan sprawdzony 2026-07-29: `https://understat.com/team/Arsenal/2025` wraca HTTP 200
i ~18KB, ale NIE zawiera `matchesData` ani `playersData` — JS je wstrzykuje.
Skutek przed fixem: `fetch_team_xg` zwracał None dla każdej drużyny, cache xG był
pusty, a 20% blend xG w `poisson.predict_match` był cichym no-opem.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import footstats.scrapers.understat_xg as ux

_SHELL_HTML = "<html><body>brak danych, wszystko renderuje JS</body></html>"

_MATCHES = [
    {
        "isResult": True,
        "datetime": "2026-07-20 18:00:00",
        "h": {"title": "Arsenal"},
        "a": {"title": "Chelsea"},
        "xG": {"h": "2.10", "a": "0.80"},
        "goals": {"h": "2", "a": "1"},
    },
]

_PLAYERS = [
    {"player_name": "Bukayo Saka", "team_title": "Arsenal",
     "goals": "12", "assists": "7", "time": "1800", "xG": "10.4"},
]


def _resp(status=200, text=_SHELL_HTML):
    r = MagicMock(status_code=status)
    r.text = text
    return r


# ── xG drużyny ──────────────────────────────────────────────────────────────


def test_pusty_html_schodzi_na_przegladarke(tmp_path):
    """Brak matchesData w HTML → odczyt window.matchesData."""
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch.object(
        ux, "time", MagicMock()
    ), patch.object(
        ux._SESSION, "get", return_value=_resp()
    ), patch(
        "footstats.scrapers.browser_fetch.pobierz_zmienne_js",
        return_value={"matchesData": _MATCHES},
    ) as mock_bf:
        wynik = ux.fetch_team_xg("Arsenal", season=2025)

    mock_bf.assert_called_once()
    assert wynik is not None
    assert wynik["xg_for_avg"] == 2.1
    assert wynik["xga_avg"] == 0.8


def test_html_z_danymi_nie_odpala_przegladarki(tmp_path):
    """Gdy plain-HTTP wystarczy, nie płacimy za uruchomienie chromium."""
    html = (
        "var matchesData = JSON.parse('"
        + '[{"isResult":true,"datetime":"2026-07-20 18:00:00",'
        '"h":{"title":"Arsenal"},"a":{"title":"Chelsea"},'
        '"xG":{"h":"1.50","a":"1.00"},"goals":{"h":"1","a":"1"}}]'
        + "')"
    )
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch.object(
        ux, "time", MagicMock()
    ), patch.object(
        ux._SESSION, "get", return_value=_resp(text=html)
    ), patch(
        "footstats.scrapers.browser_fetch.pobierz_zmienne_js"
    ) as mock_bf:
        wynik = ux.fetch_team_xg("Arsenal", season=2025)

    mock_bf.assert_not_called()
    assert wynik is not None and wynik["xg_for_avg"] == 1.5


def test_przegladarka_tez_pusta_zwraca_none(tmp_path):
    """Brak danych z obu ścieżek → None, nie wymyślone zero."""
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch.object(
        ux, "time", MagicMock()
    ), patch.object(
        ux._SESSION, "get", return_value=_resp()
    ), patch(
        "footstats.scrapers.browser_fetch.pobierz_zmienne_js", return_value={}
    ):
        assert ux.fetch_team_xg("Arsenal", season=2025) is None


def test_blad_http_tez_probuje_przegladarki(tmp_path):
    """403/timeout na plain-HTTP nie kończy sprawy — przeglądarka bywa przepuszczana."""
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch.object(
        ux, "time", MagicMock()
    ), patch.object(
        ux._SESSION, "get", return_value=_resp(status=403, text="")
    ), patch(
        "footstats.scrapers.browser_fetch.pobierz_zmienne_js",
        return_value={"matchesData": _MATCHES},
    ) as mock_bf:
        wynik = ux.fetch_team_xg("Arsenal", season=2025)

    mock_bf.assert_called_once()
    assert wynik is not None


# ── skład ligi (goal_share) ─────────────────────────────────────────────────


def test_gracze_ligi_schodza_na_przegladarke():
    with patch.object(ux, "time", MagicMock()), patch.object(
        ux._SESSION, "get", return_value=_resp()
    ), patch(
        "footstats.scrapers.browser_fetch.pobierz_zmienne_js",
        return_value={"playersData": _PLAYERS},
    ):
        gracze = ux.fetch_league_players_understat("EPL", 2025)

    assert len(gracze) == 1
    assert gracze[0]["name"] == "Bukayo Saka"
    assert gracze[0]["goals"] == 12
    assert gracze[0]["xg"] == 10.4


def test_gracze_brak_wszedzie_to_pusta_lista():
    with patch.object(ux, "time", MagicMock()), patch.object(
        ux._SESSION, "get", return_value=_resp()
    ), patch(
        "footstats.scrapers.browser_fetch.pobierz_zmienne_js", return_value={}
    ):
        assert ux.fetch_league_players_understat("EPL", 2025) == []
