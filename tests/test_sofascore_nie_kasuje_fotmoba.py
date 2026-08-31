"""Zablokowany SofaScore nie moze kasowac danych FotMoba.

Kolejnosc w przebiegu `final` (daily_agent.py):

  1010  _enrichuj_finalna_faza  -> _wzbogac_team_news zapisuje `injuries_*`
                                  z FotMoba, RAZEM Z POZYCJA
  1032  _wzbogac_forme_top      -> SofaScore nadpisuje te same pola
  1036  _apply_injury_corrections -> czyta `injuries_*` i koryguje lambde

SofaScore od 30.08 oddaje HTTP 403 na kazde zapytanie — i z Cloud Runa,
i lokalnie z lacza domowego. `pobierz_forme_meczu` nie rzuca wtedy wyjatku,
tylko zwraca `_empty_form`, w ktorym `injuries` to pusta lista. Przypisanie
w kroku 2 bylo BEZWARUNKOWE, wiec pusta lista z martwego zrodla nadpisywala
komplet absencji z pozycjami — a `_apply_injury_corrections` w kroku 3
dostawalo juz nic.

Objaw byloby zerowa korekta lambda przy poprawnie pobranych skladach:
kod chodzi, konczy sie sukcesem i nie robi nic. Dokladnie ten ksztalt bledu,
przez ktory `injury_lambda_factors` zwracalo (1.0, 1.0) w ciszy.
"""
from __future__ import annotations

import pytest

from footstats.core import daily_phases as dp
from footstats.scrapers.teamnews.base import Absencja, TeamNews


def _tn():
    return TeamNews(
        source="fotmob", home="Chelsea", away="Brighton", date="2026-08-31",
        typ_skladu="predicted",
        xi_home=tuple(f"G{i}" for i in range(11)),
        xi_away=tuple(f"A{i}" for i in range(11)),
        absencje_home=(Absencja("Cole Palmer", "injury", "Mid September 2026",
                                True, pozycja="F"),),
        absencje_away=(Absencja("Jan Paul van Hecke", "injury",
                                "Mid September 2026", True, pozycja="D"),),
        sedzia="Michael Oliver", sedzia_stats={"n_matches": 54},
    )


def _forma_martwego_zrodla(team_home: str, team_away: str) -> dict:
    """Ksztalt 1:1 z `form_scraper._empty_form` — tak wyglada odpowiedz po 403."""
    pusta = {"team": None, "team_id": None, "form": [], "goals_scored": 0,
             "goals_conceded": 0, "matches": [], "injuries": [], "source": "brak"}
    return {"home": dict(pusta), "away": dict(pusta), "h2h": []}


@pytest.fixture
def kandydat():
    return {"gospodarz": "Chelsea", "goscie": "Brighton",
            "lambda_h": 1.6, "lambda_a": 1.2,
            "pw": 45.0, "pr": 27.0, "pp": 28.0, "o25": 52.0, "bt": 51.0}


@pytest.fixture(autouse=True)
def _srodowisko(monkeypatch):
    monkeypatch.setenv(dp.FLAGA_TEAM_NEWS, "1")
    monkeypatch.setattr(dp, "_goal_shares_for", lambda team, side=None: {})
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [_tn()])
    monkeypatch.setattr("footstats.scrapers.form_scraper.PLAYWRIGHT_OK", True)


def test_martwy_sofascore_nie_kasuje_absencji_z_fotmoba(monkeypatch, kandydat):
    monkeypatch.setattr("footstats.scrapers.form_scraper.pobierz_forme_meczu",
                        _forma_martwego_zrodla)

    dp._wzbogac_team_news([kandydat])
    assert kandydat["injuries_home"], "warunek wstepny: FotMob ma zapisac absencje"

    dp._wzbogac_forme_top([kandydat], top_n=1)

    assert kandydat["injuries_home"] == [{"name": "Cole Palmer", "position": "F"}]
    assert kandydat["injuries_away"] == [
        {"name": "Jan Paul van Hecke", "position": "D"}]


def test_zywy_sofascore_dalej_nadpisuje(monkeypatch, kandydat):
    """Kontrola: naprawa nie moze wylaczyc dzialajacego zrodla.

    SofaScore niesie pelniejszy obraz (kontuzje + zawieszenia), wiec gdy
    naprawde odpowie, jego dane maja wygrac."""
    def _forma_zywa(gospodarz, goscie):
        return {
            "home": {"form": ["W", "W"], "goals_scored": 5, "goals_conceded": 1,
                     "injuries": [{"name": "Ktos Inny", "position": "M"}]},
            "away": {"form": ["L"], "goals_scored": 0, "goals_conceded": 2,
                     "injuries": [{"name": "Ktos Drugi", "position": "G"}]},
            "h2h": [],
        }

    monkeypatch.setattr("footstats.scrapers.form_scraper.pobierz_forme_meczu",
                        _forma_zywa)

    dp._wzbogac_team_news([kandydat])
    dp._wzbogac_forme_top([kandydat], top_n=1)

    assert kandydat["injuries_home"] == [{"name": "Ktos Inny", "position": "M"}]
    assert kandydat["sofa_forma_g"] == "WW(5:1)"


def test_brak_danych_z_obu_zrodel_zostawia_pole_puste(monkeypatch):
    """Bez FotMoba i bez SofaScore pole ma nie klamac, ze cos policzono."""
    k = {"gospodarz": "Chelsea", "goscie": "Brighton"}
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [])
    monkeypatch.setattr("footstats.scrapers.form_scraper.pobierz_forme_meczu",
                        _forma_martwego_zrodla)

    dp._wzbogac_team_news([k])
    dp._wzbogac_forme_top([k], top_n=1)

    assert not k.get("injuries_home")
    assert not k.get("injuries_away")
