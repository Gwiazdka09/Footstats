"""test_api_football_get_budget.py — strategia oszczedzania budzetu API-Football.

PO CO: `APIFootball._get` to 8 galezi decyzyjnych stojacych miedzy nami
a limitem 100 req/dzien — i ZADNA nie byla testowana. Kazda pomylka boli
inaczej:
  * cache pominiety      -> spalony budzet, dzien bez danych,
  * cache uzyty za mocno -> model liczy na wczorajszych skladach,
  * 429 nieobsluzony     -> wyjatek zamiast fallbacku na cache.

`waliduj()` synchronizuje nasz lokalny licznik z licznikiem SERWERA (serwer
jest prawda). Bez tego lokalny licznik dryfuje i albo blokujemy sie za wczesnie,
albo wchodzimy w 429.

Zaden test nie rusza sieci — `requests.get` jest podstawiony wszedzie.
"""
from __future__ import annotations

import pandas as pd
import pytest
import requests

import footstats.scrapers.api_football as af
from footstats.scrapers.api_football import APIFootball, _parse_odd
from footstats.utils.exceptions import BladBudzetu


class _Odp:
    def __init__(self, status=200, dane=None):
        self.status_code = status
        self._dane = dane if dane is not None else {}

    def json(self):
        return self._dane


@pytest.fixture
def klient(monkeypatch):
    """APIFootball z odcieta siecia, cache'em i budzetem.

    Domyslnie: cache pusty, budzet zdrowy, request zwraca {"response": []}.
    """
    stan = {
        "cache": {},            # cache_key -> dane (swiezy)
        "dysk": {},             # cache_key -> {"data": ...} (takze wygasle)
        "budzet": {"krytyczny": False, "uzyto": 10},
        "odpowiedz": _Odp(),
        "zapisane": [],         # (key, dane, stare)
        "zuzyte": [],           # endpointy zarejestrowane w budzecie
        "requesty": [],         # (url, params)
    }

    monkeypatch.setattr(af, "_af_cache_get", lambda k: stan["cache"].get(k))
    monkeypatch.setattr(af, "_af_load_disk_cache", lambda: stan["dysk"])
    monkeypatch.setattr(af, "af_budget_status", lambda: stan["budzet"])
    monkeypatch.setattr(af, "_af_cache_set",
                        lambda k, d, s: stan["zapisane"].append((k, d, s)))

    def _budzet(endpoint):
        if isinstance(stan.get("budzet_wyjatek"), Exception):
            raise stan["budzet_wyjatek"]
        stan["zuzyte"].append(endpoint)
        return 50

    monkeypatch.setattr(af, "bezpieczny_budget_use", _budzet)

    def _get(url, headers=None, params=None, timeout=None):
        stan["requesty"].append((url, params))
        if isinstance(stan["odpowiedz"], Exception):
            raise stan["odpowiedz"]
        return stan["odpowiedz"]

    monkeypatch.setattr(requests, "get", _get)

    stan["klient"] = APIFootball("klucz-testowy")
    return stan


# ── _get: cache ─────────────────────────────────────────────────────────────

def test_swiezy_cache_nie_zuzywa_requesta(klient):
    """Najwazniejsza oszczednosc: trafiony cache = ZERO ruchu i zero budzetu."""
    klucz = "af:/fixtures:{'league': 1}"
    klient["cache"][klucz] = {"response": ["z cache"]}

    wynik = klient["klient"]._get("/fixtures", params={"league": 1})

    assert wynik == {"response": ["z cache"]}
    assert klient["requesty"] == []
    assert klient["zuzyte"] == []


def test_force_network_omija_cache(klient):
    klucz = "af:/fixtures:{'league': 1}"
    klient["cache"][klucz] = {"response": ["stare"]}
    klient["odpowiedz"] = _Odp(200, {"response": ["swieze"]})

    wynik = klient["klient"]._get("/fixtures", params={"league": 1}, force_network=True)

    assert wynik == {"response": ["swieze"]}
    assert len(klient["requesty"]) == 1


def test_udany_request_trafia_do_cache(klient):
    klient["odpowiedz"] = _Odp(200, {"response": [1, 2]})
    klient["klient"]._get("/fixtures", params={"league": 5})

    assert len(klient["zapisane"]) == 1
    klucz, dane, _stare = klient["zapisane"][0]
    assert "af:/fixtures" in klucz
    assert dane == {"response": [1, 2]}


def test_licznik_lokalny_rosnie_po_requescie(klient):
    klient["odpowiedz"] = _Odp(200, {"response": []})
    przed = klient["klient"]._req_today
    klient["klient"]._get("/fixtures")
    assert klient["klient"]._req_today == przed + 1


# ── _get: budzet ────────────────────────────────────────────────────────────

def test_krytyczny_budzet_zwraca_wygasle_dane(klient, capsys):
    """Lepsze wczorajsze dane niz brak danych — ale user ma o tym wiedziec."""
    klucz = "af:/fixtures:None"
    klient["budzet"] = {"krytyczny": True, "uzyto": 98}
    klient["dysk"][klucz] = {"data": {"response": ["wygasle"]}}

    wynik = klient["klient"]._get("/fixtures")

    assert wynik == {"response": ["wygasle"]}
    assert klient["requesty"] == [], "wyslano request przy krytycznym budzecie"
    assert "Krytyczny budzet" in capsys.readouterr().out


def test_krytyczny_budzet_bez_cache_zwraca_none(klient, capsys):
    klient["budzet"] = {"krytyczny": True, "uzyto": 98}
    assert klient["klient"]._get("/fixtures") is None
    assert klient["requesty"] == []
    assert "budzet krytyczny" in capsys.readouterr().out


def test_wyjatek_budzetu_spada_na_wygasle_dane(klient):
    """BladBudzetu z licznika = twarda blokada; ratujemy sie cache'em."""
    klucz = "af:/fixtures:None"
    klient["budzet_wyjatek"] = BladBudzetu("wyczerpany")
    klient["dysk"][klucz] = {"data": {"response": ["ratunek"]}}

    assert klient["klient"]._get("/fixtures") == {"response": ["ratunek"]}
    assert klient["requesty"] == []


def test_endpoint_rejestrowany_w_budzecie(klient):
    klient["odpowiedz"] = _Odp(200, {"response": []})
    klient["klient"]._get("/odds")
    assert klient["zuzyte"] == ["/odds"]


# ── _get: kody HTTP ─────────────────────────────────────────────────────────

def test_429_spada_na_cache_zamiast_rzucac(klient, capsys):
    """Limit wyczerpany PO STRONIE SERWERA — nasz licznik mogl sie rozjechac."""
    klucz = "af:/fixtures:None"
    klient["odpowiedz"] = _Odp(429)
    klient["dysk"][klucz] = {"data": {"response": ["z cache"]}}

    assert klient["klient"]._get("/fixtures") == {"response": ["z cache"]}
    assert "429" in capsys.readouterr().out


def test_429_bez_cache_zwraca_none(klient):
    klient["odpowiedz"] = _Odp(429)
    assert klient["klient"]._get("/fixtures") is None


@pytest.mark.parametrize("status", [401, 403])
def test_blad_autoryzacji_uniewaznia_klucz(klient, status, capsys):
    """Zly klucz ma zostac zapamietany — kolejne wywolania nie maja go probowac."""
    klient["odpowiedz"] = _Odp(status)
    assert klient["klient"]._get("/fixtures") is None
    assert klient["klient"]._valid is False
    assert "autoryzacji" in capsys.readouterr().out


def test_nieznany_status_zwraca_none(klient):
    klient["odpowiedz"] = _Odp(500)
    assert klient["klient"]._get("/fixtures") is None


def test_timeout_spada_na_cache(klient, capsys):
    klucz = "af:/fixtures:None"
    klient["odpowiedz"] = requests.exceptions.Timeout()
    klient["dysk"][klucz] = {"data": {"response": ["cache"]}}

    assert klient["klient"]._get("/fixtures") == {"response": ["cache"]}
    assert "timeout" in capsys.readouterr().out.lower()


def test_blad_sieci_zwraca_none(klient, capsys):
    klient["odpowiedz"] = requests.exceptions.ConnectionError("brak sieci")
    assert klient["klient"]._get("/fixtures") is None
    assert "blad sieci" in capsys.readouterr().out


# ── waliduj ─────────────────────────────────────────────────────────────────

@pytest.fixture
def walidacja(monkeypatch):
    stan = {"budzet": {"uzyto": 0}, "zapisany": None, "odpowiedz": _Odp()}
    monkeypatch.setattr(af, "_af_budget_load", lambda: dict(stan["budzet"]))
    monkeypatch.setattr(af, "_af_budget_save",
                        lambda b: stan.__setitem__("zapisany", b))

    def _get(url, headers=None, timeout=None):
        if isinstance(stan["odpowiedz"], Exception):
            raise stan["odpowiedz"]
        return stan["odpowiedz"]

    monkeypatch.setattr(requests, "get", _get)
    return stan


def test_waliduj_ok_zwraca_licznik(walidacja):
    walidacja["odpowiedz"] = _Odp(200, {"response": {
        "requests": {"current": 37, "limit_day": 100}}})

    ok, msg = APIFootball("k").waliduj()
    assert ok is True
    assert "37/100" in msg
    assert "pozostalo: 63" in msg


def test_waliduj_synchronizuje_licznik_z_serwerem(walidacja):
    """Serwer jest prawda — lokalny licznik podciagamy w gore, nigdy w dol."""
    walidacja["budzet"] = {"uzyto": 5}
    walidacja["odpowiedz"] = _Odp(200, {"response": {
        "requests": {"current": 40, "limit_day": 100}}})

    APIFootball("k").waliduj()
    assert walidacja["zapisany"]["uzyto"] == 40


def test_waliduj_nie_cofa_lokalnego_licznika(walidacja):
    """Serwer pokazuje mniej niz my? Nie zerujemy — inaczej dublujemy zapytania."""
    walidacja["budzet"] = {"uzyto": 60}
    walidacja["odpowiedz"] = _Odp(200, {"response": {
        "requests": {"current": 40, "limit_day": 100}}})

    APIFootball("k").waliduj()
    assert walidacja["zapisany"] is None, "nadpisano licznik nizsza wartoscia"


def test_waliduj_401_to_zly_klucz(walidacja):
    walidacja["odpowiedz"] = _Odp(401)
    klient = APIFootball("zly")
    ok, msg = klient.waliduj()

    assert ok is False
    assert "401" in msg
    assert klient._valid is False


def test_waliduj_inny_status(walidacja):
    walidacja["odpowiedz"] = _Odp(503)
    ok, msg = APIFootball("k").waliduj()
    assert ok is False and "503" in msg


def test_waliduj_blad_sieci_nie_wywala(walidacja):
    walidacja["odpowiedz"] = requests.exceptions.ConnectionError("brak sieci")
    ok, msg = APIFootball("k").waliduj()
    assert ok is False and "brak sieci" in msg


# ── wyniki_liga ─────────────────────────────────────────────────────────────

def _fixture(gg=2, ga=1, home="Legia", away="Lech") -> dict:
    return {
        "fixture": {"date": "2026-07-31T18:00:00+00:00"},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": gg, "away": ga},
        "league": {"round": "Regular Season - 5"},
    }


def test_wyniki_liga_buduje_dataframe(klient):
    klient["odpowiedz"] = _Odp(200, {"response": [_fixture()]})
    df = klient["klient"].wyniki_liga(106)

    assert isinstance(df, pd.DataFrame) and len(df) == 1
    w = df.iloc[0]
    assert w["gospodarz"] == "Legia" and w["goscie"] == "Lech"
    assert w["gole_g"] == 2 and w["gole_a"] == 1
    assert w["data"] == "2026-07-31"
    assert w["stage"] == "REGULAR_SEASON"


def test_wyniki_liga_pomija_mecze_bez_wyniku(klient):
    """Mecz bez goli to mecz nierozegrany — nie moze wejsc do historii modelu."""
    klient["odpowiedz"] = _Odp(200, {"response": [
        _fixture(), _fixture(gg=None, ga=None, home="Wisła"),
    ]})
    df = klient["klient"].wyniki_liga(106)
    assert len(df) == 1
    assert "Wisła" not in set(df["gospodarz"])


def test_wyniki_liga_bez_danych_zwraca_none(klient):
    klient["odpowiedz"] = _Odp(200, {"response": []})
    assert klient["klient"].wyniki_liga(106) is None


def test_wyniki_liga_brak_odpowiedzi_zwraca_none(klient):
    klient["odpowiedz"] = _Odp(500)
    assert klient["klient"].wyniki_liga(106) is None


def test_sezon_wyliczany_z_miesiaca(klient):
    """Sezon europejski: od lipca liczy sie rok biezacy, wczesniej poprzedni."""
    klient["odpowiedz"] = _Odp(200, {"response": []})
    klient["klient"].wyniki_liga(106)
    _url, params = klient["requesty"][0]
    assert isinstance(params["season"], int)
    assert params["league"] == 106
    assert params["status"] == "FT"


# ── ligi_dodatkowe ──────────────────────────────────────────────────────────

def test_ligi_dodatkowe_zwraca_mape_bez_requesta(klient):
    ligi = klient["klient"].ligi_dodatkowe()
    assert ligi and all("nazwa" in l and "kod" in l for l in ligi)
    assert klient["requesty"] == [], "mapa lig nie wymaga sieci"


# ── _parse_odd ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("wejscie,oczekiwane", [
    ("2.10", 2.10), (1.85, 1.85), ("3", 3.0), (None, None),
    ("", None), ("brak", None), ([], None),
])
def test_parse_odd(wejscie, oczekiwane):
    assert _parse_odd(wejscie) == oczekiwane
