"""test_scrapers_enriched.py — wzbogacanie danych meczu (kontuzje, xG, murawa).

PO CO: modul mial 15%. `enrich_match_data` odpala SZESC osobnych pobran i kazde
moze paść niezaleznie. Kluczowe: awaria jednego zrodla NIE moze wywalic calego
wzbogacania — inaczej brak konferencji prasowej kasuje takze dane o kontuzjach
i xG, ktore juz sie udalo pobrac.

Cache ma TTL — wpis starszy niz CACHE_TTL_H musi byc zignorowany, inaczej model
liczy na skladach sprzed tygodnia i nikt tego nie zauwazy.

Zero ruchu sieciowego: `requests.get` podstawiony wszedzie.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
import requests

import footstats.scrapers.enriched as en


@pytest.fixture(autouse=True)
def cache_w_tmp(tmp_path, monkeypatch):
    """CACHE_DIR na tmp — testy nie zasmiecaja cache/enriched w projekcie."""
    monkeypatch.setattr(en, "CACHE_DIR", tmp_path / "enriched")
    return tmp_path / "enriched"


# ── cache ───────────────────────────────────────────────────────────────────

def test_klucz_cache_sanityzuje_nazwe(cache_w_tmp):
    """Nazwy druzyn maja spacje i znaki spoza ASCII — nie moga trafic do nazwy pliku."""
    sciezka = en._cache_path("fdb_teamid_Górnik Zabrze/1")
    assert "/" not in sciezka.name.replace("\\", "")
    assert sciezka.name.endswith(".json")
    assert " " not in sciezka.name


def test_brak_wpisu_daje_none():
    assert en._cache_get("nie_ma_takiego") is None


def test_zapis_i_odczyt_w_obie_strony():
    en._cache_set("klucz", {"id": 57})
    assert en._cache_get("klucz") == {"id": 57}


def test_wpis_starszy_niz_ttl_ignorowany(cache_w_tmp):
    """Przeterminowany cache to gorsze niz brak — model liczylby na starych skladach."""
    en._cache_set("stary", {"id": 1})
    plik = en._cache_path("stary")
    stara_data = (datetime.now() - timedelta(hours=en.CACHE_TTL_H + 1)).isoformat()
    plik.write_text(json.dumps({"_ts": stara_data, "payload": {"id": 1}}),
                    encoding="utf-8")

    assert en._cache_get("stary") is None


def test_uszkodzony_plik_cache_daje_none(cache_w_tmp):
    en._cache_set("zepsuty", {"x": 1})
    en._cache_path("zepsuty").write_text("{niepoprawny", encoding="utf-8")
    assert en._cache_get("zepsuty") is None


def test_zapis_do_niedostepnego_katalogu_nie_wywala(monkeypatch):
    """Cache to optymalizacja — brak praw do zapisu nie moze zatrzymac pobierania."""
    def _padnij(*a, **k):
        raise OSError("brak uprawnien")

    monkeypatch.setattr(en.Path, "write_text", _padnij)
    en._cache_set("klucz", {"x": 1})          # nie rzuca


# ── _fdb_get ────────────────────────────────────────────────────────────────

class _Odp:
    def __init__(self, status=200, dane=None):
        self.status_code = status
        self._dane = dane if dane is not None else {}

    def json(self):
        return self._dane


def test_fdb_bez_klucza_nie_rusza_sieci(monkeypatch):
    wolania = []
    monkeypatch.setattr(en, "FOOTBALL_API_KEY", "")
    monkeypatch.setattr(requests, "get", lambda *a, **k: wolania.append(a))

    assert en._fdb_get("/teams/") is None
    assert wolania == []


def test_fdb_200_zwraca_json(monkeypatch):
    monkeypatch.setattr(en, "FOOTBALL_API_KEY", "klucz")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Odp(200, {"teams": [1]}))
    assert en._fdb_get("/teams/") == {"teams": [1]}


def test_fdb_inny_status_zwraca_none(monkeypatch):
    monkeypatch.setattr(en, "FOOTBALL_API_KEY", "klucz")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Odp(429))
    assert en._fdb_get("/teams/") is None


def test_fdb_blad_sieci_zwraca_none(monkeypatch):
    monkeypatch.setattr(en, "FOOTBALL_API_KEY", "klucz")

    def _padnij(*a, **k):
        raise requests.RequestException("timeout")

    monkeypatch.setattr(requests, "get", _padnij)
    assert en._fdb_get("/teams/") is None


def test_fdb_wysyla_token_w_naglowku(monkeypatch):
    monkeypatch.setattr(en, "FOOTBALL_API_KEY", "tajny")
    zebrane = {}

    def _get(url, headers=None, timeout=None):
        zebrane.update(url=url, headers=headers)
        return _Odp(200, {})

    monkeypatch.setattr(requests, "get", _get)
    en._fdb_get("/teams/57")

    assert zebrane["headers"]["X-Auth-Token"] == "tajny"
    assert zebrane["url"].endswith("/v4/teams/57")


# ── _szukaj_team_id ─────────────────────────────────────────────────────────

@pytest.fixture
def fdb(monkeypatch):
    """Podstawia _fdb_get; kolejne wywolania zwracaja kolejne przygotowane odpowiedzi."""
    stan = {"odpowiedzi": [], "endpointy": []}

    def _get(endpoint):
        stan["endpointy"].append(endpoint)
        return stan["odpowiedzi"].pop(0) if stan["odpowiedzi"] else None

    monkeypatch.setattr(en, "_fdb_get", _get)
    return stan


def test_team_id_z_wyszukiwania_po_nazwie(fdb):
    fdb["odpowiedzi"] = [{"teams": [{"id": 57, "name": "Arsenal FC"}]}]
    assert en._szukaj_team_id("Arsenal") == 57


def test_team_id_zapisywany_do_cache(fdb):
    fdb["odpowiedzi"] = [{"teams": [{"id": 57, "name": "Arsenal FC"}]}]
    en._szukaj_team_id("Arsenal")

    fdb["odpowiedzi"] = []                    # kolejne pobranie zwrocilo by None
    assert en._szukaj_team_id("Arsenal") == 57, "nie uzyto cache"


def test_cache_oszczedza_zapytania(fdb):
    fdb["odpowiedzi"] = [{"teams": [{"id": 57, "name": "Arsenal FC"}]}]
    en._szukaj_team_id("Arsenal")
    ile = len(fdb["endpointy"])

    en._szukaj_team_id("Arsenal")
    assert len(fdb["endpointy"]) == ile, "drugie wywolanie poszlo po sieci"


def test_fallback_na_pelna_liste_druzyn(fdb):
    """Gdy wyszukiwanie po nazwie nic nie da, przeszukujemy caly katalog."""
    fdb["odpowiedzi"] = [
        {"teams": []},
        {"teams": [{"id": 66, "name": "Manchester United FC", "shortName": "Man United"}]},
    ]
    assert en._szukaj_team_id("Manchester United") == 66


def test_fallback_dopasowuje_po_short_name(fdb):
    fdb["odpowiedzi"] = [
        {"teams": []},
        {"teams": [{"id": 61, "name": "Chelsea Football Club", "shortName": "Chelsea"}]},
    ]
    assert en._szukaj_team_id("chelsea") == 61


def test_nieznana_druzyna_daje_none(fdb):
    fdb["odpowiedzi"] = [{"teams": []}, {"teams": [{"id": 1, "name": "Inna", "shortName": "I"}]}]
    assert en._szukaj_team_id("Nieistniejacy Klub") is None


def test_brak_odpowiedzi_daje_none(fdb):
    fdb["odpowiedzi"] = []
    assert en._szukaj_team_id("Cokolwiek") is None


# ── sprawdz_murawe ──────────────────────────────────────────────────────────

def test_murawa_nieznanej_druzyny_to_false():
    assert en.sprawdz_murawe("Klub Bez Wpisu") is False


def test_murawa_czyta_mape(monkeypatch):
    monkeypatch.setitem(en.SZTUCZNA_MURAWA, "Testowy Klub", True)
    assert en.sprawdz_murawe("Testowy Klub") is True


# ── enrich_match_data ───────────────────────────────────────────────────────

@pytest.fixture
def zrodla(monkeypatch):
    """Podstawia wszystkie szesc pobran; domyslnie kazde zwraca dane."""
    stan = {
        "kontuzje": {"injured": 2},
        "konferencje": {"cytat": "gramy o wszystko"},
        "xg": {"xg_avg": 1.6},
    }

    def _wolaj(klucz):
        def _fn(team, *a, **k):
            wartosc = stan[klucz]
            if isinstance(wartosc, Exception):
                raise wartosc
            return wartosc
        return _fn

    monkeypatch.setattr(en, "pobierz_kontuzje", _wolaj("kontuzje"))
    monkeypatch.setattr(en, "pobierz_konferencje", _wolaj("konferencje"))
    monkeypatch.setattr(en, "pobierz_forme_xg", _wolaj("xg"))
    return stan


def test_zwraca_komplet_kluczy(zrodla):
    wynik = en.enrich_match_data("Legia", "Lech", "2026-08-02")
    for klucz in ("meta", "home_injuries", "away_injuries", "home_press",
                  "away_press", "home_xg", "away_xg", "murawa"):
        assert klucz in wynik, f"brak klucza {klucz}"


def test_meta_ma_druzyny_date_i_znacznik_czasu(zrodla):
    meta = en.enrich_match_data("Legia", "Lech", "2026-08-02")["meta"]
    assert meta["home"] == "Legia" and meta["away"] == "Lech"
    assert meta["match_date"] == "2026-08-02"
    assert meta["fetched_at"]


def test_dziala_bez_daty_meczu(zrodla):
    assert en.enrich_match_data("Legia", "Lech")["meta"]["match_date"] is None


def test_wypelnia_dane_z_obu_stron(zrodla):
    wynik = en.enrich_match_data("Legia", "Lech")
    assert wynik["home_injuries"] == {"injured": 2}
    assert wynik["away_injuries"] == {"injured": 2}
    assert wynik["home_xg"] == {"xg_avg": 1.6}


def test_awaria_jednego_zrodla_nie_kasuje_reszty(zrodla):
    """SEDNO: padnieta konferencja nie moze zabrac kontuzji i xG."""
    zrodla["konferencje"] = ValueError("scraper padl")

    wynik = en.enrich_match_data("Legia", "Lech")

    assert wynik["home_press"] is None
    assert wynik["home_injuries"] == {"injured": 2}, "utracono dane innego zrodla"
    assert wynik["home_xg"] == {"xg_avg": 1.6}


def test_murawa_liczona_dla_obu_druzyn(zrodla, monkeypatch):
    monkeypatch.setitem(en.SZTUCZNA_MURAWA, "Sztuczna", True)
    murawa = en.enrich_match_data("Sztuczna", "Naturalna")["murawa"]
    assert murawa["home_artificial"] is True
    assert murawa["away_artificial"] is False


def test_brak_danych_ze_zrodla_daje_none_nie_wyjatek(zrodla):
    zrodla["xg"] = None
    wynik = en.enrich_match_data("Legia", "Lech")
    assert wynik["home_xg"] is None
    assert wynik["home_injuries"] is not None
