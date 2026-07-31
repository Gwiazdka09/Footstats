"""test_results_updater_pending.py — `update_pending`: rozliczanie zaleglych meczow.

PO CO: to ostatni duzy kawalek sciezki rozliczen bez testow. Ta funkcja PISZE
wyniki do bazy, a z nich liczy sie accuracy i kalibracja — blad tutaj truje dane
wstecz i nie da sie go zauwazyc po zachowaniu pipeline'u.

Cztery rzeczy krytyczne:
  * `dry_run` NIE MOZE PISAC. To jedyny bezpieczny sposob sprawdzenia, co
    funkcja zrobi, zanim ruszy na produkcji.
  * OKNO CZASOWE: tylko mecze juz rozegrane (data < dzis) i nie starsze niz
    `days_back`. Mecz dzisiejszy moze jeszcze trwac — rozliczenie go teraz
    zapisaloby wynik z pierwszej polowy.
  * BUDZET 75 zapytan (bufor 25 ze 100/dzien). Po przekroczeniu przechodzimy
    na scraper zamiast wchodzic w 429.
  * CACHE per (data, liga) — bez niego 20 meczow z jednej kolejki to 20 zapytan
    zamiast jednego.

Zaden test nie dotyka bazy ani sieci; `time.sleep` (rate limit 0.5s) podstawiony.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import footstats.scrapers.results_updater as ru


def _dzien(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).isoformat()


def _pending(mid=1, home="Legia", away="Lech", offset=-1,
             liga="Ekstraklasa", **kw) -> dict:
    return {"id": mid, "team_home": home, "team_away": away,
            "match_date": _dzien(offset), "league": liga, "ai_tip": "1", **kw}


def _fixture(home="Legia", away="Lech", hg=2, ag=1) -> dict:
    return {
        "fixture": {"id": 1, "status": {"short": "FT"}},
        "goals": {"home": hg, "away": ag},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {},
    }


@pytest.fixture
def env(monkeypatch):
    """Podstawia klucz, baze, oba zrodla fixtures, scraper i Telegram."""
    stan = {
        "pending": [],
        "fixtures_by_date": [],     # wynik _fetch_fixtures_by_date
        "fixtures_liga": [],        # wynik _fetch_fixtures
        "scraper": None,            # wynik get_match_result
        "update_blad": None,        # wyjatek z update_result
        "zapisane": [],             # (id, wynik, stats)
        "telegram": [],
        "zapytania_date": [],
        "zapytania_liga": [],
    }

    monkeypatch.setattr(ru, "_get_api_key", lambda: "klucz-testowy")
    monkeypatch.setattr("time.sleep", lambda s: None)

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "init_db", lambda: None)
    monkeypatch.setattr(bt, "get_pending_results", lambda: list(stan["pending"]))

    def _update(mid, wynik, match_stats=None):
        if stan["update_blad"]:
            raise stan["update_blad"]
        stan["zapisane"].append((mid, wynik, match_stats))
        return {"id": mid, "tip_correct": 1}

    monkeypatch.setattr(bt, "update_result", _update)

    def _by_date(key, date_str):
        stan["zapytania_date"].append(date_str)
        return list(stan["fixtures_by_date"])

    def _by_liga(key, league_id, date_str):
        stan["zapytania_liga"].append((league_id, date_str))
        return list(stan["fixtures_liga"])

    monkeypatch.setattr(ru, "_fetch_fixtures_by_date", _by_date)
    monkeypatch.setattr(ru, "_fetch_fixtures", _by_liga)

    # `_znajdz_wynik` -> `_fixture_to_result(fix, api_key)` -> `_fetch_match_stats`,
    # ktore bije po sieci po statystyki meczu. Bez tego podstawienia guard
    # z conftest slusznie blokuje test (i tak wlasnie go zlapal).
    monkeypatch.setattr(ru, "_fetch_match_stats",
                        lambda key, fid: dict(stan.get("statystyki") or {}))

    import footstats.scrapers.flashscore_results as fs
    monkeypatch.setattr(fs, "get_match_result",
                        lambda h, a, d: stan["scraper"], raising=False)

    import footstats.utils.telegram_notify as tg
    monkeypatch.setattr(tg, "telegram_dostepny", lambda: True, raising=False)
    monkeypatch.setattr(tg, "send_wynik_update",
                        lambda *a: stan["telegram"].append(a), raising=False)

    return stan


# ── brak klucza / brak danych ───────────────────────────────────────────────

def test_brak_klucza_konczy_bez_zapytan(monkeypatch, capsys):
    monkeypatch.setattr(ru, "_get_api_key", lambda: None)
    wynik = ru.update_pending()
    assert wynik == {"updated": 0, "not_found": 0, "errors": 0}
    assert "Brak APISPORTS_KEY" in capsys.readouterr().out


def test_brak_pending_konczy_bez_zapytan(env):
    wynik = ru.update_pending()
    assert wynik == {"updated": 0, "not_found": 0, "errors": 0}
    assert env["zapytania_date"] == []


# ── okno czasowe ────────────────────────────────────────────────────────────

def test_mecz_dzisiejszy_pomijany(env):
    """Moze jeszcze trwac — rozliczenie zapisaloby wynik z pierwszej polowy."""
    env["pending"] = [_pending(offset=0)]
    ru.update_pending()
    assert env["zapytania_date"] == []


def test_mecz_przyszly_pomijany(env):
    env["pending"] = [_pending(offset=3)]
    ru.update_pending()
    assert env["zapytania_date"] == []


def test_mecz_wczorajszy_sprawdzany(env):
    env["pending"] = [_pending(offset=-1)]
    ru.update_pending(days_back=2)
    assert env["zapytania_date"] == [_dzien(-1)]


def test_mecz_starszy_niz_days_back_pomijany(env):
    """Stare zaleglosci nie maja juz fixtures w API — nie palimy na nie budzetu."""
    env["pending"] = [_pending(offset=-10)]
    ru.update_pending(days_back=2)
    assert env["zapytania_date"] == []


def test_days_back_rozszerza_okno(env):
    env["pending"] = [_pending(offset=-10)]
    ru.update_pending(days_back=30)
    assert env["zapytania_date"] == [_dzien(-10)]


# ── zrodlo 0: fixtures po dacie ─────────────────────────────────────────────

def test_znajduje_wynik_z_fixtures_po_dacie(env):
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture(hg=3, ag=0)]

    wynik = ru.update_pending()

    assert wynik["updated"] == 1
    assert env["zapisane"][0][1] == "3-0"


def test_nie_pyta_o_lige_gdy_znalazl_po_dacie(env):
    """Oszczednosc: trafienie w zrodle 0 konczy szukanie."""
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture()]

    ru.update_pending()
    assert env["zapytania_liga"] == []


def test_cache_daty_dziala_dla_wielu_meczow(env):
    """SEDNO oszczedzania: 5 meczow z jednej kolejki = JEDNO zapytanie."""
    env["pending"] = [_pending(mid=i, home=f"D{i}") for i in range(5)]
    env["fixtures_by_date"] = []

    ru.update_pending()
    assert env["zapytania_date"] == [_dzien(-1)], "cache daty nie zadzialal"


# ── zrodlo 1: fixtures per liga ─────────────────────────────────────────────

def test_pyta_o_lige_gdy_brak_po_dacie(env):
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = []
    env["fixtures_liga"] = [_fixture(hg=1, ag=1)]

    wynik = ru.update_pending()

    assert env["zapytania_liga"], "nie sprobowano zapytania per liga"
    assert wynik["updated"] == 1
    assert env["zapisane"][0][1] == "1-1"


def test_nieznana_liga_nie_generuje_zapytan(env):
    """`_liga_ids_dla_nazwy` zwraca [] — nie strzelamy w ciemno."""
    env["pending"] = [_pending(liga="Klasa Okregowa")]
    ru.update_pending()
    assert env["zapytania_liga"] == []


# ── zrodlo 2: scraper ───────────────────────────────────────────────────────

def test_scraper_jako_ostatnia_deska(env, capsys):
    env["pending"] = [_pending()]
    env["scraper"] = "2-1"

    wynik = ru.update_pending()

    assert wynik["updated"] == 1
    assert env["zapisane"][0][1] == "2-1"
    assert "SCRAPER FALLBACK" in capsys.readouterr().out


def test_scraper_nie_dostarcza_statystyk(env):
    """Scraper oddaje sam wynik — statystyki musza byc puste, nie zmyslone."""
    env["pending"] = [_pending()]
    env["scraper"] = "2-1"

    ru.update_pending()
    assert env["zapisane"][0][2] == {}


def test_brak_wyniku_liczony_jako_not_found(env, capsys):
    env["pending"] = [_pending()]
    wynik = ru.update_pending()

    assert wynik["not_found"] == 1
    assert wynik["updated"] == 0
    assert "NOT FOUND" in capsys.readouterr().out


def test_awaria_scrapera_nie_wywala_petli(env, monkeypatch):
    import footstats.scrapers.flashscore_results as fs

    def _wybuch(h, a, d):
        raise OSError("scraper padl")

    monkeypatch.setattr(fs, "get_match_result", _wybuch, raising=False)
    env["pending"] = [_pending(mid=1), _pending(mid=2, home="Wisła")]

    wynik = ru.update_pending()
    assert wynik["not_found"] == 2


# ── dry_run ─────────────────────────────────────────────────────────────────

def test_dry_run_nie_pisze_do_bazy(env, capsys):
    """KRYTYCZNE: jedyny bezpieczny sposob sprawdzenia, co funkcja zrobi."""
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture()]

    wynik = ru.update_pending(dry_run=True)

    assert wynik["updated"] == 1, "dry-run ma raportowac, co BY zrobil"
    assert env["zapisane"] == [], "dry-run zapisal do bazy"
    assert "[DRY]" in capsys.readouterr().out


def test_dry_run_nie_wysyla_telegrama(env):
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture()]

    ru.update_pending(dry_run=True)
    assert env["telegram"] == []


# ── zapis i powiadomienia ───────────────────────────────────────────────────

def test_udany_zapis_wysyla_telegram(env):
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture()]

    ru.update_pending()
    assert len(env["telegram"]) == 1
    assert "Legia vs Lech" in env["telegram"][0]


def test_awaria_telegrama_nie_cofa_zapisu(env, monkeypatch):
    """Powiadomienie to dodatek — jego blad nie moze podwazyc rozliczenia."""
    import footstats.utils.telegram_notify as tg

    def _wybuch(*a):
        raise OSError("bot padl")

    monkeypatch.setattr(tg, "send_wynik_update", _wybuch, raising=False)
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture()]

    wynik = ru.update_pending()
    assert wynik["updated"] == 1
    assert len(env["zapisane"]) == 1


def test_blad_zapisu_liczony_jako_error(env):
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture()]
    env["update_blad"] = RuntimeError("baza padla")

    wynik = ru.update_pending()
    assert wynik["errors"] == 1
    assert wynik["updated"] == 0


def test_blad_jednego_zapisu_nie_przerywa_reszty(env):
    env["pending"] = [_pending(mid=1), _pending(mid=2)]
    env["fixtures_by_date"] = [_fixture()]
    env["update_blad"] = RuntimeError("baza padla")

    wynik = ru.update_pending()
    assert wynik["errors"] == 2, "petla stanela po pierwszym bledzie zapisu"


# ── podsumowanie ────────────────────────────────────────────────────────────

def test_podsumowanie_drukowane(env, capsys):
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture()]

    ru.update_pending()
    out = capsys.readouterr().out
    assert "Zaktualizowano: 1" in out
    assert "Requesty API" in out


def test_verbose_false_nie_drukuje(env, capsys):
    env["pending"] = [_pending()]
    env["fixtures_by_date"] = [_fixture()]

    ru.update_pending(verbose=False)
    assert "Zaktualizowano" not in capsys.readouterr().out
