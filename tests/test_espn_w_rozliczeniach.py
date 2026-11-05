"""test_espn_w_rozliczeniach.py — ESPN jako zrodlo wyniku nogi kuponu.

Przechodzi przez PRAWDZIWE `_find_leg_result` -> `_get_matches_espn` -> `EspnSource`;
podmieniona jest tylko siec (`requests.get` w MIEJSCU UZYCIA, czyli w espn_source)
i pozostale zrodla kaskady. Dopasowanie nazw idzie wspolna funkcja z football-data.org.
"""
from __future__ import annotations

import pytest

import footstats.core.coupon_settlement as cs
from footstats.scrapers.sources import espn_source


def _ev(eid, data_utc, h, a, hs, as_, status="STATUS_FULL_TIME"):
    return {
        "id": eid, "date": data_utc, "status": {"type": {"name": status}},
        "competitions": [{"competitors": [
            {"homeAway": "away", "score": str(as_), "team": {"displayName": a}},
            {"homeAway": "home", "score": str(hs), "team": {"displayName": h}},
        ]}],
    }


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


@pytest.fixture
def espn(monkeypatch, tmp_path):
    """Atrapa ESPN (dzien YYYYMMDD -> events) + wylaczone pozostale zrodla kaskady."""
    monkeypatch.setattr(espn_source, "CACHE_DIR", tmp_path)
    dni: dict[str, list] = {}
    wywolania: list[str] = []

    def _get(url, params=None, headers=None, timeout=None):
        wywolania.append(params["dates"])
        return _Resp({"events": dni.get(params["dates"], [])})

    monkeypatch.setattr(espn_source.requests, "get", _get)
    monkeypatch.setattr(cs, "_get_fixtures_api", lambda k, d: [])
    monkeypatch.setattr(cs, "_get_matches_fdb", lambda k, d: [])

    import footstats.scrapers.flashscore_results as fs
    monkeypatch.setattr(fs, "get_match_result", lambda *a, **k: None, raising=False)

    import footstats.core.backtest as bt

    def _brak_bazy():
        raise OSError("brak bazy w tescie")

    monkeypatch.setattr(bt, "_connect", _brak_bazy)
    import footstats.scrapers.sources.aggregator as agg
    monkeypatch.setattr(agg, "consensus_result", lambda h, a, d: None, raising=False)
    return {"dni": dni, "wywolania": wywolania}


def _szukaj(home, away, mdate="2026-11-03", fdb_cache=None):
    return cs._find_leg_result(home, away, mdate, {}, {} if fdb_cache is None else fdb_cache, "", "")


@pytest.mark.parametrize("kupon_h,kupon_a,espn_h,espn_a", [
    ("Hearts", "Rangers", "Heart of Midlothian", "Rangers"),
    ("København", "Odense", "FC Copenhagen", "Odense BK"),
    ("Sønderjyske", "Midtjylland", "SønderjyskE", "FC Midtjylland"),
    ("PAOK", "Asteras Tripolis", "PAOK Salonika", "Asteras Tripolis"),
    ("Wolverhampton", "Preston", "Wolverhampton Wanderers", "Preston North End"),
    ("Osnabrück", "Kaiserslautern", "VfL Osnabrück", "1. FC Kaiserslautern"),
    ("Paderborn", "Frankfurt", "SC Paderborn 07", "Eintracht Frankfurt"),
    ("Mainz", "Bayern", "1. FSV Mainz 05", "Bayern Munich"),
])
def test_noga_dostaje_wynik_z_espn_mimo_innych_nazw(espn, kupon_h, kupon_a, espn_h, espn_a):
    espn["dni"]["20261103"] = [_ev("1", "2026-11-03T17:45Z", espn_h, espn_a, 2, 1)]
    assert _szukaj(kupon_h, kupon_a) == "2-1"


@pytest.mark.parametrize("kupon_h,kupon_a,espn_h,espn_a", [
    ("Sheffield United", "Leeds", "Sheffield Wednesday", "Leeds United"),
    ("Bristol City", "Cardiff", "Bristol Rovers", "Cardiff City"),
    ("Manchester City", "Arsenal", "Manchester United", "Arsenal"),
    ("Inter", "Napoli", "Inter Miami", "Orlando City"),
    ("Legia", "Lech Poznan", "Legia Warszawa", "Lechia Gdansk"),
])
def test_falszywe_pary_nie_dostaja_wyniku(espn, kupon_h, kupon_a, espn_h, espn_a):
    espn["dni"]["20261103"] = [_ev("1", "2026-11-03T17:45Z", espn_h, espn_a, 2, 1)]
    assert _szukaj(kupon_h, kupon_a) is None


def test_odwrocona_kolejnosc_competitors_nie_zamienia_stron(espn):
    espn["dni"]["20261103"] = [_ev("1", "2026-11-03T17:45Z", "Hearts", "Rangers", 3, 0)]
    assert _szukaj("Hearts", "Rangers") == "3-0"


def test_dogrywka_i_karne_nie_daja_wyniku(espn):
    espn["dni"]["20261103"] = [
        _ev("1", "2026-11-03T17:45Z", "Hearts", "Rangers", 1, 1, "STATUS_FINAL_PEN"),
    ]
    assert _szukaj("Hearts", "Rangers") is None


def test_przesuniety_termin_data_plus_jeden(espn):
    espn["dni"]["20261104"] = [_ev("1", "2026-11-04T17:45Z", "Hearts", "Rangers", 0, 2)]
    assert _szukaj("Hearts", "Rangers", "2026-11-03") == "0-2"


def test_cache_per_data_nie_pyta_dwa_razy(espn):
    espn["dni"]["20261103"] = [_ev("1", "2026-11-03T17:45Z", "A Team", "B Team", 1, 0)]
    cache: dict = {}
    assert _szukaj("Nieznani", "Gracze", fdb_cache=cache) is None  # obie daty trafiaja do cache
    n = len(espn["wywolania"])
    _szukaj("C Team", "D Team", fdb_cache=cache)
    assert len(espn["wywolania"]) == n


def test_espn_przed_flashscore(espn, monkeypatch):
    import footstats.scrapers.flashscore_results as fs
    wolane = []
    monkeypatch.setattr(fs, "get_match_result",
                        lambda *a, **k: wolane.append(a) or "9-9", raising=False)
    espn["dni"]["20261103"] = [_ev("1", "2026-11-03T17:45Z", "Hearts", "Rangers", 1, 0)]
    assert _szukaj("Hearts", "Rangers") == "1-0"
    assert wolane == []


# ── rozliczanie predykcji (results_updater.update_pending) ───────────────────

def test_update_pending_uzywa_espn_przed_flashscore(monkeypatch):
    """Predykcja bez API-Football dostaje wynik z ESPN; FlashScore nie jest pytany."""
    from datetime import datetime, timedelta

    from footstats.scrapers import results_updater as ru

    wczoraj = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    monkeypatch.setattr(ru, "_get_api_key", lambda: None)
    monkeypatch.setattr("footstats.core.backtest.init_db", lambda: None)
    monkeypatch.setattr("footstats.core.backtest.get_pending_results", lambda: [{
        "id": 7, "match_date": wczoraj, "league": "Scottish Premiership",
        "team_home": "Hearts", "team_away": "Rangers", "ai_tip": "1",
    }])
    # import lokalny w funkcji -> patch u ZRODLA
    monkeypatch.setattr(
        "footstats.core.coupon_settlement._get_matches_espn",
        lambda d: [{"homeTeam": {"name": "Heart of Midlothian"},
                    "awayTeam": {"name": "Rangers"},
                    "score": {"fullTime": {"home": 2, "away": 0}}}],
    )
    monkeypatch.setattr(
        "footstats.scrapers.flashscore_results.get_match_result",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("FlashScore pytany")),
    )
    zapisane: list[tuple] = []
    monkeypatch.setattr(
        "footstats.core.backtest.update_result",
        lambda pid, wynik, stats=None: zapisane.append((pid, wynik)) or {"tip_correct": 1},
    )
    assert ru.update_pending(days_back=2, verbose=False)["updated"] == 1
    assert zapisane == [(7, "2-0")]


def test_kropkowany_prefiks_espn_pasuje_do_kuponu(espn):
    """Zmierzone 5.11: ESPN ma "F.C. København", kupon "FC København" (#1452)."""
    espn["dni"]["20261102"] = [
        _ev("1", "2026-11-02T18:00Z", "Sønderjyske Fodbold", "F.C. København", 0, 2)]
    assert _szukaj("Sønderjyske Fodbold", "FC København", "2026-11-02") == "0-2"
