"""Testy czystych parserów Superbet (superbet_parsing.py).

Logika wcześniej zakopana w god-module superbet.py (0 testów) — po wydzieleniu
do czystego modułu testowalna w izolacji (bez Playwright).
"""
from footstats.scrapers.superbet_parsing import (
    _czy_betbuilder,
    _czy_linia_to_mecz,
    _parsuj_item_api,
    _parsuj_json_api,
    _parsuj_ticket,
    _parsuj_zdarzenia,
)


# ── _czy_betbuilder ────────────────────────────────────────────────────────
def test_betbuilder_wykrywa_liczba_goli():
    assert _czy_betbuilder("Liczba goli powyżej 2.5") is True


def test_betbuilder_wykrywa_strzelca():
    assert _czy_betbuilder("Strzelec: Lewandowski") is True


def test_betbuilder_wykrywa_karte():
    assert _czy_betbuilder("Żółta karta dla gospodarzy") is True


def test_betbuilder_falsz_dla_zwyklego_1x2():
    assert _czy_betbuilder("1") is False
    assert _czy_betbuilder("Zwycięstwo gospodarza") is False


# ── _czy_linia_to_mecz ─────────────────────────────────────────────────────
def test_linia_to_mecz_prawdziwy_mecz():
    assert _czy_linia_to_mecz("Real Madryt - Barcelona") is True


def test_linia_to_mecz_myslnik_en_dash():
    assert _czy_linia_to_mecz("Bayern – Dortmund") is True


def test_linia_to_mecz_falsz_dla_typu_betbuilder():
    # zawiera słowo kluczowe typu ("powyżej") → nie mecz
    assert _czy_linia_to_mecz("Liczba goli - powyżej 2.5") is False


def test_linia_to_mecz_falsz_dla_zakresu_wyniku():
    assert _czy_linia_to_mecz("Wynik - 1-3") is False


def test_linia_to_mecz_falsz_bez_separatora():
    assert _czy_linia_to_mecz("Realny faworyt dnia") is False


def test_linia_to_mecz_falsz_mala_litera():
    assert _czy_linia_to_mecz("real madryt - barcelona") is False


# ── _parsuj_ticket ─────────────────────────────────────────────────────────
def test_parsuj_ticket_pelny():
    data = {
        "ticketId": "T1",
        "coefficient": 3.5,
        "payment": {"amount": 10.0},
        "events": [
            {"name": "A - B", "marketName": "1", "coefficient": 1.8},
            {"name": "C - D", "marketName": "Over 2.5", "odds": 1.9},
        ],
    }
    out = _parsuj_ticket(data, "typer")
    assert out is not None
    assert out["nick"] == "typer"
    assert out["kurs_laczny"] == 3.5
    assert out["stawka"] == 10.0
    assert len(out["zdarzenia"]) == 2
    assert out["zdarzenia"][0]["mecz"] == "A - B"
    assert out["zrodlo"] == "superbet_ticket_api"


def test_parsuj_ticket_none_gdy_pusty():
    assert _parsuj_ticket({"ticketId": "T2"}, "x") is None


def test_parsuj_ticket_odrzuca_kurs_ponizej_1():
    out = _parsuj_ticket(
        {"ticketId": "T3", "coefficient": 0.5,
         "events": [{"name": "A - B", "marketName": "1", "odds": 2.0}]},
        "x",
    )
    assert out["kurs_laczny"] is None  # 0.5 < 1.0 odrzucone


# ── _parsuj_item_api ───────────────────────────────────────────────────────
def test_parsuj_item_nick_z_zagniezdzonej_sciezki():
    item = {
        "user": {"username": "ProTyper"},
        "totalOdds": 5.0,
        "selections": [{"eventName": "A - B", "marketName": "1", "odds": 2.5}],
    }
    out = _parsuj_item_api(item)
    assert out["nick"] == "ProTyper"
    assert out["kurs_laczny"] == 5.0
    assert out["zdarzenia"][0]["mecz"] == "A - B"


def test_parsuj_item_none_dla_nie_dict():
    assert _parsuj_item_api("nie-dict") is None


def test_parsuj_item_none_gdy_brak_danych():
    assert _parsuj_item_api({"foo": "bar"}) is None


# ── _parsuj_json_api (dispatcher) ──────────────────────────────────────────
def test_json_api_format_ticket():
    out = _parsuj_json_api({"ticketId": "T", "coefficient": 2.0,
                            "events": [{"name": "A - B", "marketName": "1"}]}, "n")
    assert len(out) == 1
    assert out[0]["zrodlo"] == "superbet_ticket_api"


def test_json_api_lista():
    data = [{"username": "u1", "totalOdds": 2.0,
             "selections": [{"eventName": "A - B", "marketName": "1"}]}]
    out = _parsuj_json_api(data)
    assert len(out) == 1


def test_json_api_dict_z_kluczem_data():
    data = {"data": [{"username": "u1", "totalOdds": 2.0,
                      "selections": [{"eventName": "A - B", "marketName": "1"}]}]}
    out = _parsuj_json_api(data)
    assert len(out) == 1


def test_json_api_pusty():
    assert _parsuj_json_api({}) == []


# ── _parsuj_zdarzenia (parsing linii tekstowych) ───────────────────────────
def test_parsuj_zdarzenia_mecz_typ_kurs():
    linie = ["Real Madryt - Barcelona", "1", "2.10"]
    out = _parsuj_zdarzenia(linie)
    assert len(out) == 1
    assert out[0]["mecz"] == "Real Madryt - Barcelona"
    assert out[0]["typ"] == "1"
    assert out[0]["kurs"] == 2.10


def test_parsuj_zdarzenia_pomija_metadane():
    linie = ["Stawka 10 PLN", "Kurs łączny 5.0", "Real Madryt - Barcelona", "Over 2.5"]
    out = _parsuj_zdarzenia(linie)
    assert len(out) == 1
    assert out[0]["mecz"] == "Real Madryt - Barcelona"
