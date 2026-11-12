"""espn_stats: statystyki meczu z atrapy JSON ESPN (zero sieci)."""
import requests

import footstats.scrapers.sources.espn_stats as espn_stats

SCOREBOARD = {"events": [{
    "id": "700",
    "status": {"type": {"name": "STATUS_FULL_TIME"}},
    "competitions": [{"competitors": [
        {"homeAway": "away", "team": {"displayName": "Poland"},
         "statistics": [{"name": "wonCorners", "displayValue": "3"}]},
        {"homeAway": "home", "team": {"displayName": "Scotland"},
         "statistics": [{"name": "foo", "displayValue": "9"},
                        {"name": "wonCorners", "displayValue": "6"}]},
    ]}],
}, {
    "id": "701",
    "status": {"type": {"name": "STATUS_SCHEDULED"}},
    "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"displayName": "Scotland"}},
        {"homeAway": "away", "team": {"displayName": "Poland"}}]}],
}]}


def _st(**stat):
    return [{"name": k, "value": v} for k, v in stat.items()]


SUMMARY = {"rosters": [
    {"homeAway": "home", "team": {"displayName": "Scotland"}, "roster": [
        {"athlete": {"displayName": "Scott McTominay"},
         "stats": _st(totalGoals=1, ownGoals=0, shotsOnTarget=2, appearances=1)},
        {"stats": _st(totalGoals=9)},  # bez klucza athlete — pomijany
        {"athlete": {"displayName": "Ławka Gracz"},
         "stats": _st(totalGoals=0, shotsOnTarget=0, appearances=0)},
    ]},
    {"homeAway": "away", "team": {"displayName": "Poland"}, "roster": [
        {"athlete": {"displayName": "Piotr Zieliński"},
         "stats": _st(totalGoals=0, ownGoals=1, shotsOnTarget=1, appearances=1)},
    ]},
]}


class _Resp:
    def __init__(self, dane, kod=200):
        self._d, self.status_code = dane, kod

    def json(self):
        return self._d


def _atrapa(monkeypatch, scoreboard=SCOREBOARD, summary=SUMMARY):
    def get(url, params=None, headers=None, timeout=None):
        assert timeout == 15
        if url.endswith("/summary"):
            return _Resp(summary)
        return _Resp(scoreboard if params["dates"] == "20261112" else {"events": []})
    monkeypatch.setattr(espn_stats.requests, "get", get)


def test_statystyki_meczu_zwraca_rozne_i_zawodnikow(monkeypatch):
    _atrapa(monkeypatch)
    wynik = espn_stats.statystyki_meczu("Scotland", "Poland", "2026-11-12")
    assert wynik["corners"] == (6, 3)
    z = wynik["zawodnicy"]
    assert z["scott mctominay"] == {"gole": 1, "sot": 2, "zagral": True, "druzyna": "home"}
    assert z["piotr zielinski"]["druzyna"] == "away"
    assert z["lawka gracz"]["zagral"] is False
    assert len(z) == 3  # wpis bez athlete pominięty


def test_brak_meczu_to_none(monkeypatch):
    _atrapa(monkeypatch)
    assert espn_stats.statystyki_meczu("Legia", "Lech", "2026-11-12") is None


def test_blad_sieci_to_none(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("brak sieci")
    monkeypatch.setattr(espn_stats.requests, "get", boom)
    assert espn_stats.statystyki_meczu("Scotland", "Poland", "2026-11-12") is None


def test_brak_wonCorners_daje_corners_none(monkeypatch):
    sb = {"events": [{
        "id": "1", "status": {"type": {"name": "STATUS_FULL_TIME"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"displayName": "Scotland"}},
            {"homeAway": "away", "team": {"displayName": "Poland"}}]}]}]}
    _atrapa(monkeypatch, scoreboard=sb)
    wynik = espn_stats.statystyki_meczu("Scotland", "Poland", "2026-11-12")
    assert wynik["corners"] is None
