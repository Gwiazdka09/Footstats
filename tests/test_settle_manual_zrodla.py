"""D5 — dziennik kuponów sięga po wyniki do źródeł zewnętrznych (pod flagą).

PROBLEM, KTÓRY TO ROZWIĄZUJE: `settle_manual_coupons` rozlicza wyłącznie
z NASZYCH `predictions` i jest all-legs-or-nothing. Kupon na mecz, którego sami
nie typowaliśmy, nie rozliczy się NIGDY — zostaje ACTIVE do końca świata.

Zmierzone na produkcji 2026-08-24 na sześciu kuponach dziennika (#164-169):
predykcję ma 1 noga z 12. Powód strukturalny, nie awaria — kupony powstają
z `quick_picks`/Bzzoiro (~30 kandydatów dziennie), a `predictions` zapisuje
tylko ścieżka `top3`/`kupon_d` (24.08: 2 wiersze, 23.08: 13). Dwa ledwo
zachodzące na siebie zbiory meczów.

DLACZEGO POD FLAGĄ, A NIE NA STAŁE: `_find_leg_result` odpytuje API-Football
i football-data, czyli kosztuje wywołania limitowanego planu. Domyślnie OFF —
zero zmiany zachowania. Regresji pilnuje `test_settle_manual_coupons.py`, którego
fikstura wysadza test, gdy `_find_leg_result` zostanie wywołane.

NASZE DANE MAJĄ PIERWSZEŃSTWO także przy włączonej fladze: są darmowe i pochodzą
z tego samego przebiegu co typ. Zewnętrzne źródła to fallback, nie zamiennik.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

import footstats.core.backtest as backtest
import footstats.core.coupon_settlement as settlement
import footstats.core.coupon_tracker as coupon_tracker
import footstats.core.match_linker as match_linker
from footstats.core.match_linker import LinkResult

from tests.test_settle_manual_coupons import _SCHEMA, _SQLiteConn

FLAGA = "MANUAL_SETTLE_EXTERNAL"
DATA = "2026-07-20"


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Własna plikowa SQLite; zewnętrzne źródła zawsze przez stub — zero sieci."""
    sciezka = str(tmp_path / "test.db")
    setup = sqlite3.connect(sciezka)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    monkeypatch.setattr(backtest, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(backtest, "init_db", lambda: None)
    monkeypatch.setattr(coupon_tracker, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(coupon_tracker, "init_coupon_tables", lambda: None)
    import footstats.scrapers.results_updater as ru
    monkeypatch.setattr(ru, "_get_api_key", lambda: "klucz-af")
    monkeypatch.setenv("FOOTBALL_API_KEY", "klucz-fdb")
    return sciezka


@pytest.fixture
def bez_naszych(monkeypatch):
    """`link_leg` nie znajduje predykcji — stan 11 z 12 nóg serii 4."""
    monkeypatch.setattr(match_linker, "link_leg",
                        lambda *a, **k: LinkResult(matched=False, match_confidence="none",
                                                   prediction=None, reason="brak"))


@pytest.fixture
def zewnetrzne(monkeypatch):
    """Stub `_find_leg_result` z licznikiem wywołań i podglądem cache."""
    stan = {"wolania": [], "wyniki": {}, "rzuca": False, "cache_id": set()}

    def _stub(home, away, mdate, fixtures_cache, fdb_cache, api_key, fdb_key):
        stan["wolania"].append((home, away, mdate, api_key, fdb_key))
        stan["cache_id"].add(id(fixtures_cache))
        if stan["rzuca"]:
            raise OSError("API-Football niedostepne")
        return stan["wyniki"].get(f"{home} vs {away}")

    monkeypatch.setattr(settlement, "_find_leg_result", _stub)
    return stan


def _kupon(sciezka: str, nogi: list[dict], kurs: float = 2.0) -> int:
    conn = sqlite3.connect(sciezka)
    cur = conn.execute(
        "INSERT INTO coupons (kupon_type, status, legs_json, total_odds, stake_pln,"
        " match_date_first, user_id) VALUES ('manual','ACTIVE',?,?,10.0,?,1)",
        (json.dumps(nogi, ensure_ascii=False), kurs, DATA),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def _status(sciezka: str, cid: int) -> str:
    conn = sqlite3.connect(sciezka)
    s = conn.execute("SELECT status FROM coupons WHERE id=?", (cid,)).fetchone()[0]
    conn.close()
    return s


def _bankroll(sciezka: str) -> float:
    conn = sqlite3.connect(sciezka)
    b = conn.execute("SELECT balance FROM bankroll_state WHERE user_id=1").fetchone()[0]
    conn.close()
    return b


def _noga(home: str, away: str, tip: str = "1") -> dict:
    return {"home": home, "away": away, "tip": tip, "odds": 1.5}


def _predykcja(wynik: str) -> dict:
    return {"id": 1, "team_home": "Legia", "team_away": "Lech", "match_date": DATA,
            "ai_tip": "1", "actual_result": wynik}


# ── flaga OFF = dzisiejsze zachowanie, co do joty ───────────────────────────

def test_flaga_off_nie_siega_na_zewnatrz(db, bez_naszych, zewnetrzne, monkeypatch):
    monkeypatch.delenv(FLAGA, raising=False)
    cid = _kupon(db, [_noga("Bologna", "Lazio")])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert zewnetrzne["wolania"] == [], "domyslnie zero ruchu do zewnetrznych API"
    assert _status(db, cid) == "ACTIVE"
    assert stats["settled"] == 0 and stats["skipped"] == 1


@pytest.mark.parametrize("wartosc", ["0", "", "false", "nie"])
def test_tylko_jawne_wlaczenie_otwiera_zrodla(db, bez_naszych, zewnetrzne,
                                              monkeypatch, wartosc: str):
    monkeypatch.setenv(FLAGA, wartosc)

    settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert zewnetrzne["wolania"] == []


# ── flaga ON — sedno D5 ─────────────────────────────────────────────────────

def test_kupon_bez_naszej_predykcji_rozlicza_sie_z_zewnatrz(db, bez_naszych,
                                                            zewnetrzne, monkeypatch):
    """Dokladnie stan serii 4: zadnej predykcji, wynik istnieje u zrodel."""
    monkeypatch.setenv(FLAGA, "1")
    zewnetrzne["wyniki"] = {"Bologna vs Lazio": "1-0"}
    cid = _kupon(db, [_noga("Bologna", "Lazio", "1")])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert _status(db, cid) == "WON"
    assert stats["settled"] == 1
    assert stats["z_zewnatrz"] == 1


def test_przegrana_noga_daje_lost(db, bez_naszych, zewnetrzne, monkeypatch):
    monkeypatch.setenv(FLAGA, "1")
    zewnetrzne["wyniki"] = {"Bologna vs Lazio": "0-2"}
    cid = _kupon(db, [_noga("Bologna", "Lazio", "1")])

    settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert _status(db, cid) == "LOST"


def test_nasze_dane_maja_pierwszenstwo(db, zewnetrzne, monkeypatch):
    """Predykcja z wynikiem jest darmowa — nie wolno za nia placic zapytaniem."""
    monkeypatch.setenv(FLAGA, "1")
    monkeypatch.setattr(match_linker, "link_leg",
                        lambda *a, **k: LinkResult(matched=True, match_confidence="exact",
                                                   prediction=_predykcja("2-0"),
                                                   reason="exact"))
    cid = _kupon(db, [_noga("Legia", "Lech", "1")])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert zewnetrzne["wolania"] == [], "mielismy wynik u siebie, a poszlo zapytanie"
    assert _status(db, cid) == "WON"
    assert stats["z_zewnatrz"] == 0


def test_all_or_nothing_zostaje_przy_wlaczonej_fladze(db, bez_naszych,
                                                      zewnetrzne, monkeypatch):
    """Jedna noga bez wyniku → caly kupon ACTIVE. Zero rozliczen czesciowych."""
    monkeypatch.setenv(FLAGA, "1")
    zewnetrzne["wyniki"] = {"Bologna vs Lazio": "1-0"}   # druga noga bez wyniku
    cid = _kupon(db, [_noga("Bologna", "Lazio"), _noga("Roma", "Fiorentina")])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert _status(db, cid) == "ACTIVE"
    assert stats["settled"] == 0 and stats["skipped"] == 1


def test_awaria_zrodla_nie_rozlicza_i_nie_wywala(db, bez_naszych, zewnetrzne,
                                                 monkeypatch):
    """Kupon zamkniety na podstawie bledu sieci bylby gorszy niz niezamkniety."""
    monkeypatch.setenv(FLAGA, "1")
    zewnetrzne["rzuca"] = True
    cid = _kupon(db, [_noga("Bologna", "Lazio")])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert _status(db, cid) == "ACTIVE"
    assert stats["settled"] == 0


def test_dry_run_nie_zmienia_statusu(db, bez_naszych, zewnetrzne, monkeypatch):
    monkeypatch.setenv(FLAGA, "1")
    zewnetrzne["wyniki"] = {"Bologna vs Lazio": "1-0"}
    cid = _kupon(db, [_noga("Bologna", "Lazio")])

    stats = settlement.settle_manual_coupons(dry_run=True, verbose=False)

    assert _status(db, cid) == "ACTIVE"
    assert stats["settled"] == 1


# ── koszt zapytan: cache dzielony miedzy nogami i kuponami ──────────────────

def test_cache_dzielony_miedzy_kuponami(db, bez_naszych, zewnetrzne, monkeypatch):
    """Osobny cache na kupon oznaczalby N-krotnie wiecej zapytan o te sama date."""
    monkeypatch.setenv(FLAGA, "1")
    _kupon(db, [_noga("Bologna", "Lazio")])
    _kupon(db, [_noga("Roma", "Fiorentina")])

    settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert len(zewnetrzne["wolania"]) == 2
    assert len(zewnetrzne["cache_id"]) == 1, "kazdy kupon dostal wlasny cache"


def test_klucze_przekazane_do_zrodel(db, bez_naszych, zewnetrzne, monkeypatch):
    monkeypatch.setenv(FLAGA, "1")
    _kupon(db, [_noga("Bologna", "Lazio")])

    settlement.settle_manual_coupons(dry_run=False, verbose=False)

    _, _, mdate, api_key, fdb_key = zewnetrzne["wolania"][0]
    assert (mdate, api_key, fdb_key) == (DATA, "klucz-af", "klucz-fdb")


# ── dziennik zostaje neutralny dla bankrolla ────────────────────────────────

def test_bankroll_nietkniety(db, bez_naszych, zewnetrzne, monkeypatch):
    monkeypatch.setenv(FLAGA, "1")
    zewnetrzne["wyniki"] = {"Bologna vs Lazio": "1-0"}
    przed = _bankroll(db)
    _kupon(db, [_noga("Bologna", "Lazio")])

    settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert _bankroll(db) == przed


def test_kupony_nie_manual_dalej_pomijane(db, zewnetrzne, monkeypatch):
    """Flaga otwiera zrodla dla DZIENNIKA, nie zmienia zakresu funkcji."""
    monkeypatch.setenv(FLAGA, "1")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO coupons (kupon_type, status, legs_json, total_odds, stake_pln,"
        " match_date_first, user_id) VALUES ('SINGLE','ACTIVE',?,2.0,10.0,?,1)",
        (json.dumps([_noga("Bologna", "Lazio")]), DATA),
    )
    conn.commit()
    conn.close()

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert zewnetrzne["wolania"] == []
    assert stats["settled"] == 0 and stats["skipped"] == 0
