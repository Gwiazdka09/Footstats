"""Mapowanie statystyk sedziego FotMob na kolumny tabeli `referees`.

Pulapka: `yellowCards` przychodzi jako SREDNIA na mecz, `redCards` jako SUMA
sezonu, a `avg_goals` i `home_win_pct` nie przychodza wcale. Wpisanie sumy do
kolumny "srednia" albo zera w brakujace pole to ten sam blad co 50/50/50
w api_football — odbiorca dostaje liczbe i nie wie, ze to nie pomiar.
"""
from __future__ import annotations

from footstats.scrapers.teamnews.sedzia import statystyki_sedziego

# Ksztalt skopiowany z zywej odpowiedzi FotMoba (Michael Oliver, 30.08).
_SUROWY = {
    "text": "Michael Oliver",
    "stats": [
        {"type": "matches", "value": 54, "valueType": "total"},
        {"type": "yellowCards", "value": 3.8, "valueType": "perMatch",
         "average": 4.01, "total": 205},
        {"type": "redCards", "value": 2, "valueType": "total"},
        {"type": "unknown", "value": 5, "valueType": "total"},
        {"type": "penalties", "value": 6, "valueType": "total"},
        {"type": "fouls", "value": 23.37, "valueType": "perMatch", "average": 21.71},
    ],
}


def test_zolte_brane_wprost_bo_juz_sa_srednia():
    assert statystyki_sedziego(_SUROWY)["avg_yellow"] == 3.8


def test_czerwone_dzielone_przez_mecze_bo_przychodza_jako_suma():
    """2 czerwone na 54 mecze = 0.037 na mecz. Wpisanie samego 2 zrobiloby
    z Olivera sedziego wyrzucajacego dwoch ludzi w kazdym meczu."""
    assert statystyki_sedziego(_SUROWY)["avg_red"] == round(2 / 54, 4)


def test_liczba_meczow_przenoszona():
    assert statystyki_sedziego(_SUROWY)["n_matches"] == 54


def test_brakujacych_kolumn_NIE_MA_w_slowniku():
    """FotMob nie daje sredniej goli ani % wygranych gospodarza. Klucz ma byc
    NIEOBECNY, nie obecny z zerem — zero to twierdzenie o swiecie."""
    wynik = statystyki_sedziego(_SUROWY)
    assert "avg_goals" not in wynik
    assert "home_win_pct" not in wynik


def test_zero_meczow_nie_dzieli_przez_zero():
    surowy = {"text": "Debiutant", "stats": [
        {"type": "matches", "value": 0, "valueType": "total"},
        {"type": "redCards", "value": 0, "valueType": "total"},
    ]}
    wynik = statystyki_sedziego(surowy)
    assert "avg_red" not in wynik
    assert "n_matches" not in wynik


def test_zolte_jako_suma_NIE_sa_brane_za_srednia():
    """Gdyby FotMob zmienil jednostke, milczace przyjecie wartosci wpisaloby
    205 zoltych na mecz. Brak `perMatch` = brak klucza."""
    surowy = {"text": "X", "stats": [
        {"type": "matches", "value": 54, "valueType": "total"},
        {"type": "yellowCards", "value": 205, "valueType": "total"},
    ]}
    assert "avg_yellow" not in statystyki_sedziego(surowy)


def test_brak_sedziego_daje_pusty_slownik():
    assert statystyki_sedziego(None) == {}
    assert statystyki_sedziego({}) == {}


def test_nieznany_typ_statystyki_jest_ignorowany_bez_wybuchu():
    """FotMob ma w tablicy wpis {"type": "unknown"} — parser ma go minac."""
    surowy = {"text": "X", "stats": [
        {"type": "unknown", "value": 5, "valueType": "total"},
        {"type": "matches", "value": 10, "valueType": "total"},
    ]}
    assert statystyki_sedziego(surowy)["n_matches"] == 10


def test_smieci_w_tablicy_stats_nie_wywracaja_parsera():
    surowy = {"text": "X", "stats": [None, "bzdura", {}, {"value": 1},
                                     {"type": "matches", "value": 10, "valueType": "total"}]}
    assert statystyki_sedziego(surowy)["n_matches"] == 10
