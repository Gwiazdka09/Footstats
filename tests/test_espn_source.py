"""test_espn_source.py — EspnSource: nieoficjalne API ESPN, tylko wyniki po 90 minutach.

Zero sieci: `requests.get` podmieniony w MIEJSCU UZYCIA (modul espn_source),
cache kierowany do katalogu tymczasowego.
"""
from __future__ import annotations

from typing import Any

import pytest
import requests

from footstats.scrapers.sources import espn_source
from footstats.scrapers.sources.espn_source import EspnSource


def _ev(eid: str, data_utc: str, status: str, gospodarz: tuple[str, str],
        gosc: tuple[str, str], odwroc: bool = False) -> dict[str, Any]:
    """Zdarzenie ESPN; krotki = (nazwa, score). `odwroc` zamienia kolejnosc tablicy."""
    h = {"homeAway": "home", "score": gospodarz[1], "team": {"displayName": gospodarz[0]}}
    a = {"homeAway": "away", "score": gosc[1], "team": {"displayName": gosc[0]}}
    return {
        "id": eid, "date": data_utc,
        "status": {"type": {"name": status}},
        "competitions": [{"competitors": [a, h] if odwroc else [h, a]}],
    }


class _Resp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._p, self.status_code = payload, status

    def json(self) -> Any:
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


@pytest.fixture
def siec(monkeypatch, tmp_path):
    """Podstawia requests.get: dzien (YYYYMMDD) -> payload/Exception/_Resp."""
    monkeypatch.setattr(espn_source, "CACHE_DIR", tmp_path)
    stan: dict[str, Any] = {"dni": {}, "wywolania": []}

    def _get(url, params=None, headers=None, timeout=None):
        dzien = params["dates"]
        stan["wywolania"].append(dzien)
        wynik = stan["dni"].get(dzien, {"events": []})
        if isinstance(wynik, requests.RequestException):
            raise wynik
        return wynik if isinstance(wynik, _Resp) else _Resp(wynik)

    monkeypatch.setattr(espn_source.requests, "get", _get)
    return stan


def test_pelny_czas_daje_wynik_a_gospodarz_po_homeaway(siec):
    siec["dni"]["20261103"] = {"events": [
        _ev("1", "2026-11-03T17:45Z", "STATUS_FULL_TIME", ("Hearts", "2"), ("Rangers", "1"), odwroc=True),
    ]}
    mecze = EspnSource().fetch("2026-11-03")
    assert len(mecze) == 1
    m = mecze[0]
    assert (m.home, m.away, m.ft_home, m.ft_away) == ("Hearts", "Rangers", 2, 1)
    assert m.status == "finished" and m.date == "2026-11-03" and m.source == "espn"
    assert m.to_result_str() == "2-1"


@pytest.mark.parametrize("status", [
    "STATUS_FINAL_PEN", "STATUS_FINAL_AET", "STATUS_FINAL_AGT",
    "STATUS_POSTPONED", "STATUS_IN_PROGRESS", "STATUS_SCHEDULED",
])
def test_tylko_full_time_daje_wynik(siec, status):
    siec["dni"]["20261103"] = {"events": [
        _ev("1", "2026-11-03T17:45Z", status, ("A", "1"), ("B", "1")),
    ]}
    mecze = EspnSource().fetch("2026-11-03")
    assert all(m.to_result_str() is None for m in mecze)
    assert all(m.status != "finished" for m in mecze)


def test_score_nieliczbowy_pomija_mecz(siec):
    siec["dni"]["20261103"] = {"events": [
        _ev("1", "2026-11-03T17:45Z", "STATUS_FULL_TIME", ("A", "x"), ("B", "1")),
        _ev("2", "2026-11-03T18:00Z", "STATUS_FULL_TIME", ("C", "3"), ("D", "0")),
    ]}
    mecze = EspnSource().fetch("2026-11-03")
    assert [(m.home, m.ft_home) for m in mecze] == [("C", 3)]


def test_pozny_mecz_trafia_do_dnia_polskiego(siec):
    """22:30 UTC dnia d-1 to juz dzien d w Polsce; 21:59 UTC nie."""
    siec["dni"]["20261102"] = {"events": [
        _ev("1", "2026-11-02T22:30Z", "STATUS_FULL_TIME", ("Pozny", "1"), ("X", "0")),
        _ev("2", "2026-11-02T21:59Z", "STATUS_FULL_TIME", ("Wczesny", "1"), ("Y", "0")),
    ]}
    siec["dni"]["20261103"] = {"events": [
        _ev("3", "2026-11-03T12:00Z", "STATUS_FULL_TIME", ("Dzien", "2"), ("Z", "2")),
    ]}
    siec["dni"]["20261104"] = {"events": [
        _ev("4", "2026-11-04T01:00Z", "STATUS_FULL_TIME", ("Jutro", "0"), ("W", "0")),
    ]}
    nazwy = {m.home for m in EspnSource().fetch("2026-11-03")}
    assert nazwy == {"Pozny", "Dzien"}


def test_zdarzenie_z_sasiedniego_koszyka_ale_z_data_utc_d_jest_brane(siec):
    """Granica dnia ESPN nieznana: mecz UTC d moze lezec w koszyku d+1 i byc zdublowany."""
    ev = _ev("9", "2026-11-03T01:00Z", "STATUS_FULL_TIME", ("Rano", "1"), ("Q", "0"))
    siec["dni"]["20261102"] = {"events": [ev]}
    siec["dni"]["20261103"] = {"events": [ev]}
    mecze = EspnSource().fetch("2026-11-03")
    assert [m.home for m in mecze] == ["Rano"]


@pytest.mark.parametrize("blad", [
    requests.ConnectionError("boom"),
    _Resp({}, status=500),
    _Resp(ValueError("zly json")),
    _Resp({"brak": "events"}),
    _Resp({"events": [{"date": "2026-11-03T10:00Z"}]}),
    _Resp({"events": [{"date": "zla", "status": {"type": {"name": "STATUS_FULL_TIME"}},
                       "competitions": [{"competitors": []}]}]}),
])
def test_bledy_daja_pusta_liste_i_warning(siec, caplog, blad):
    for d in ("20261102", "20261103", "20261104"):
        siec["dni"][d] = blad
    with caplog.at_level("WARNING"):
        assert EspnSource().fetch("2026-11-03") == []
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_cache_nie_zapisuje_pustych_ani_nieudanych(siec, tmp_path):
    siec["dni"]["20261102"] = requests.ConnectionError("x")
    siec["dni"]["20261103"] = {"events": []}
    EspnSource().fetch("2026-11-03")
    assert list(tmp_path.iterdir()) == []


def test_cache_nastepne_wywolanie_bez_sieci(siec):
    siec["dni"]["20261103"] = {"events": [
        _ev("1", "2026-11-03T17:45Z", "STATUS_FULL_TIME", ("A", "1"), ("B", "0")),
    ]}
    EspnSource().fetch("2026-11-03")
    n = len(siec["wywolania"])
    assert len(EspnSource().fetch("2026-11-03")) == 1
    # dzien z danymi jest z cache; puste sasiednie koszyki pytane ponownie
    assert "20261103" not in siec["wywolania"][n:]


def test_zarejestrowany_w_agregatorze():
    from footstats.scrapers.sources.aggregator import get_sources
    assert "espn" in [s.name for s in get_sources()]


def test_kropkowany_prefiks_nazwy_jest_sklejany(siec):
    """ESPN pisze "F.C. København"; normalize_team_name robi z tego "f c kobenhavn"."""
    siec["dni"]["20261102"] = {"events": [
        _ev("1", "2026-11-02T18:00Z", "STATUS_FULL_TIME",
            ("Sønderjyske Fodbold", "0"), ("F.C. København", "2")),
    ]}
    assert EspnSource().fetch("2026-11-02")[0].away == "FC København"
