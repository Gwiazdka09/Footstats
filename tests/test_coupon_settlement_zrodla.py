"""test_coupon_settlement_zrodla.py — kaskada zrodel wyniku dla nogi kuponu.

PO CO: `_find_leg_result` to serce rozliczen. Piec zrodel w ustalonej kolejnosci
plus fallback na date+1. Docstring w kodzie tlumaczy, po co ten fallback:

    "Terminarz bywa przesuwany o 1 dzien po stronie API juz po utworzeniu
     kuponu (...), co bez tego fallbacku skutkuje fuzzy-matchem do innego meczu
     tego dnia (falszywy wynik) albo wieczna PARTIAL"

Oba skutki sa ciche: falszywy wynik zapisuje sie jak prawdziwy, a wieczny
PARTIAL wyglada jak "mecz jeszcze nierozegrany". Zadne z tego nie bylo
przetestowane.

Drugi wazny szczegol: FlashScore jest CELOWO po zrodlach twardych (API-Football,
football-data.org) — jego cache bywa zapisany pod bledna data. Kolejnosc
kaskady to decyzja projektowa, nie przypadek, wiec ma test.
"""
from __future__ import annotations

from datetime import date

import pytest
import requests

import footstats.core.coupon_settlement as cs


@pytest.fixture
def zrodla(monkeypatch):
    """Podstawia wszystkie piec zrodel. Domyslnie kazde nic nie znajduje."""
    stan = {
        "af": {},              # data -> lista fixtures
        "fdb": {},             # data -> lista meczow
        "znajdz": None,        # wynik `_znajdz_wynik` (albo dict data->wynik)
        "flashscore": {},      # data -> wynik
        "db": {},              # data -> actual_result
        "consensus": {},       # data -> wynik
        "kolejnosc": [],       # slad, ktore zrodlo bylo pytane
    }

    monkeypatch.setattr(cs, "_get_fixtures_api",
                        lambda key, d: stan["kolejnosc"].append(f"af:{d}") or stan["af"].get(d, []))
    monkeypatch.setattr(cs, "_get_matches_fdb",
                        lambda key, d: stan["kolejnosc"].append(f"fdb:{d}") or stan["fdb"].get(d, []))

    import footstats.scrapers.results_updater as ru

    def _znajdz(pending, fixtures, api_key=None, min_similarity=0.70):
        if isinstance(stan["znajdz"], dict):
            for d, wynik in stan["znajdz"].items():
                if fixtures and fixtures[0].get("_data") == d:
                    return wynik
            return None
        return stan["znajdz"]

    monkeypatch.setattr(ru, "_znajdz_wynik", _znajdz)

    import footstats.scrapers.flashscore_results as fs
    monkeypatch.setattr(fs, "get_match_result",
                        lambda h, a, d, cache_enabled=True:
                        stan["kolejnosc"].append(f"fs:{d}") or stan["flashscore"].get(d),
                        raising=False)

    import footstats.core.backtest as bt

    class _Kursor:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class _Conn:
        def execute(self, sql, params=()):
            d = params[0] if params else None
            stan["kolejnosc"].append(f"db:{d}")
            wynik = stan["db"].get(d)
            return _Kursor({"actual_result": wynik} if wynik else None)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(bt, "_connect", lambda: _Conn())

    import footstats.scrapers.sources.aggregator as agg
    monkeypatch.setattr(agg, "consensus_result",
                        lambda h, a, d: stan["kolejnosc"].append(f"cons:{d}")
                        or stan["consensus"].get(d), raising=False)
    return stan


def _szukaj(stan, home="Legia", away="Lech", mdate="2026-08-02"):
    return cs._find_leg_result(
        home, away, mdate,
        fixtures_cache={}, fdb_cache={},
        api_key="klucz-af", fdb_key="klucz-fdb",
    )


# ── kaskada: kolejnosc zrodel ───────────────────────────────────────────────

def test_brak_wyniku_we_wszystkich_zrodlach(zrodla):
    assert _szukaj(zrodla) is None


def test_api_football_ma_priorytet(zrodla):
    zrodla["znajdz"] = "2-1"
    assert _szukaj(zrodla) == "2-1"
    assert not any(k.startswith("fs:") for k in zrodla["kolejnosc"]), \
        "pytano FlashScore mimo trafienia w API-Football"


def test_football_data_gdy_brak_w_api(zrodla, monkeypatch):
    zrodla["fdb"]["2026-08-02"] = [{
        "homeTeam": {"name": "Legia Warszawa"}, "awayTeam": {"name": "Lech Poznan"},
        "score": {"fullTime": {"home": 3, "away": 0}},
    }]
    assert _szukaj(zrodla) == "3-0"


def test_flashscore_dopiero_po_zrodlach_twardych(zrodla):
    """DECYZJA PROJEKTOWA: cache FlashScore bywa pod bledna data, wiec ma nizszy
    priorytet niz API-Football i football-data.org."""
    zrodla["flashscore"]["2026-08-02"] = "1-1"
    wynik = _szukaj(zrodla)

    assert wynik == "1-1"
    kolejnosc = zrodla["kolejnosc"]
    pierwszy_fs = next(i for i, k in enumerate(kolejnosc) if k.startswith("fs:"))
    assert any(k.startswith("af:") for k in kolejnosc[:pierwszy_fs]), \
        "FlashScore odpytany przed API-Football"
    assert any(k.startswith("fdb:") for k in kolejnosc[:pierwszy_fs]), \
        "FlashScore odpytany przed football-data.org"


def test_baza_predictions_jako_czwarte_zrodlo(zrodla):
    zrodla["db"]["2026-08-02"] = "0-0"
    assert _szukaj(zrodla) == "0-0"


def test_konsensus_jako_ostatnia_deska(zrodla):
    zrodla["consensus"]["2026-08-02"] = "2-2"
    wynik = _szukaj(zrodla)

    assert wynik == "2-2"
    assert zrodla["kolejnosc"][-1].startswith("cons:")


# ── fallback +1 dzien (przesuniety terminarz) ───────────────────────────────

def test_sprawdza_takze_dzien_pozniej(zrodla):
    """SEDNO: terminarz przesuniety o dobe po utworzeniu kuponu."""
    zrodla["flashscore"]["2026-08-03"] = "1-0"
    assert _szukaj(zrodla, mdate="2026-08-02") == "1-0"


def test_data_wlasciwa_ma_pierwszenstwo_nad_nastepna(zrodla):
    """Gdy obie daty maja wynik, liczy sie ta z kuponu."""
    zrodla["flashscore"] = {"2026-08-02": "2-1", "2026-08-03": "5-0"}
    assert _szukaj(zrodla, mdate="2026-08-02") == "2-1"


def test_obie_daty_sprawdzane_w_kazdym_zrodle(zrodla):
    _szukaj(zrodla, mdate="2026-08-02")
    assert "af:2026-08-02" in zrodla["kolejnosc"]
    assert "af:2026-08-03" in zrodla["kolejnosc"]


def test_niepoprawna_data_nie_wywala(zrodla):
    """Zla data w kuponie: fallback +1 sie nie policzy, ale funkcja ma dzialac."""
    assert _szukaj(zrodla, mdate="nie-data") is None


def test_przesuniecie_logowane(zrodla, caplog):
    """Wynik z innej daty to sygnal — musi zostac w logu, nie przejsc cicho."""
    import logging
    zrodla["flashscore"]["2026-08-03"] = "1-0"
    with caplog.at_level(logging.INFO):
        _szukaj(zrodla, mdate="2026-08-02")
    assert any("przesuniety terminarz" in r.message for r in caplog.records)


# ── odporność ───────────────────────────────────────────────────────────────

def test_wynik_w_krotce_rozpakowany(zrodla, monkeypatch):
    """Niektore zrodla oddaja (wynik, statystyki) — do bazy ma isc sam wynik."""
    import footstats.scrapers.flashscore_results as fs
    monkeypatch.setattr(fs, "get_match_result",
                        lambda h, a, d, cache_enabled=True: ("3-1", {"xg": 1.5}),
                        raising=False)
    assert _szukaj(zrodla) == "3-1"


def test_awaria_bazy_logowana_a_nie_przemilczana(zrodla, monkeypatch, caplog):
    """Bez logu awaria bazy wyglada identycznie jak 'mecz nierozegrany'."""
    import logging
    import footstats.core.backtest as bt

    def _wybuch():
        raise RuntimeError("baza padla")

    monkeypatch.setattr(bt, "_connect", _wybuch)
    with caplog.at_level(logging.WARNING):
        _szukaj(zrodla)
    assert any("predictions" in r.message for r in caplog.records)


def test_awaria_konsensusu_logowana(zrodla, monkeypatch, caplog):
    import logging
    import footstats.scrapers.sources.aggregator as agg

    def _wybuch(h, a, d):
        raise OSError("agregator padl")

    monkeypatch.setattr(agg, "consensus_result", _wybuch, raising=False)
    with caplog.at_level(logging.WARNING):
        assert _szukaj(zrodla) is None
    assert any("onsensus" in r.message for r in caplog.records)


def test_brak_klucza_af_pomija_zrodlo(zrodla):
    wynik = cs._find_leg_result(
        "Legia", "Lech", "2026-08-02",
        fixtures_cache={}, fdb_cache={}, api_key="", fdb_key="k",
    )
    assert wynik is None
    assert not any(k.startswith("af:") for k in zrodla["kolejnosc"])


# ── _znajdz_wynik_fdb ───────────────────────────────────────────────────────

def _mecz_fdb(home="Legia Warszawa", away="Lech Poznan", hg=2, ag=1) -> dict:
    return {"homeTeam": {"name": home}, "awayTeam": {"name": away},
            "score": {"fullTime": {"home": hg, "away": ag}}}


def test_fdb_dopasowuje_wariant_nazwy():
    assert cs._znajdz_wynik_fdb("Legia", "Lech", [_mecz_fdb()]) == "2-1"


def test_fdb_odrzuca_slabe_dopasowanie():
    mecze = [_mecz_fdb(home="Wisła Kraków", away="Raków Częstochowa")]
    assert cs._znajdz_wynik_fdb("Legia", "Lech", mecze) is None


def test_fdb_bierze_najlepsze_dopasowanie():
    """Przy kilku kandydatach liczy sie NAJWYZSZY wynik podobienstwa."""
    mecze = [
        _mecz_fdb(home="Legia Warszawa II", away="Lech Poznan II", hg=9, ag=9),
        _mecz_fdb(home="Legia Warszawa", away="Lech Poznan", hg=2, ag=1),
    ]
    assert cs._znajdz_wynik_fdb("Legia Warszawa", "Lech Poznan", mecze) == "2-1"


def test_fdb_pomija_mecz_bez_wyniku():
    """Mecz FINISHED bez goli = dane niepelne, nie wynik 0-0."""
    mecz = _mecz_fdb()
    mecz["score"]["fullTime"] = {"home": None, "away": None}
    assert cs._znajdz_wynik_fdb("Legia", "Lech", [mecz]) is None


def test_fdb_pusta_lista():
    assert cs._znajdz_wynik_fdb("Legia", "Lech", []) is None


# ── _get_fixtures_api / _get_matches_fdb ────────────────────────────────────

class _Odp:
    def __init__(self, status=200, dane=None):
        self.status_code = status
        self._dane = dane if dane is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._dane


# Data MUSI byc ruchoma. Od 23.08 `_get_fixtures_api` nie wychodzi do API dla dat
# spoza okna darmowego planu, wiec data zaszyta na sztywno sprawia, ze test przestaje
# sprawdzac to, co opisuje: dostaje pusta liste z progu, nie z badanego zachowania.
# Progu pilnuje osobno `tests/test_horyzont_zrodel_wynikow.py`.
_DZIS = date.today().isoformat()


def test_fixtures_api_zwraca_liste(monkeypatch):
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _Odp(200, {"response": [1, 2]}))
    assert cs._get_fixtures_api("klucz", _DZIS) == [1, 2]


def test_fixtures_api_blad_daje_pusta_liste(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Odp(500))
    assert cs._get_fixtures_api("klucz", _DZIS) == []


def test_fixtures_api_blad_sieci_daje_pusta_liste(monkeypatch):
    def _padnij(*a, **k):
        raise requests.RequestException("brak sieci")

    monkeypatch.setattr(requests, "get", _padnij)
    assert cs._get_fixtures_api("klucz", "2026-08-02") == []


def test_fdb_bez_klucza_nie_rusza_sieci(monkeypatch):
    wolania = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: wolania.append(a))
    assert cs._get_matches_fdb("", "2026-08-02") == []
    assert wolania == []


def test_fdb_pyta_o_mecze_zakonczone(monkeypatch):
    zebrane = {}

    def _get(url, headers=None, params=None, timeout=None):
        zebrane.update(params=params, headers=headers)
        return _Odp(200, {"matches": [1]})

    monkeypatch.setattr(requests, "get", _get)
    assert cs._get_matches_fdb("klucz", "2026-08-02") == [1]
    assert zebrane["params"]["status"] == "FINISHED"
    assert zebrane["headers"]["X-Auth-Token"] == "klucz"


def test_fdb_blad_daje_pusta_liste(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Odp(403))
    assert cs._get_matches_fdb("klucz", "2026-08-02") == []


def test_fdb_nie_myli_manchesterow():
    """REGRESJA (bug #7): to zrodlo omijalo ochrone przed kolizja nazw.

    Surowy SequenceMatcher dawal 0.83 dla Manchester United / Manchester City —
    powyzej progu 0.70 — wiec kupon na United mogl zostac rozliczony wynikiem
    City. `team_similarity` daje tam 0.50 i blokuje dopasowanie.
    """
    mecze = [_mecz_fdb(home="Manchester City", away="Arsenal", hg=4, ag=0)]
    assert cs._znajdz_wynik_fdb("Manchester United", "Arsenal", mecze) is None


def test_fdb_nie_myli_klubow_dundee():
    mecze = [_mecz_fdb(home="Dundee FC", away="Celtic", hg=0, ag=3)]
    assert cs._znajdz_wynik_fdb("Dundee United", "Celtic", mecze) is None
