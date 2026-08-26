"""ZADANIE D — „drugi wybór": czy typ nr 2 modelu trafia częściej niż typ nr 1.

PUŁAPKA, KTÓRA PRZESĄDZA O KSZTAŁCIE TEGO PLIKU: bazy 7 rynków, zmierzone na
produkcji 2026-08-26 (n=424), mają rozrzut 31 punktów procentowych —

    1: 43.9%   X: 23.6%   2: 32.5%
    Over 2.5: 55.0%   Under 2.5: 45.0%
    BTTS: 52.6%

Raport liczony SUROWĄ trafnością koronowałby Over 2.5 za samą bazę, nie za
wiedzę modelu — dokładnie ten sam błąd co `_pomijaj_btts` w
`system_paper.py:42`, gdzie argmax po surowym prawdopodobieństwie wybiera
rynek dwustronny w 74% meczów, bo taki rynek z definicji ma jedną stronę
≥50%. Dlatego główną miarą jest PRZEWAGA nad bazą WŁASNEGO rynku, nie
surowa trafność — test nr 6 poniżej to sprawdza wprost.
"""
from __future__ import annotations

import pytest

from footstats.core.ranking_rynkow import (
    przewaga_nad_baza,
    ranking_rynkow,
    rozklad_rynkow,
)


def _wiersz(**nadpisania) -> dict:
    """Kompletny wiersz `model_log` z sensownymi wartościami domyślnymi."""
    bazowy = {
        "prob_home": 40.0,
        "prob_draw": 25.0,
        "prob_away": 35.0,
        "prob_over25": 55.0,
        "prob_btts": 50.0,
        "model_tip": "1",
        "actual_result": "2-1",
    }
    bazowy.update(nadpisania)
    return bazowy


# ── 1. sortowanie i komplet 7 pozycji ───────────────────────────────────────

def test_ranking_posortowany_malejaco_siedem_pozycji():
    wiersz = _wiersz(
        prob_home=40.0, prob_draw=25.0, prob_away=35.0,
        prob_over25=60.0, prob_btts=48.0,
    )
    ranking = ranking_rynkow(wiersz)

    assert len(ranking) == 7
    proby = [poz["prob"] for poz in ranking]
    assert proby == sorted(proby, reverse=True)
    assert {poz["rynek"] for poz in ranking} == {
        "1", "X", "2", "Over 2.5", "Under 2.5", "BTTS", "BTTS NIE",
    }


# ── 2. dopełnienia Under 2.5 / BTTS NIE ─────────────────────────────────────

def test_under25_i_btts_nie_sa_dopelnieniem():
    wiersz = _wiersz(prob_over25=60.0, prob_btts=48.0)
    ranking = {poz["rynek"]: poz for poz in ranking_rynkow(wiersz)}

    assert ranking["Under 2.5"]["prob"] == 40.0
    assert ranking["BTTS NIE"]["prob"] == 52.0


# ── 3. trafiony liczony z actual_result, NIGDY z model_tip/tip_correct ─────

def test_trafiony_liczony_z_actual_result_nie_z_model_tip():
    """Model typował "X", ale ranking MUSI znać prawdę o wszystkich 7 rynkach
    z SAMEGO wyniku — gdyby czerpał z `model_tip`/`tip_correct`, rynek "1"
    (i pozostałe nietypowane przez model) zostałby bez odpowiedzi."""
    wiersz = _wiersz(model_tip="X", actual_result="2-1")
    ranking = {poz["rynek"]: poz for poz in ranking_rynkow(wiersz)}

    assert ranking["1"]["trafiony"] == 1        # 2-1 = wygrana gospodarza
    assert ranking["X"]["trafiony"] == 0        # model typował X, ale to nie remis
    assert ranking["2"]["trafiony"] == 0
    assert ranking["Over 2.5"]["trafiony"] == 1  # 3 gole razem
    assert ranking["Under 2.5"]["trafiony"] == 0
    assert ranking["BTTS"]["trafiony"] == 1     # obie strzeliły
    assert ranking["BTTS NIE"]["trafiony"] == 0


# ── 4. wynik nierozliczalny ─────────────────────────────────────────────────

def test_wynik_nierozliczalny_wszystkie_trafiony_none():
    wiersz = _wiersz(actual_result="2-1 (AET)")
    ranking = ranking_rynkow(wiersz)

    assert len(ranking) == 7
    assert all(poz["trafiony"] is None for poz in ranking)


# ── 5. NULL pomija dany rynek, reszta bez zmian ─────────────────────────────

def test_null_prob_btts_pomija_btts_i_btts_nie():
    wiersz = _wiersz(prob_btts=None)
    ranking = ranking_rynkow(wiersz)

    rynki = {poz["rynek"] for poz in ranking}
    assert "BTTS" not in rynki
    assert "BTTS NIE" not in rynki
    assert len(ranking) == 5
    assert rynki == {"1", "X", "2", "Over 2.5", "Under 2.5"}


def test_null_prob_over25_pomija_over_i_under():
    wiersz = _wiersz(prob_over25=None)
    ranking = ranking_rynkow(wiersz)

    rynki = {poz["rynek"] for poz in ranking}
    assert "Over 2.5" not in rynki
    assert "Under 2.5" not in rynki
    assert len(ranking) == 5


# ── 6. TEST-PUŁAPKA: przewaga, nie surowa trafność ──────────────────────────

def test_przewaga_wskazuje_rynek_z_mniejsza_baza_nie_z_wieksza_trafnoscia():
    """Pozycja #1 (dominuje ją "Over 2.5"/"1", rynki o wysokiej bazie własnej)
    ma WYŻSZĄ surową trafność niż pozycja #2 (dominuje ją "X"/"BTTS NIE",
    rynki o niskiej bazie) — a mimo to pozycja #2 ma WYŻSZĄ przewagę nad
    bazą. Wyliczone ręcznie (patrz uzasadnienie w treści zadania D):

        rank #1: trafność 6/7 ≈ 85.7%, baza ≈ 65.3%  → przewaga ≈ 20.4 pp
        rank #2: trafność 3/7 ≈ 42.9%, baza ≈ 18.4%  → przewaga ≈ 24.5 pp

    Gdyby raport sortował po surowej trafności (błąd `_pomijaj_btts`),
    wskazałby #1 — dokładnie odwrotnie niż mówią dane.
    """
    # Grupa A (5 wierszy): prob_over25 najwyzsze -> rank1="Over 2.5",
    # prob_draw drugie -> rank2="X". 4/5 wynikow to "3-1" (Over2.5 trafia,
    # X nie), 1/5 to "1-1" (Over2.5 pudlo, X trafia).
    grupa_a_wysoka = [
        _wiersz(prob_home=20.0, prob_draw=55.0, prob_away=15.0,
                prob_over25=65.0, prob_btts=48.0, actual_result="3-1")
        for _ in range(4)
    ]
    grupa_a_niska = [
        _wiersz(prob_home=20.0, prob_draw=55.0, prob_away=15.0,
                prob_over25=65.0, prob_btts=48.0, actual_result="1-1")
    ]
    # Grupa B (2 wiersze): prob_home najwyzsze -> rank1="1", BTTS NIE drugie
    # -> rank2="BTTS NIE". Wynik "2-0": "1" trafia, BTTS NIE trafia.
    grupa_b = [
        _wiersz(prob_home=70.0, prob_draw=5.0, prob_away=10.0,
                prob_over25=40.0, prob_btts=35.0, actual_result="2-0")
        for _ in range(2)
    ]
    wiersze = grupa_a_wysoka + grupa_a_niska + grupa_b

    rank1 = przewaga_nad_baza(wiersze, rank=1)
    rank2 = przewaga_nad_baza(wiersze, rank=2)

    assert rank1["n"] == 7
    assert rank2["n"] == 7
    # Surowa trafnosc: #1 wygrywa.
    assert rank1["trafnosc"] > rank2["trafnosc"]
    # Przewaga nad baza: #2 wygrywa — to jest sedno zadania.
    assert rank2["przewaga"] > rank1["przewaga"]
    assert rank1["trafnosc"] == pytest.approx(600 / 7)
    assert rank2["trafnosc"] == pytest.approx(300 / 7)


# ── 7. rozklad_rynkow sumuje sie do n ────────────────────────────────────────

def test_rozklad_rynkow_sumuje_sie_do_n():
    wiersze = [
        _wiersz(prob_home=60.0, prob_draw=10.0, prob_away=10.0,
                prob_over25=55.0, prob_btts=55.0, actual_result="1-0"),
        _wiersz(prob_home=10.0, prob_draw=15.0, prob_away=75.0,
                prob_over25=40.0, prob_btts=30.0, actual_result="0-2"),
        _wiersz(prob_home=20.0, prob_draw=15.0, prob_away=15.0,
                prob_over25=90.0, prob_btts=30.0, actual_result="2-2"),
    ]

    rozklad = rozklad_rynkow(wiersze, rank=1)

    assert sum(rozklad.values()) == len(wiersze)
    assert rozklad.get("1") == 1
    assert rozklad.get("2") == 1
    assert rozklad.get("Over 2.5") == 1


def test_rozklad_rynkow_pomija_wiersze_bez_danej_pozycji():
    """Wiersz z tylko 5 rynkami (NULL BTTS) dalej ma pozycje #1-#5 — rozklad
    dla rank=6 musi go po prostu pominac, a nie wywalic sie wyjatkiem."""
    wiersze = [_wiersz(prob_btts=None)]

    rozklad = rozklad_rynkow(wiersze, rank=6)

    assert sum(rozklad.values()) == 0


# ── raport_drugiego_wyboru (scripts/stan_uczenia.py) ────────────────────────

class _ConnRaportuD:
    """Minimalne polaczenie: jedno zapytanie SELECT, jedna lista wynikow."""

    def __init__(self, wiersze: list[dict]) -> None:
        self._wiersze = wiersze
        self.zapytania: list[str] = []

    def execute(self, zapytanie, params=None):
        self.zapytania.append(zapytanie)
        return _KursorRaportuD(self._wiersze)


class _KursorRaportuD:
    def __init__(self, wiersze: list[dict]) -> None:
        self._w = wiersze

    def fetchall(self):
        return self._w


def test_raport_drugiego_wyboru_brak_danych_mowi_o_tym_wprost(capsys):
    from scripts import stan_uczenia

    conn = _ConnRaportuD([])

    stan_uczenia.raport_drugiego_wyboru(conn)

    out = capsys.readouterr().out
    assert "BRAK DANYCH" in out


def test_raport_drugiego_wyboru_werdykt_gdy_pozycja_2_bije_1(capsys):
    """Ten sam syntetyczny zestaw co test-pulapka wyzej: pozycja #1 ma wyzsza
    surowa trafnosc, ale pozycja #2 wyzsza przewage — raport ma to wprost
    powiedziec, nie wskazac #1 tylko dlatego, ze trafia czesciej."""
    from scripts import stan_uczenia

    grupa_a_wysoka = [
        _wiersz(prob_home=20.0, prob_draw=55.0, prob_away=15.0,
                prob_over25=65.0, prob_btts=48.0, actual_result="3-1")
        for _ in range(4)
    ]
    grupa_a_niska = [
        _wiersz(prob_home=20.0, prob_draw=55.0, prob_away=15.0,
                prob_over25=65.0, prob_btts=48.0, actual_result="1-1")
    ]
    grupa_b = [
        _wiersz(prob_home=70.0, prob_draw=5.0, prob_away=10.0,
                prob_over25=40.0, prob_btts=35.0, actual_result="2-0")
        for _ in range(2)
    ]
    conn = _ConnRaportuD(grupa_a_wysoka + grupa_a_niska + grupa_b)

    stan_uczenia.raport_drugiego_wyboru(conn)

    out = capsys.readouterr().out
    assert "BIJE typ główny" in out
    assert "#2" in out
    assert "mala proba" in out  # n=7 < PROG_MALA_PROBA


def test_raport_drugiego_wyboru_werdykt_gdy_pozycja_1_wygrywa(monkeypatch, capsys):
    """Kontrprzyklad: gdy #1 ma najwyzsza przewage, raport ma to powiedziec
    bez sugerowania, ze drugi wybor jest lepszy. Liczenie samej przewagi ma
    juz osobny, wyczerpujacy test wyzej — tu sprawdzamy WYLACZNIE formatowanie
    werdyktu raportu, wiec `przewaga_nad_baza`/`rozklad_rynkow` sa zamockowane."""
    import footstats.core.ranking_rynkow as rr
    from scripts import stan_uczenia

    wyniki = {
        1: {"n": 50, "trafnosc": 60.0, "baza": 44.0, "przewaga": 16.0},
        2: {"n": 50, "trafnosc": 40.0, "baza": 30.0, "przewaga": 10.0},
        3: {"n": 50, "trafnosc": 35.0, "baza": 32.5, "przewaga": 2.5},
    }
    monkeypatch.setattr(rr, "przewaga_nad_baza", lambda wiersze, rank: wyniki[rank])
    monkeypatch.setattr(rr, "rozklad_rynkow", lambda wiersze, rank: {"1": len(wiersze)})

    conn = _ConnRaportuD([_wiersz()])

    stan_uczenia.raport_drugiego_wyboru(conn)

    out = capsys.readouterr().out
    assert "typ główny" in out
    assert "NIE bije" in out
