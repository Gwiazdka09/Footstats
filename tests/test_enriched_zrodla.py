"""test_enriched_zrodla.py — trzy zrodla wzbogacania: kontuzje, konferencje, xG.

PO CO: najgrozniejsza jest tu `pobierz_forme_xg`. Funkcja odwraca perspektywe
w zaleznosci od tego, czy druzyna grala u siebie:

    jest_gospodarzem -> xg_for = home_xg, xg_against = away_xg
    inaczej          -> xg_for = away_xg, xg_against = home_xg

Pomylka w tym miejscu ZAMIENIA xG strzelone ze straconymi. Model dostaje wtedy
dokladnie odwrotny obraz sily druzyny, a wynik nadal wyglada wiarygodnie —
zadna walidacja tego nie wylapie. Dlatego oba warianty maja osobny test.

Do tego kazde zrodlo ma cache i musi go uzywac (limit zapytan) oraz przezyc
brak danych bez wyjatku.
"""
from __future__ import annotations

import pytest
import requests

import footstats.scrapers.enriched as en


@pytest.fixture(autouse=True)
def cache_w_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(en, "CACHE_DIR", tmp_path / "enriched")


class _Odp:
    def __init__(self, status=200, dane=None):
        self.status_code = status
        self._dane = dane if dane is not None else {}

    def json(self):
        return self._dane


# ══════════════════════════════════════════════════════════════════════════
#  pobierz_kontuzje
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def fdb(monkeypatch):
    stan = {"team_id": 57, "dane": None, "wywolania": []}

    monkeypatch.setattr(en, "_szukaj_team_id",
                        lambda n: stan["team_id"])

    def _get(endpoint):
        stan["wywolania"].append(endpoint)
        return stan["dane"]

    monkeypatch.setattr(en, "_fdb_get", _get)
    return stan


def _gracz(name="Kowalski", status="ACTIVE", position="Defender") -> dict:
    return {"name": name, "status": status, "position": position}


def test_kontuzje_rozdziela_urazy_od_zawieszen(fdb):
    fdb["dane"] = {"name": "Arsenal FC", "squad": [
        _gracz("Zdrowy", "ACTIVE"),
        _gracz("Ranny", "INJURED", "Midfielder"),
        _gracz("Ukarany", "SUSPENDED"),
    ]}
    wynik = en.pobierz_kontuzje("Arsenal")

    assert [g["name"] for g in wynik["injured"]] == ["Ranny"]
    assert [g["name"] for g in wynik["suspended"]] == ["Ukarany"]
    assert wynik["squad_size"] == 3
    assert wynik["team_name"] == "Arsenal FC"


@pytest.mark.parametrize("status", ["INJURED", "injured", "Long-term injury", "kontuzja"])
def test_rozne_zapisy_kontuzji_rozpoznawane(fdb, status):
    fdb["dane"] = {"squad": [_gracz("X", status)]}
    assert len(en.pobierz_kontuzje("Arsenal")["injured"]) == 1


@pytest.mark.parametrize("status", ["SUSPENDED", "banned", "zawieszony"])
def test_rozne_zapisy_zawieszenia_rozpoznawane(fdb, status):
    fdb["dane"] = {"squad": [_gracz("X", status)]}
    assert len(en.pobierz_kontuzje("Arsenal")["suspended"]) == 1


def test_brak_statusu_nie_wywala(fdb):
    """API potrafi oddac status=None — gracz ma byc po prostu zdrowy."""
    fdb["dane"] = {"squad": [{"name": "Bezstatusowy"}]}
    wynik = en.pobierz_kontuzje("Arsenal")
    assert wynik["injured"] == [] and wynik["suspended"] == []


def test_nieznana_druzyna_daje_none(fdb):
    fdb["team_id"] = None
    assert en.pobierz_kontuzje("Nieistniejacy") is None


def test_brak_odpowiedzi_daje_none(fdb):
    fdb["dane"] = None
    assert en.pobierz_kontuzje("Arsenal") is None


def test_kontuzje_uzywaja_cache(fdb):
    fdb["dane"] = {"squad": []}
    en.pobierz_kontuzje("Arsenal")
    ile = len(fdb["wywolania"])

    en.pobierz_kontuzje("Arsenal")
    assert len(fdb["wywolania"]) == ile, "drugie wywolanie poszlo po sieci"


# ══════════════════════════════════════════════════════════════════════════
#  pobierz_konferencje
# ══════════════════════════════════════════════════════════════════════════

class _Feed:
    def __init__(self, entries):
        self.entries = entries


@pytest.fixture
def rss(monkeypatch):
    stan = {"entries": [], "url": None}

    class _FakeFeedparser:
        @staticmethod
        def parse(url):
            stan["url"] = url
            if isinstance(stan["entries"], Exception):
                raise stan["entries"]
            return _Feed(stan["entries"])

    monkeypatch.setattr(en, "feedparser", _FakeFeedparser)
    return stan


def test_brak_feedparsera_daje_none(monkeypatch):
    """feedparser jest opcjonalny — jego brak nie moze wywalic wzbogacania."""
    monkeypatch.setattr(en, "feedparser", None)
    assert en.pobierz_konferencje("Legia") is None


def test_konferencja_zwraca_pierwszy_wpis(rss):
    rss["entries"] = [
        {"title": "Trener o meczu", "link": "http://a", "published": "2026-07-30",
         "summary": "Zagramy ofensywnie"},
        {"title": "Starszy wpis", "link": "http://b"},
    ]
    wynik = en.pobierz_konferencje("Legia")

    assert wynik["title"] == "Trener o meczu"
    assert wynik["link"] == "http://a"
    assert wynik["snippet"] == "Zagramy ofensywnie"


def test_html_usuwany_ze_snippetu(rss):
    """Google News zwraca HTML — do promptu ma isc czysty tekst."""
    rss["entries"] = [{"title": "t", "summary": "<a href='x'>Trener</a> <b>powiedzial</b>"}]
    assert en.pobierz_konferencje("Legia")["snippet"] == "Trener powiedzial"


def test_snippet_przycinany_do_limitu(rss):
    rss["entries"] = [{"title": "t", "summary": "x" * 5000}]
    assert len(en.pobierz_konferencje("Legia")["snippet"]) == en.PRESS_CHARS


def test_pusty_feed_daje_none(rss):
    rss["entries"] = []
    assert en.pobierz_konferencje("Legia") is None


def test_nazwa_druzyny_trafia_do_zapytania(rss):
    rss["entries"] = [{"title": "t"}]
    en.pobierz_konferencje("Górnik Zabrze")
    assert "rnik" in rss["url"], "nazwa druzyny nie trafila do URL"


def test_awaria_rss_daje_none(rss):
    rss["entries"] = AttributeError("zly ksztalt feeda")
    assert en.pobierz_konferencje("Legia") is None


# ══════════════════════════════════════════════════════════════════════════
#  _bzz_get
# ══════════════════════════════════════════════════════════════════════════

def test_bzz_bez_klucza_nie_rusza_sieci(monkeypatch):
    wolania = []
    monkeypatch.setattr(en, "BZZOIRO_KEY", "")
    monkeypatch.setattr(requests, "get", lambda *a, **k: wolania.append(a))

    assert en._bzz_get("/teams/") is None
    assert wolania == []


def test_bzz_200_zwraca_json(monkeypatch):
    monkeypatch.setattr(en, "BZZOIRO_KEY", "klucz")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Odp(200, {"results": [1]}))
    assert en._bzz_get("/teams/") == {"results": [1]}


def test_bzz_wysyla_token(monkeypatch):
    monkeypatch.setattr(en, "BZZOIRO_KEY", "tajny")
    zebrane = {}

    def _get(url, headers=None, params=None, timeout=None):
        zebrane.update(headers=headers, params=params)
        return _Odp(200, {})

    monkeypatch.setattr(requests, "get", _get)
    en._bzz_get("/teams/", {"name": "Legia"})

    assert zebrane["headers"]["Authorization"] == "Token tajny"
    assert zebrane["params"] == {"name": "Legia"}


def test_bzz_blad_sieci_daje_none(monkeypatch):
    monkeypatch.setattr(en, "BZZOIRO_KEY", "klucz")

    def _padnij(*a, **k):
        raise requests.RequestException("timeout")

    monkeypatch.setattr(requests, "get", _padnij)
    assert en._bzz_get("/teams/") is None


# ══════════════════════════════════════════════════════════════════════════
#  pobierz_forme_xg
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def bzz(monkeypatch):
    """Podstawia _bzz_get: /teams/ zwraca id, /events/ zwraca mecze."""
    stan = {"team_id": 11, "events": [], "sciezki": []}

    def _get(path, params=None):
        stan["sciezki"].append(path)
        if path == "/teams/":
            return {"results": [{"id": stan["team_id"]}]} if stan["team_id"] else {"results": []}
        if path == "/events/":
            return {"results": stan["events"]} if stan["events"] is not None else None
        return None

    monkeypatch.setattr(en, "_bzz_get", _get)
    return stan


def _event(data="2026-07-30", home_id=11, away_id=22,
           home_xg=2.0, away_xg=0.5, home="Legia", away="Lech") -> dict:
    return {
        "event_date": data,
        "home_team": {"id": home_id, "name": home},
        "away_team": {"id": away_id, "name": away},
        "stats": {"home_xg": home_xg, "away_xg": away_xg},
        "score": "2:0",
    }


def test_xg_gdy_druzyna_gra_u_siebie(bzz):
    """team_id=11 jest GOSPODARZEM → xg_for = home_xg."""
    bzz["events"] = [_event(home_id=11, home_xg=2.4, away_xg=0.7)]
    wynik = en.pobierz_forme_xg("Legia")

    wpis = wynik["historia"][0]
    assert wpis["xg_for"] == 2.4
    assert wpis["xg_against"] == 0.7
    assert wpis["opponent"] == "Lech"


def test_xg_gdy_druzyna_gra_na_wyjezdzie(bzz):
    """team_id=11 jest GOSCIEM → xg_for = away_xg. Odwrotnie = zatruty model."""
    bzz["events"] = [_event(home_id=22, away_id=11, home_xg=2.4, away_xg=0.7,
                            home="Lech", away="Legia")]
    wynik = en.pobierz_forme_xg("Legia")

    wpis = wynik["historia"][0]
    assert wpis["xg_for"] == 0.7, "xG strzelone pobrane ze zlej strony"
    assert wpis["xg_against"] == 2.4
    assert wpis["opponent"] == "Lech"


def test_srednie_liczone_z_historii(bzz):
    bzz["events"] = [
        _event(data="2026-07-30", home_xg=2.0, away_xg=1.0),
        _event(data="2026-07-20", home_xg=1.0, away_xg=0.0),
    ]
    wynik = en.pobierz_forme_xg("Legia")

    assert wynik["mecze"] == 2
    assert wynik["xg_scored_avg"] == 1.5
    assert wynik["xg_conc_avg"] == 0.5


def test_bierze_najnowsze_mecze(bzz):
    """Sortowanie malejaco po dacie — forma to OSTATNIE mecze, nie pierwsze z brzegu."""
    bzz["events"] = [
        _event(data="2026-01-01", home_xg=9.0),
        _event(data="2026-07-30", home_xg=1.0),
        _event(data="2026-06-15", home_xg=5.0),
    ]
    wynik = en.pobierz_forme_xg("Legia", ostatnie_n=2)

    assert [w["date"] for w in wynik["historia"]] == ["2026-07-30", "2026-06-15"]


def test_limit_ostatnie_n_respektowany(bzz):
    bzz["events"] = [_event(data=f"2026-07-{d:02d}") for d in range(1, 20)]
    assert en.pobierz_forme_xg("Legia", ostatnie_n=3)["mecze"] == 3


def test_alternatywne_nazwy_pol_xg(bzz):
    """API bywa niespojne: stats.xg_home zamiast stats.home_xg."""
    ev = _event()
    ev["stats"] = {"xg_home": 3.1, "xg_away": 0.4}
    bzz["events"] = [ev]

    assert en.pobierz_forme_xg("Legia")["historia"][0]["xg_for"] == 3.1


def test_xg_na_poziomie_zdarzenia(bzz):
    """Trzeci wariant: xG bezposrednio w zdarzeniu, bez `stats`."""
    ev = _event()
    ev["stats"] = {}
    ev["home_xg"], ev["away_xg"] = 1.7, 1.2
    bzz["events"] = [ev]

    assert en.pobierz_forme_xg("Legia")["historia"][0]["xg_for"] == 1.7


def test_brak_xg_nie_psuje_sredniej(bzz):
    """Mecz bez xG wchodzi do historii, ale nie zaniza sredniej zerem."""
    ev_bez = _event(data="2026-07-29")
    ev_bez["stats"] = {}
    bzz["events"] = [_event(data="2026-07-30", home_xg=2.0, away_xg=1.0), ev_bez]

    wynik = en.pobierz_forme_xg("Legia")
    assert wynik["mecze"] == 2
    assert wynik["xg_scored_avg"] == 2.0, "brakujace xG policzone jako 0"


def test_xg_nieznanej_druzyny_daje_none(bzz):
    bzz["team_id"] = None
    assert en.pobierz_forme_xg("Nieistniejacy") is None


def test_xg_bez_meczow_daje_none(bzz):
    bzz["events"] = []
    assert en.pobierz_forme_xg("Legia") is None


def test_forma_xg_uzywa_cache(bzz):
    bzz["events"] = [_event()]
    en.pobierz_forme_xg("Legia")
    ile = len(bzz["sciezki"])

    en.pobierz_forme_xg("Legia")
    assert len(bzz["sciezki"]) == ile, "drugie wywolanie poszlo po sieci"


def test_rozne_n_to_rozne_wpisy_cache(bzz):
    """Cache musi rozrozniac ostatnie_n — inaczej n=3 oddaje wynik dla n=5."""
    bzz["events"] = [_event(data=f"2026-07-{d:02d}") for d in range(1, 10)]
    assert en.pobierz_forme_xg("Legia", ostatnie_n=2)["mecze"] == 2
    assert en.pobierz_forme_xg("Legia", ostatnie_n=5)["mecze"] == 5


def test_zerowe_xg_nie_jest_traktowane_jak_brak(bzz):
    """REGRESJA: `a or b or c` uznawalo xG = 0.0 za brak danych.

    Mecz bez straconego xG wypadal ze sredniej straconych — czyli IDEALNY
    wystep defensywny podnosil statystyke straconych, zamiast ja obnizac.
    """
    bzz["events"] = [
        _event(data="2026-07-30", home_xg=2.0, away_xg=0.0),
        _event(data="2026-07-20", home_xg=2.0, away_xg=2.0),
    ]
    wynik = en.pobierz_forme_xg("Legia")

    assert wynik["historia"][0]["xg_against"] == 0.0, "zero potraktowane jak brak"
    assert wynik["xg_conc_avg"] == 1.0, "srednia policzona z pominieciem zera"


def test_zerowe_xg_strzelone_tez_liczone(bzz):
    bzz["events"] = [
        _event(data="2026-07-30", home_xg=0.0, away_xg=1.0),
        _event(data="2026-07-20", home_xg=2.0, away_xg=1.0),
    ]
    wynik = en.pobierz_forme_xg("Legia")

    assert wynik["historia"][0]["xg_for"] == 0.0
    assert wynik["xg_scored_avg"] == 1.0
