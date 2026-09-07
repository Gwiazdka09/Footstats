"""Raport CLV musi czytac stamtad, gdzie CLV realnie powstaje — z nog kuponow.

`get_clv_report` czyta `predictions`, a ta tabela pokrywa wylacznie typy, ktore
przeszly przez LLM-a: 291 wierszy wobec 439 rozliczonych kuponow. Glowne zrodlo
danych — `system_paper.build_single_leg_coupons`, 429 z tych kuponow — omija
`predictions` calkowicie. Raport oparty tylko na niej mierzylby 2% ruchu
i wygladal przy tym na kompletny.

CLV to jedyny pomiar, ktory mowi "czy bijemy linie zamkniecia" BEZ czekania na
wyniki, wiec musi obejmowac te sciezke, ktora naprawde gra.
"""
from __future__ import annotations

import json

import pytest

from footstats.core.clv_tracker import raport_clv_z_kuponow


def _kupon(legs, status="WON", data="2026-09-01", liga="PL"):
    return {"status": status, "match_date_first": data,
            "legs_json": json.dumps(legs), "liga": liga}


def test_pusta_lista_daje_pusty_raport():
    r = raport_clv_z_kuponow([])
    assert r["overall"] is None
    assert r["per_typ"] == []


def test_liczy_clv_z_nogi_bez_prediction_id():
    """Rdzen: noga ma `odds` i `clv_closing`, i to wystarcza."""
    kupony = [_kupon([{"tip": "1", "odds": 2.00, "clv_closing": 1.80, "liga": "PL"}])]
    r = raport_clv_z_kuponow(kupony)
    assert r["overall"]["n"] == 1
    assert r["overall"]["clv_avg"] == pytest.approx(11.11, abs=0.01)
    assert r["overall"]["positive_pct"] == 100.0


def test_noga_bez_kursu_zamkniecia_nie_liczy_sie():
    kupony = [_kupon([{"tip": "BTTS", "odds": 2.0}, {"tip": "1", "odds": 2.0, "clv_closing": 1.8}])]
    r = raport_clv_z_kuponow(kupony)
    assert r["overall"]["n"] == 1


@pytest.mark.parametrize("noga", [
    {"tip": "1", "odds": None, "clv_closing": 1.8},
    {"tip": "1", "odds": 1.0, "clv_closing": 1.8},     # kurs <= 1 nie istnieje
    {"tip": "1", "odds": 2.0, "clv_closing": 1.0},
    {"tip": "1", "odds": "bzdura", "clv_closing": 1.8},
])
def test_smieciowa_noga_jest_pomijana_a_nie_wysadza(noga):
    assert raport_clv_z_kuponow([_kupon([noga])])["overall"] is None


def test_grupowanie_po_typie_bo_typy_maja_rozne_rynki():
    """1X2 i Over/Under to rozne rynki o roznej marzy — laczna srednia je miesza."""
    kupony = [
        _kupon([{"tip": "1", "odds": 2.00, "clv_closing": 1.80}]),
        _kupon([{"tip": "1", "odds": 2.00, "clv_closing": 1.90}]),
        _kupon([{"tip": "Over 2.5", "odds": 1.80, "clv_closing": 2.00}]),
        _kupon([{"tip": "Over 2.5", "odds": 1.85, "clv_closing": 2.00}]),
    ]
    r = raport_clv_z_kuponow(kupony, min_probek=2)
    typy = {t["typ"]: t for t in r["per_typ"]}
    assert typy["1"]["n"] == 2 and typy["1"]["clv_avg"] > 0
    assert typy["Over 2.5"]["n"] == 2 and typy["Over 2.5"]["clv_avg"] < 0


def test_maly_kubelek_wypada_z_rozbicia_ale_nie_z_calosci():
    """Progu probek pilnujemy w rozbiciu; `overall` ma widziec wszystko."""
    kupony = [
        _kupon([{"tip": "1", "odds": 2.0, "clv_closing": 1.8}]),
        _kupon([{"tip": "1", "odds": 2.0, "clv_closing": 1.8}]),
        _kupon([{"tip": "X2", "odds": 2.0, "clv_closing": 1.8}]),
    ]
    r = raport_clv_z_kuponow(kupony, min_probek=2)
    assert r["overall"]["n"] == 3
    assert [t["typ"] for t in r["per_typ"]] == ["1"]


def test_zepsuty_legs_json_nie_zabija_raportu():
    kupony = [{"status": "WON", "match_date_first": "2026-09-01", "legs_json": "{niejson"},
              _kupon([{"tip": "1", "odds": 2.0, "clv_closing": 1.8}])]
    assert raport_clv_z_kuponow(kupony)["overall"]["n"] == 1


def test_srednia_wazona_nie_jest_srednia_srednich():
    """`overall` liczy sie z WSZYSTKICH nog, nie ze srednich kubelkow.

    Srednia srednich dawalaby typowi z jedna noga taka sama wage jak typowi
    z setka — czyli dokladnie ten blad kubelkowania, ktory juz raz kosztowal
    ten projekt dwa falszywe wnioski jednego dnia.
    """
    kupony = [_kupon([{"tip": "1", "odds": 2.0, "clv_closing": 1.8}]) for _ in range(9)]
    kupony.append(_kupon([{"tip": "X2", "odds": 1.0001, "clv_closing": 2.0}]))
    r = raport_clv_z_kuponow(kupony)
    # 9 nog po +11.11% i jedna po -50% → wazona okolo +4.9%, srednia srednich -19.4%
    assert r["overall"]["clv_avg"] == pytest.approx(4.94, abs=0.1)
