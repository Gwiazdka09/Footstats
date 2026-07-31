"""test_daily_phases_kursy.py — trzystopniowy fallback kursow.

PO CO: kursy decyduja o EV, czyli o tym, czy typ w ogole trafi do kuponu.
Lancuch ma trzy zrodla o rosnacym koszcie:

    1. API-Football  — reuse klucza + budzetu (100 req/dzien)
    2. The Odds API  — requests-only, cala liga w jednym zapytaniu
    3. SofaScore     — Playwright, najdrozsze, w cloud draft nie istnieje

Zasada, ktora MUSI trzymac na kazdym stopniu: **nigdy nie nadpisuj istniejacych
kursow**. Kursy Bzzoiro sa podstawowe; gdyby tanszy fallback je nadpisywal,
liczylibysmy EV z gorszego zrodla i nikt by nie zauwazyl — kurs nadal by byl.

Drugi niezmiennik: lancuch ma sie ZATRZYMAC, gdy braki sa uzupelnione.
Kazde zbedne wejscie w kolejny stopien to spalony budzet albo uruchomiona
przegladarka.
"""
from __future__ import annotations

import pytest

import footstats.core.daily_phases as dp


def _mecz(gospodarz="Legia", goscie="Lech", odds=None, **kw) -> dict:
    m = {"gospodarz": gospodarz, "goscie": goscie, "data": "2026-08-02", **kw}
    if odds is not None:
        m["odds"] = odds
    return m


_KOMPLET = {"home": 1.85, "draw": 3.4, "away": 4.2}


# ── _uzupelnij_kursy ────────────────────────────────────────────────────────

def test_dopisuje_brakujace_klucze():
    w = _mecz(odds={"home": 1.85})
    assert dp._uzupelnij_kursy(w, {"draw": 3.4, "away": 4.2}) is True
    assert w["odds"] == {"home": 1.85, "draw": 3.4, "away": 4.2}


def test_nie_nadpisuje_istniejacych():
    """SEDNO: kursy Bzzoiro sa podstawowe, fallback tylko uzupelnia."""
    w = _mecz(odds={"home": 1.85})
    dp._uzupelnij_kursy(w, {"home": 9.99, "draw": 3.4})
    assert w["odds"]["home"] == 1.85, "fallback nadpisal kurs zrodla podstawowego"
    assert w["odds"]["draw"] == 3.4


def test_brak_kursow_zrodlowych_nic_nie_robi():
    w = _mecz(odds={"home": 1.85})
    assert dp._uzupelnij_kursy(w, None) is False
    assert dp._uzupelnij_kursy(w, {}) is False
    assert w["odds"] == {"home": 1.85}


def test_mecz_bez_kursow_dostaje_komplet():
    w = _mecz()
    dp._uzupelnij_kursy(w, _KOMPLET)
    assert w["odds"] == _KOMPLET


def test_dodatkowe_rynki_tez_dopisywane():
    w = _mecz(odds=dict(_KOMPLET))
    dp._uzupelnij_kursy(w, {"btts": 1.9, "over_2_5": 1.75})
    assert w["odds"]["btts"] == 1.9


# ── _wzbogac_o_kursy_fallback: filtrowanie ──────────────────────────────────

@pytest.fixture
def lancuch(monkeypatch):
    """Podstawia wszystkie trzy stopnie. Domyslnie kazdy nic nie znajduje."""
    stan = {
        "af": None,            # wynik fetch_odds_af (albo Exception)
        "af_wywolania": [],
        "odds_api": 0,         # ile uzupelnil dolacz_kursy_odds_api
        "odds_api_wywolania": [],
        "playwright": False,   # czy SofaScore dostepny
    }

    def _af(g, a, data):
        stan["af_wywolania"].append((g, a))
        if isinstance(stan["af"], Exception):
            raise stan["af"]
        return stan["af"]

    monkeypatch.setattr(dp, "fetch_odds_af", _af)

    import footstats.scrapers.odds_api as oa

    def _oa(braki):
        stan["odds_api_wywolania"].append(len(braki))
        if isinstance(stan["odds_api"], Exception):
            raise stan["odds_api"]
        for w in braki[:stan["odds_api"]]:
            dp._uzupelnij_kursy(w, _KOMPLET)
        return stan["odds_api"]

    monkeypatch.setattr(oa, "dolacz_kursy_odds_api", _oa)

    import footstats.scrapers.sofascore_odds as so
    monkeypatch.setattr(so, "PLAYWRIGHT_OK", stan["playwright"], raising=False)
    return stan


def test_mecz_z_kompletnymi_kursami_pomijany(lancuch):
    """Nie palimy budzetu na mecze, ktore juz maja kursy."""
    dp._wzbogac_o_kursy_fallback([_mecz(odds=dict(_KOMPLET))])
    assert lancuch["af_wywolania"] == []


@pytest.mark.parametrize("niepelne", [
    {"home": 1.85, "draw": 3.4},          # brak away
    {"home": 1.85, "away": 4.2},          # brak draw
    {"draw": 3.4, "away": 4.2},           # brak home
    {"home": 1.85, "draw": None, "away": 4.2},   # pusta wartosc
])
def test_niepelne_kursy_kwalifikuja_do_fallbacku(lancuch, niepelne):
    """Kurs bez kompletu 1X2 jest bezuzyteczny — musi wejsc do uzupelniania."""
    dp._wzbogac_o_kursy_fallback([_mecz(odds=niepelne)])
    assert lancuch["af_wywolania"], f"mecz z {niepelne} nie trafil do fallbacku"


def test_pusta_lista_nie_wywala(lancuch):
    dp._wzbogac_o_kursy_fallback([])
    assert lancuch["af_wywolania"] == []


def test_top_n_ogranicza_liczbe_zapytan(lancuch):
    """Twardy limit budzetu: przy 10 brakach i top_n=3 leca 3 zapytania."""
    braki = [_mecz(gospodarz=f"D{i}") for i in range(10)]
    dp._wzbogac_o_kursy_fallback(braki, top_n=3)
    assert len(lancuch["af_wywolania"]) == 3


def test_mecz_bez_nazw_druzyn_pomijany(lancuch):
    dp._wzbogac_o_kursy_fallback([_mecz(gospodarz="", goscie="")])
    assert lancuch["af_wywolania"] == []


# ── stopien 1: API-Football ─────────────────────────────────────────────────

def test_af_uzupelnia_kursy(lancuch, capsys):
    lancuch["af"] = _KOMPLET
    mecze = [_mecz()]
    dp._wzbogac_o_kursy_fallback(mecze)

    assert mecze[0]["odds"] == _KOMPLET
    assert "uzupełniono 1/1" in capsys.readouterr().out


def test_af_nie_nadpisuje_kursow_bzzoiro(lancuch):
    lancuch["af"] = {"home": 9.99, "draw": 3.4, "away": 4.2}
    mecze = [_mecz(odds={"home": 1.85})]
    dp._wzbogac_o_kursy_fallback(mecze)

    assert mecze[0]["odds"]["home"] == 1.85


def test_awaria_af_nie_przerywa_petli(lancuch):
    lancuch["af"] = OSError("API padlo")
    dp._wzbogac_o_kursy_fallback([_mecz(gospodarz="A"), _mecz(gospodarz="B")])
    assert len(lancuch["af_wywolania"]) == 2, "petla stanela po pierwszym bledzie"


def test_komplet_z_af_zatrzymuje_lancuch(lancuch):
    """Uzupelnione = koniec. Kolejny stopien to zbedny koszt."""
    lancuch["af"] = _KOMPLET
    dp._wzbogac_o_kursy_fallback([_mecz()])
    assert lancuch["odds_api_wywolania"] == [], "wszedl w Odds API mimo kompletu"


# ── stopien 2: The Odds API ─────────────────────────────────────────────────

def test_odds_api_dostaje_tylko_nadal_brakujace(lancuch):
    lancuch["af"] = None
    dp._wzbogac_o_kursy_fallback([_mecz(gospodarz="A"), _mecz(gospodarz="B")])
    assert lancuch["odds_api_wywolania"] == [2]


def test_odds_api_uzupelnia(lancuch, capsys):
    lancuch["odds_api"] = 1
    mecze = [_mecz()]
    dp._wzbogac_o_kursy_fallback(mecze)

    assert mecze[0]["odds"] == _KOMPLET
    assert "The Odds API" in capsys.readouterr().out


def test_awaria_odds_api_nie_przerywa_lancucha(lancuch):
    lancuch["odds_api"] = KeyError("brak klucza")
    dp._wzbogac_o_kursy_fallback([_mecz()])       # nie rzuca


def test_komplet_z_odds_api_zatrzymuje_przed_sofascore(lancuch, capsys):
    lancuch["odds_api"] = 1
    dp._wzbogac_o_kursy_fallback([_mecz()])
    assert "SofaScore" not in capsys.readouterr().out


# ── stopien 3: SofaScore ────────────────────────────────────────────────────

def test_brak_playwrighta_pomija_sofascore(lancuch, monkeypatch, capsys):
    """W cloud draft Playwright nie istnieje — lancuch ma sie zatrzymac cicho."""
    import footstats.scrapers.sofascore_odds as so
    monkeypatch.setattr(so, "PLAYWRIGHT_OK", False, raising=False)

    dp._wzbogac_o_kursy_fallback([_mecz()])
    assert "Playwright" in capsys.readouterr().out


def test_blad_sesji_sofascore_nie_wywala(lancuch, monkeypatch, capsys):
    import footstats.scrapers.sofascore_odds as so
    import footstats.scrapers.form_scraper as fs
    monkeypatch.setattr(so, "PLAYWRIGHT_OK", True, raising=False)
    monkeypatch.setattr(fs, "_sofa_session", lambda: None, raising=False)

    dp._wzbogac_o_kursy_fallback([_mecz()])
    assert "błąd sesji" in capsys.readouterr().out


def test_sofascore_uzupelnia_i_zamyka_przegladarke(lancuch, monkeypatch):
    """Przegladarka MUSI zostac zamknieta — inaczej job zostawia proces."""
    import footstats.scrapers.sofascore_odds as so
    import footstats.scrapers.form_scraper as fs

    zamkniete = {"browser": False, "playwright": False}

    class _Browser:
        def close(self):
            zamkniete["browser"] = True

    class _P:
        def stop(self):
            zamkniete["playwright"] = True

    monkeypatch.setattr(so, "PLAYWRIGHT_OK", True, raising=False)
    monkeypatch.setattr(so, "fetch_odds",
                        lambda g, a, d, page=None: _KOMPLET, raising=False)
    monkeypatch.setattr(fs, "_sofa_session",
                        lambda: (_P(), _Browser(), object()), raising=False)

    mecze = [_mecz()]
    dp._wzbogac_o_kursy_fallback(mecze)

    assert mecze[0]["odds"] == _KOMPLET
    assert zamkniete["browser"] and zamkniete["playwright"]


def test_przegladarka_zamykana_takze_po_bledzie(lancuch, monkeypatch):
    import footstats.scrapers.sofascore_odds as so
    import footstats.scrapers.form_scraper as fs

    zamkniete = {"browser": False}

    class _Browser:
        def close(self):
            zamkniete["browser"] = True

    class _P:
        def stop(self):
            pass

    def _wybuch(g, a, d, page=None):
        raise RuntimeError("scraper padl")

    monkeypatch.setattr(so, "PLAYWRIGHT_OK", True, raising=False)
    monkeypatch.setattr(so, "fetch_odds", _wybuch, raising=False)
    monkeypatch.setattr(fs, "_sofa_session",
                        lambda: (_P(), _Browser(), object()), raising=False)

    dp._wzbogac_o_kursy_fallback([_mecz()])
    assert zamkniete["browser"], "przegladarka nie zamknieta po bledzie scrapera"
