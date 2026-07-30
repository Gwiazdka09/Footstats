"""test_safe_http.py — retry/backoff w BezpiecznyHTTP.get.

PO CO: modul mial 12% pokrycia, a to on decyduje, czy przy 429/500 ponawiamy,
czy odpuszczamy. Zla decyzja = albo spalony budzet API-Football (100 req/dzien),
albo dziury w danych. Kazdy kod HTTP ma inna sciezke i zadna nie byla sprawdzona.

`time.sleep` jest mockowany ZAWSZE — przy 429 produkcja czeka 62 sekundy.
"""
from __future__ import annotations

import pytest
import requests

from footstats.utils.exceptions import BladPolaczenia
from footstats.utils.safe_http import BezpiecznyHTTP


class _Odpowiedz:
    """Minimalna atrapa requests.Response."""

    def __init__(self, status: int, dane: dict | None = None, tresc: bytes = b"{}"):
        self.status_code = status
        self._dane = dane if dane is not None else {}
        self.content = tresc
        self.elapsed = _Czas()

    def json(self) -> dict:
        return self._dane


class _Czas:
    @staticmethod
    def total_seconds() -> float:
        return 0.01


@pytest.fixture(autouse=True)
def bez_spania(monkeypatch):
    """429 usypia produkcje na 62s — w tescie nigdy nie spimy naprawde."""
    spania: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: spania.append(s))
    return spania


def _podstaw(monkeypatch, odpowiedzi):
    """Kolejne wywolania requests.get zwracaja kolejne elementy (lub rzucaja)."""
    kolejka = list(odpowiedzi)
    wywolania = {"n": 0}

    def _get(*a, **k):
        wywolania["n"] += 1
        pozycja = kolejka.pop(0)
        if isinstance(pozycja, Exception):
            raise pozycja
        return pozycja

    monkeypatch.setattr(requests, "get", _get)
    return wywolania


def test_200_zwraca_json(monkeypatch):
    _podstaw(monkeypatch, [_Odpowiedz(200, {"ok": True})])
    assert BezpiecznyHTTP.get("http://x") == {"ok": True}


def test_401_nie_ponawia(monkeypatch):
    """Zly klucz nie naprawi sie przez retry — nie palimy prob."""
    w = _podstaw(monkeypatch, [_Odpowiedz(401)])
    assert BezpiecznyHTTP.get("http://x") is None
    assert w["n"] == 1


def test_403_nie_ponawia(monkeypatch):
    w = _podstaw(monkeypatch, [_Odpowiedz(403)])
    assert BezpiecznyHTTP.get("http://x") is None
    assert w["n"] == 1


def test_404_nie_ponawia(monkeypatch):
    w = _podstaw(monkeypatch, [_Odpowiedz(404)])
    assert BezpiecznyHTTP.get("http://x") is None
    assert w["n"] == 1


def test_nieznany_status_nie_ponawia(monkeypatch):
    w = _podstaw(monkeypatch, [_Odpowiedz(418)])
    assert BezpiecznyHTTP.get("http://x") is None
    assert w["n"] == 1


def test_429_czeka_i_ponawia(monkeypatch, bez_spania):
    _podstaw(monkeypatch, [_Odpowiedz(429), _Odpowiedz(200, {"po": "czekaniu"})])
    assert BezpiecznyHTTP.get("http://x") == {"po": "czekaniu"}
    assert bez_spania and bez_spania[0] >= 60, "rate limit ma odczekac ~minute"


def test_500_ponawia_z_narastajacym_backoffem(monkeypatch, bez_spania):
    w = _podstaw(monkeypatch, [_Odpowiedz(500), _Odpowiedz(500), _Odpowiedz(500)])
    assert BezpiecznyHTTP.get("http://x", retries=2) is None
    assert w["n"] == 3, "powinny byc 3 proby (1 + 2 retry)"
    assert bez_spania == [5, 10], "backoff ma rosnac miedzy probami"


def test_500_a_potem_sukces(monkeypatch):
    _podstaw(monkeypatch, [_Odpowiedz(500), _Odpowiedz(200, {"w": "koncu"})])
    assert BezpiecznyHTTP.get("http://x") == {"w": "koncu"}


def test_brak_polaczenia_rzuca_typowanym_bledem(monkeypatch):
    """Po wyczerpaniu prob leci BladPolaczenia, nie goly requests.ConnectionError."""
    blad = requests.exceptions.ConnectionError("brak sieci")
    _podstaw(monkeypatch, [blad, blad, blad])
    with pytest.raises(BladPolaczenia):
        BezpiecznyHTTP.get("http://x", retries=2)


def test_polaczenie_wraca_przy_kolejnej_probie(monkeypatch):
    _podstaw(monkeypatch, [
        requests.exceptions.ConnectionError("chwilowo"),
        _Odpowiedz(200, {"wrocilo": 1}),
    ])
    assert BezpiecznyHTTP.get("http://x") == {"wrocilo": 1}


def test_timeout_zwraca_none_po_probach(monkeypatch):
    t = requests.exceptions.Timeout()
    w = _podstaw(monkeypatch, [t, t, t])
    assert BezpiecznyHTTP.get("http://x", retries=2) is None
    assert w["n"] == 3


def test_zepsuty_json_nie_ponawia(monkeypatch):
    """Serwer odpowiedzial — powtorka da to samo smiecie."""
    w = _podstaw(monkeypatch, [requests.exceptions.JSONDecodeError("zle", "doc", 0)])
    assert BezpiecznyHTTP.get("http://x") is None
    assert w["n"] == 1


def test_blad_systemowy_nie_wywala_programu(monkeypatch):
    _podstaw(monkeypatch, [OSError("gniazdo padlo")])
    assert BezpiecznyHTTP.get("http://x") is None


def test_parametry_ida_do_requests(monkeypatch):
    zebrane = {}

    def _get(url, headers=None, params=None, timeout=None):
        zebrane.update(url=url, headers=headers, params=params, timeout=timeout)
        return _Odpowiedz(200, {})

    monkeypatch.setattr(requests, "get", _get)
    BezpiecznyHTTP.get("http://x", params={"a": 1}, headers={"K": "v"}, timeout=7)

    assert zebrane["url"] == "http://x"
    assert zebrane["params"] == {"a": 1}
    assert zebrane["headers"] == {"K": "v"}
    assert zebrane["timeout"] == 7
