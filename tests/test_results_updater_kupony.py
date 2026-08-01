"""test_results_updater_kupony.py — `update_active_coupons`: zamykanie kuponow.

PO CO: ta funkcja zamyka kupony i RUSZA BANKROLL. Blad tutaj zapisuje falszywy
bilans, ktorego nie widac po zachowaniu pipeline'u — kupon po prostu ma status.

Najwazniejsza jest logika PARTIAL: jesli CHOC JEDNA noga jest nierozstrzygnieta,
kupon NIE MOZE zostac zamkniety. Przedwczesne zamkniecie zapisaloby wynik
policzony z niekompletnych danych i dopisalo wyplate do bankrolla.

Drugi bezpiecznik: kupony `manual` sa wykluczone z automatu — rozlicza je
uzytkownik przez `/coupon/{id}/result`. Automat nie ma prawa ich dotknac.

Zero dostepu do bazy i sieci: `_connect`, fixtures i scraper podstawione.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
import requests

import footstats.scrapers.results_updater as ru


def _dzien(offset: int) -> str:
    return (datetime.now().date() + timedelta(days=offset)).isoformat()


def _noga(home="Legia", away="Lech", tip="1") -> dict:
    return {"home": home, "away": away, "tip": tip}


def _kupon(cid=1, nogi=None, total_odds=2.0, stake=10.0, offset=-1) -> dict:
    return {
        "id": cid,
        "legs_json": json.dumps(nogi if nogi is not None else [_noga()]),
        "total_odds": total_odds,
        "stake_pln": stake,
        "match_date_first": _dzien(offset),
    }


def _fixture(home="Legia", away="Lech", hg=2, ag=1) -> dict:
    return {
        "fixture": {"id": 1, "status": {"short": "FT"}},
        "goals": {"home": hg, "away": ag},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {},
    }


class _Kursor:
    def __init__(self, wiersze):
        self._wiersze = wiersze

    def fetchall(self):
        return self._wiersze

    def fetchone(self):
        return self._wiersze[0] if self._wiersze else None


class _Conn:
    """Atrapa polaczenia — notuje kazde zapytanie."""

    def __init__(self, kupony, bankroll=100.0):
        self._kupony = kupony
        self._bankroll = bankroll
        self.zapytania: list[tuple] = []

    def execute(self, sql, params=()):
        self.zapytania.append((" ".join(sql.split()), params))
        s = sql.strip().upper()
        if s.startswith("SELECT ID, LEGS_JSON"):
            return _Kursor(self._kupony)
        if "BANKROLL_STATE" in s and s.startswith("SELECT"):
            return _Kursor([{"balance": self._bankroll}])
        return _Kursor([])

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    # pomocnicze dla asercji
    def polecenia(self, prefiks: str) -> list[tuple]:
        return [z for z in self.zapytania
                if z[0].strip().upper().startswith(prefiks)]


@pytest.fixture
def env(monkeypatch):
    stan = {
        "kupony": [],
        "fixtures": [],
        "scraper": None,
        "bankroll": 100.0,
        "conn": None,
        "http": 0,
    }

    monkeypatch.setattr(ru, "_get_api_key", lambda: "klucz")
    monkeypatch.setattr("time.sleep", lambda s: None)

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "init_db", lambda: None)

    def _connect():
        if stan["conn"] is None:
            stan["conn"] = _Conn(stan["kupony"], stan["bankroll"])
        return stan["conn"]

    monkeypatch.setattr(bt, "_connect", _connect)

    class _Odp:
        status_code = 200

        @staticmethod
        def raise_for_status():
            pass

        @staticmethod
        def json():
            return {"response": list(stan["fixtures"])}

    def _get(*a, **k):
        stan["http"] += 1
        return _Odp()

    monkeypatch.setattr(requests, "get", _get)
    monkeypatch.setattr(ru, "_fetch_match_stats", lambda key, fid: {})

    import footstats.scrapers.flashscore_results as fs
    monkeypatch.setattr(fs, "get_match_result",
                        lambda h, a, d: stan["scraper"], raising=False)
    return stan


# ── wejscie ─────────────────────────────────────────────────────────────────

def test_brak_klucza_konczy_bez_zapytan(monkeypatch, capsys):
    monkeypatch.setattr(ru, "_get_api_key", lambda: None)
    assert ru.update_active_coupons() == {"closed": 0, "partial": 0, "errors": 0}
    assert "Brak APISPORTS_KEY" in capsys.readouterr().out


def test_brak_aktywnych_kuponow(env, capsys):
    assert ru.update_active_coupons() == {"closed": 0, "partial": 0, "errors": 0}
    assert "Brak aktywnych" in capsys.readouterr().out


def test_zapytanie_wyklucza_kupony_manualne(env):
    """Kupony manualne rozlicza UZYTKOWNIK — automat nie ma prawa ich dotknac."""
    env["kupony"] = [_kupon()]
    env["fixtures"] = [_fixture()]
    ru.update_active_coupons()

    select = env["conn"].polecenia("SELECT ID, LEGS_JSON")[0][0]
    assert "manual" in select
    assert "STATUS = 'ACTIVE'" in select.upper()


def test_kupon_za_stary_pomijany(env, capsys):
    env["kupony"] = [_kupon(offset=-30)]
    ru.update_active_coupons(days_back=3)

    assert "[SKIP]" in capsys.readouterr().out
    assert env["conn"].polecenia("UPDATE COUPONS") == []


# ── PARTIAL: sedno bezpieczenstwa ───────────────────────────────────────────

def test_jedna_nierozstrzygnieta_noga_blokuje_zamkniecie(env, capsys):
    """KRYTYCZNE: kupon z brakujacym wynikiem NIE MOZE zostac zamkniety."""
    env["kupony"] = [_kupon(nogi=[_noga("Legia", "Lech"),
                                  _noga("Wisła", "Raków")])]
    env["fixtures"] = [_fixture("Legia", "Lech")]      # tylko pierwsza noga

    wynik = ru.update_active_coupons()

    assert wynik["partial"] == 1
    assert wynik["closed"] == 0
    assert env["conn"].polecenia("UPDATE COUPONS") == [], "zamknieto niepelny kupon"
    assert "[PARTIAL]" in capsys.readouterr().out


def test_partial_nie_rusza_bankrolla(env):
    env["kupony"] = [_kupon(nogi=[_noga("Legia", "Lech"), _noga("A", "B")])]
    env["fixtures"] = [_fixture("Legia", "Lech")]

    ru.update_active_coupons()
    assert env["conn"].polecenia("INSERT INTO BANKROLL_HISTORY") == []


# ── ocena kuponu ────────────────────────────────────────────────────────────

def test_wszystkie_nogi_trafione_daje_win(env):
    env["kupony"] = [_kupon(total_odds=2.5, stake=10.0)]
    env["fixtures"] = [_fixture(hg=2, ag=1)]          # typ "1" trafiony

    wynik = ru.update_active_coupons()

    assert wynik["closed"] == 1
    update = env["conn"].polecenia("UPDATE COUPONS")[0][1]
    assert update[0] == "WIN"
    assert update[1] == 25.0                          # 10 * 2.5


def test_nietrafiona_noga_daje_lose_i_zerowa_wyplate(env):
    env["kupony"] = [_kupon(total_odds=2.5, stake=10.0)]
    env["fixtures"] = [_fixture(hg=0, ag=3)]          # typ "1" nietrafiony

    ru.update_active_coupons()

    update = env["conn"].polecenia("UPDATE COUPONS")[0][1]
    assert update[0] == "LOSE"
    assert update[1] == 0.0


def test_roi_liczone_wzgledem_stawki(env):
    env["kupony"] = [_kupon(total_odds=3.0, stake=20.0)]
    env["fixtures"] = [_fixture(hg=2, ag=1)]

    ru.update_active_coupons()

    roi = env["conn"].polecenia("UPDATE COUPONS")[0][1][2]
    assert roi == 200.0                               # (60-20)/20 * 100


def test_roi_przegranej_to_minus_sto(env):
    env["kupony"] = [_kupon(total_odds=3.0, stake=20.0)]
    env["fixtures"] = [_fixture(hg=0, ag=1)]

    ru.update_active_coupons()
    assert env["conn"].polecenia("UPDATE COUPONS")[0][1][2] == -100.0


def test_wszystkie_nogi_musza_byc_trafione(env):
    """AKO: jedna nietrafiona noga przesadza o calym kuponie."""
    env["kupony"] = [_kupon(nogi=[_noga("Legia", "Lech", "1"),
                                  _noga("Wisła", "Raków", "1")])]
    env["fixtures"] = [_fixture("Legia", "Lech", 2, 1),      # trafiona
                       _fixture("Wisła", "Raków", 0, 2)]     # nietrafiona

    ru.update_active_coupons()
    assert env["conn"].polecenia("UPDATE COUPONS")[0][1][0] == "LOSE"


# ── bankroll ────────────────────────────────────────────────────────────────

def test_wygrana_dopisuje_wyplate_do_bankrolla(env):
    env["bankroll"] = 100.0
    env["kupony"] = [_kupon(total_odds=2.0, stake=10.0)]
    env["fixtures"] = [_fixture(hg=2, ag=1)]

    ru.update_active_coupons()

    stan_bankrollu = env["conn"].polecenia("UPDATE BANKROLL_STATE")
    assert stan_bankrollu, "bankroll nie zaktualizowany po wygranej"
    assert stan_bankrollu[0][1][0] == 120.0           # 100 + 20


def test_wygrana_zapisuje_wpis_historii(env):
    env["kupony"] = [_kupon(total_odds=2.0, stake=10.0)]
    env["fixtures"] = [_fixture(hg=2, ag=1)]

    ru.update_active_coupons()

    historia = env["conn"].polecenia("INSERT INTO BANKROLL_HISTORY")
    assert historia
    assert historia[0][1][3] == "WIN"
    assert "#1" in historia[0][1][4]


def test_przegrana_nie_rusza_bankrolla(env):
    env["kupony"] = [_kupon()]
    env["fixtures"] = [_fixture(hg=0, ag=2)]

    ru.update_active_coupons()
    assert env["conn"].polecenia("UPDATE BANKROLL_STATE") == []
    assert env["conn"].polecenia("INSERT INTO BANKROLL_HISTORY") == []


# ── dry_run ─────────────────────────────────────────────────────────────────

def test_dry_run_nie_zamyka_i_nie_rusza_bankrolla(env, capsys):
    env["kupony"] = [_kupon()]
    env["fixtures"] = [_fixture(hg=2, ag=1)]

    wynik = ru.update_active_coupons(dry_run=True)

    assert env["conn"].polecenia("UPDATE COUPONS") == []
    assert env["conn"].polecenia("UPDATE BANKROLL_STATE") == []
    assert "[DRY]" in capsys.readouterr().out
    assert wynik["closed"] == 0, "dry-run nie zapisuje, wiec nic nie zamknal"


# ── fallback scrapera ───────────────────────────────────────────────────────

def test_scraper_ratuje_noge_bez_wyniku_w_api(env, capsys):
    env["kupony"] = [_kupon()]
    env["fixtures"] = []
    env["scraper"] = "2-1"

    wynik = ru.update_active_coupons()

    assert wynik["closed"] == 1
    assert "COUPON SCRAPER FALLBACK" in capsys.readouterr().out


def test_awaria_scrapera_daje_partial_a_nie_wysypke(env, monkeypatch):
    import footstats.scrapers.flashscore_results as fs

    def _wybuch(h, a, d):
        raise OSError("scraper padl")

    monkeypatch.setattr(fs, "get_match_result", _wybuch, raising=False)
    env["kupony"] = [_kupon()]

    wynik = ru.update_active_coupons()
    assert wynik["partial"] == 1


# ── nazwy nog w alternatywnym formacie ──────────────────────────────────────

def test_noga_w_formacie_mecz_rozbijana(env):
    """Starsze kupony maja 'mecz': 'Legia vs Lech' zamiast home/away."""
    env["kupony"] = [_kupon(nogi=[{"mecz": "Legia vs Lech", "tip": "1"}])]
    env["fixtures"] = [_fixture("Legia", "Lech", 2, 1)]

    assert ru.update_active_coupons()["closed"] == 1


# ── cache zapytan ───────────────────────────────────────────────────────────

def test_jedno_zapytanie_na_date_dla_wielu_nog(env):
    """Trzy nogi z tego samego dnia = JEDNO zapytanie."""
    env["kupony"] = [_kupon(nogi=[_noga("A", "B"), _noga("C", "D"), _noga("E", "F")])]
    env["fixtures"] = []
    env["scraper"] = "1-0"

    ru.update_active_coupons()
    assert env["http"] == 1, f"oczekiwano 1 zapytania, bylo {env['http']}"


def test_blad_http_nie_wywala_rozliczenia(env, monkeypatch):
    def _padnij(*a, **k):
        raise requests.RequestException("brak sieci")

    monkeypatch.setattr(requests, "get", _padnij)
    env["kupony"] = [_kupon()]

    wynik = ru.update_active_coupons()
    assert wynik["partial"] == 1        # brak wyniku, ale bez wyjatku


# ── podsumowanie ────────────────────────────────────────────────────────────

def test_podsumowanie_drukowane(env, capsys):
    env["kupony"] = [_kupon()]
    env["fixtures"] = [_fixture(hg=2, ag=1)]

    ru.update_active_coupons()
    assert "Zamknięte: 1" in capsys.readouterr().out


def test_verbose_false_milczy(env, capsys):
    env["kupony"] = [_kupon()]
    env["fixtures"] = [_fixture(hg=2, ag=1)]

    ru.update_active_coupons(verbose=False)
    assert "Zamknięte" not in capsys.readouterr().out
