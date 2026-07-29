"""test_understat_liga_xg.py — xG całej ligi jednym pobraniem.

Understat przestał wystawiać dane jako zmienne JS (`matchesData`/`playersData`
nie ma ani w HTML, ani w `window` — sprawdzone 2026-07-29). Dane siedzą teraz
w tabelach DOM budowanych przez JS. Tabela ligi zawiera komplet: drużyna, M, xG, xGA
dla wszystkich zespołów — jedno pobranie zamiast osobnego per drużyna.
"""
from __future__ import annotations

from unittest.mock import patch

import footstats.scrapers.understat_xg as ux

# Fragment realnej tabeli ligi. Kolumny xG/xGA niosą deltę vs gole ("77.49+6.49").
_HTML_LIGA = """
<html><body>
<table>
  <tr><th>№</th><th>Team</th><th>M</th><th>W</th><th>D</th><th>L</th>
      <th>G</th><th>GA</th><th>PTS</th><th>xG</th><th>xGA</th><th>xPTS</th></tr>
  <tr><td>1</td><td>Arsenal</td><td>38</td><td>26</td><td>7</td><td>5</td>
      <td>71</td><td>27</td><td>85</td><td>77.49+6.49</td><td>33.13+6.13</td><td>79.87-5.13</td></tr>
  <tr><td>2</td><td>Manchester City</td><td>38</td><td>23</td><td>9</td><td>6</td>
      <td>77</td><td>35</td><td>78</td><td>79.36+2.36</td><td>46.49+11.49</td><td>73.95-4.05</td></tr>
</table>
</body></html>
"""


def test_parsuje_liczbe_z_delta():
    """'77.49+6.49' to xG 77.49, a nie 77.49+6.49 ani 6.49."""
    assert ux._parsuj_liczbe("77.49+6.49") == 77.49
    assert ux._parsuj_liczbe("33.13-6.13") == 33.13
    assert ux._parsuj_liczbe("38") == 38.0
    assert ux._parsuj_liczbe("") is None
    assert ux._parsuj_liczbe("brak") is None


def test_liczy_srednie_na_mecz(tmp_path):
    """Model czyta xg_for_avg/xga_avg — sumy sezonowe trzeba podzielić przez M."""
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch(
        "footstats.scrapers.browser_fetch.pobierz_html", return_value=_HTML_LIGA
    ):
        wynik = ux.fetch_league_team_xg("EPL", 2025)

    assert set(wynik) == {"Arsenal", "Manchester City"}
    ars = wynik["Arsenal"]
    assert ars["mecze"] == 38
    assert ars["xg_for_avg"] == round(77.49 / 38, 2)
    assert ars["xga_avg"] == round(33.13 / 38, 2)


def test_zapisuje_do_cache_czytanego_przez_model(tmp_path):
    """poisson.predict_match czyta _cache_get(_to_slug(team), season) — musi trafić."""
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch(
        "footstats.scrapers.browser_fetch.pobierz_html", return_value=_HTML_LIGA
    ):
        ux.fetch_league_team_xg("EPL", 2025)

    with patch.object(ux, "_CACHE_DIR", tmp_path):
        z_cache = ux._cache_get(ux._to_slug("Manchester City"), 2025)

    assert z_cache is not None
    assert z_cache["xg_for_avg"] == round(79.36 / 38, 2)


def test_jedno_pobranie_na_lige(tmp_path):
    """Sedno zmiany: 20 drużyn = 1 uruchomienie przeglądarki, nie 20."""
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch(
        "footstats.scrapers.browser_fetch.pobierz_html", return_value=_HTML_LIGA
    ) as mock_fetch:
        ux.fetch_league_team_xg("EPL", 2025)
    assert mock_fetch.call_count == 1


def test_pomija_druzyny_bez_kompletu_danych(tmp_path):
    """Wiersz bez M albo bez xG jest bezużyteczny — pomijamy, nie zgadujemy."""
    html = _HTML_LIGA.replace("<td>38</td><td>26</td>", "<td></td><td>26</td>")
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch(
        "footstats.scrapers.browser_fetch.pobierz_html", return_value=html
    ):
        wynik = ux.fetch_league_team_xg("EPL", 2025)
    assert "Arsenal" not in wynik
    assert "Manchester City" in wynik


def test_zero_meczow_nie_dzieli_przez_zero(tmp_path):
    html = _HTML_LIGA.replace("<td>38</td><td>26</td>", "<td>0</td><td>26</td>")
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch(
        "footstats.scrapers.browser_fetch.pobierz_html", return_value=html
    ):
        assert "Arsenal" not in ux.fetch_league_team_xg("EPL", 2025)


def test_brak_przegladarki_jest_graceful(tmp_path):
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch(
        "footstats.scrapers.browser_fetch.pobierz_html", return_value=None
    ):
        assert ux.fetch_league_team_xg("EPL", 2025) == {}


def test_smieciowy_html_jest_graceful(tmp_path):
    with patch.object(ux, "_CACHE_DIR", tmp_path), patch(
        "footstats.scrapers.browser_fetch.pobierz_html", return_value="<html>nic</html>"
    ):
        assert ux.fetch_league_team_xg("EPL", 2025) == {}
