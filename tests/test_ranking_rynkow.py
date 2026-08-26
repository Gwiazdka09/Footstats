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

REVIEW 2026-08-26: `przewaga_nad_baza`/`rozklad_rynkow`/`rozklad_z_przewaga`
przyjmują `rankingi` (wynik `ranking_rynkow` policzony RAZ na wiersz), nie
surowe wiersze `model_log` — patrz uzasadnienie w module `ranking_rynkow.py`.
"""
from __future__ import annotations

import pytest

from footstats.core.ranking_rynkow import (
    policz_nierozliczalne,
    przewaga_nad_baza,
    ranking_rynkow,
    rozklad_rynkow,
    rozklad_z_przewaga,
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


def _rankingi(wiersze: list[dict]) -> list[list[dict]]:
    """Skrót testowy — dokladnie to, co raport ma robic RAZ na wiersz."""
    return [ranking_rynkow(w) for w in wiersze]


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
    rankingi = _rankingi(wiersze)

    rank1 = przewaga_nad_baza(rankingi, rank=1)
    rank2 = przewaga_nad_baza(rankingi, rank=2)

    assert rank1["n"] == 7
    assert rank2["n"] == 7
    # Surowa trafnosc: #1 wygrywa.
    assert rank1["trafnosc"] > rank2["trafnosc"]
    # Przewaga nad baza: #2 wygrywa — to jest sedno zadania.
    assert rank2["przewaga"] > rank1["przewaga"]
    assert rank1["trafnosc"] == pytest.approx(600 / 7)
    assert rank2["trafnosc"] == pytest.approx(300 / 7)


def test_przewaga_nad_baza_rozroznia_brak_pozycji_od_nierozliczalnego():
    """MEDIUM z review: n==0 ma DWIE rozne przyczyny — sklejenie ich dawalo
    raportowi falszywa diagnoze."""
    # Wiersz A: tylko 5 rynkow (NULL BTTS) — pozycja #6 w ogole nie istnieje.
    brak_pozycji = ranking_rynkow(_wiersz(prob_btts=None))
    # Wiersz B: komplet 7 rynkow, ale wynik nierozliczalny (AET) — pozycja
    # #6 ISTNIEJE, tylko `trafiony` jest None.
    nierozliczalny = ranking_rynkow(_wiersz(actual_result="2-1 (AET)"))

    wynik = przewaga_nad_baza([brak_pozycji, nierozliczalny], rank=6)

    assert wynik["n"] == 0
    assert wynik["brak_pozycji"] == 1
    assert wynik["nierozliczalne"] == 1


def test_policz_nierozliczalne_liczy_pelne_awarie_wyniku():
    rozliczalny = ranking_rynkow(_wiersz(actual_result="2-1"))
    nierozliczalny = ranking_rynkow(_wiersz(actual_result="2-1 (AET)"))

    assert policz_nierozliczalne([rozliczalny, nierozliczalny, nierozliczalny]) == 2


# ── 7. rozklad_rynkow — spojny mianownik z przewaga_nad_baza ────────────────

def test_rozklad_rynkow_sumuje_sie_do_n_rozliczalnych_nie_do_wszystkich_wierszy():
    """Nazwa i asercja MUSZA odpowiadac `n` z `przewaga_nad_baza`, nie
    surowej liczbie wierszy — inaczej rozklad i tabela trafnosci nad nim
    licza z roznych mianownikow (review 26.08: rozklad sumowal sie do 427,
    tabela mowila n=424 dla tej samej pozycji)."""
    wiersze = [
        _wiersz(prob_home=60.0, prob_draw=10.0, prob_away=10.0,
                prob_over25=55.0, prob_btts=55.0, actual_result="1-0"),
        _wiersz(prob_home=10.0, prob_draw=15.0, prob_away=75.0,
                prob_over25=40.0, prob_btts=30.0, actual_result="0-2"),
        _wiersz(prob_home=20.0, prob_draw=15.0, prob_away=15.0,
                prob_over25=90.0, prob_btts=30.0, actual_result="2-2"),
        # Nierozliczalny — rank1 istnieje ("1", prob_home=60 najwyzsze), ale
        # AET nie pozwala go rozliczyc. Rozklad MA go pominac, tak jak
        # `przewaga_nad_baza`.
        _wiersz(prob_home=60.0, prob_draw=10.0, prob_away=10.0,
                prob_over25=55.0, prob_btts=55.0, actual_result="2-1 (AET)"),
    ]
    rankingi = _rankingi(wiersze)

    rozklad = rozklad_rynkow(rankingi, rank=1)
    n_z_przewagi = przewaga_nad_baza(rankingi, rank=1)["n"]

    assert n_z_przewagi == 3
    assert sum(rozklad.values()) == n_z_przewagi
    assert rozklad.get("1") == 1
    assert rozklad.get("2") == 1
    assert rozklad.get("Over 2.5") == 1


def test_rozklad_rynkow_pomija_wiersze_bez_danej_pozycji():
    """Wiersz z tylko 5 rynkami (NULL BTTS) dalej ma pozycje #1-#5 — rozklad
    dla rank=6 musi go po prostu pominac, a nie wywalic sie wyjatkiem."""
    rankingi = _rankingi([_wiersz(prob_btts=None)])

    rozklad = rozklad_rynkow(rankingi, rank=6)

    assert sum(rozklad.values()) == 0


# ── 8. rozklad_z_przewaga — MEDIUM z review: naglowkowe +Xpp ukrywa rynki ───

def test_rozklad_z_przewaga_ma_metryki_per_rynek_i_jest_posortowany():
    """Naglowkowe uśrednienie po calej pozycji #1 ukrywa, ze najczestszy
    rynek moze miec przewage UJEMNA (review 26.08: BTTS n=134, -3.3pp).
    Tabela per-rynek ma to pokazac wprost, posortowana malejaco po n."""
    # 4 wiersze z rynkiem "1" na #1 (wiekszy koszyk, 3 trafienia/4),
    # 2 wiersze z rynkiem "X" na #1 (mniejszy koszyk, 2 trafienia/2).
    wiersze_jeden = [
        _wiersz(prob_home=60.0, prob_draw=10.0, prob_away=10.0,
                prob_over25=55.0, prob_btts=55.0, actual_result=wynik)
        for wynik in ("1-0", "1-0", "1-0", "0-1")
    ]
    wiersze_x = [
        _wiersz(prob_home=10.0, prob_draw=60.0, prob_away=10.0,
                prob_over25=55.0, prob_btts=55.0, actual_result=wynik)
        for wynik in ("1-1", "1-1")
    ]
    rankingi = _rankingi(wiersze_jeden + wiersze_x)

    rozklad = rozklad_z_przewaga(rankingi, rank=1)

    assert [poz["rynek"] for poz in rozklad] == ["1", "X"]  # malejaco po n
    jeden = next(p for p in rozklad if p["rynek"] == "1")
    x = next(p for p in rozklad if p["rynek"] == "X")
    assert jeden["n"] == 4
    assert x["n"] == 2
    assert jeden["trafnosc"] == pytest.approx(75.0)
    assert x["trafnosc"] == pytest.approx(100.0)
    assert jeden["przewaga"] == pytest.approx(jeden["trafnosc"] - jeden["baza"])
    assert x["przewaga"] == pytest.approx(x["trafnosc"] - x["baza"])


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


def test_raport_drugiego_wyboru_zapytanie_wybiera_wlasciwe_kolumny():
    """`_ConnRaportuD.zapytania` nikt dotad nie czytal — literowka w SELECT
    (np. `prob_over_25` zamiast `prob_over25`) przechodzilaby na zielono."""
    from scripts import stan_uczenia

    conn = _ConnRaportuD([_wiersz()])
    stan_uczenia.raport_drugiego_wyboru(conn)

    zapytanie = conn.zapytania[0].upper()
    for kolumna in ("PROB_HOME", "PROB_DRAW", "PROB_AWAY", "PROB_OVER25",
                    "PROB_BTTS", "ACTUAL_RESULT"):
        assert kolumna in zapytanie, zapytanie


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
    assert "pominięto" not in out  # zero nierozliczalnych w tej probce


def test_raport_drugiego_wyboru_drukuje_tabele_rynkow_z_przewaga(capsys):
    """MEDIUM z review (finding 4): tabela per-rynek na pozycji #1 ma
    pokazac n/trafnosc/baze/przewage osobno, zeby naglowkowe uśrednienie nie
    ukrylo rynku bez przewagi. Liczby wyliczone recznie jak w tescie-pulapce
    wyzej: "Over 2.5" (5 wierszy) trafnosc 80.0%, baza 4/7≈57.1%,
    przewaga≈+22.9pp; "1" (2 wiersze) trafnosc 100.0%, baza 6/7≈85.7%,
    przewaga≈+14.3pp."""
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
    assert "rozkład rynków na pozycji #1" in out
    assert "Over 2.5" in out
    assert "80.0%" in out and "57.1%" in out and "+22.9pp" in out
    assert "100.0%" in out and "85.7%" in out and "+14.3pp" in out


def test_raport_drugiego_wyboru_rozroznia_brak_pozycji_od_nierozliczalnego(capsys):
    """MEDIUM z review (finding 2): review odtworzyl wiersz majacy 7 rynkow,
    o ktorym raport mowil "zaden wiersz nie ma tylu rynkow" — falszywa
    diagnoza. Probka nizej ma WSZYSTKIE wiersze nierozliczalne (AET), mimo
    ze kazdy ma komplet 7 rynkow — raport ma to nazwac po imieniu."""
    from scripts import stan_uczenia

    wiersze = [_wiersz(actual_result="2-1 (AET)") for _ in range(3)]
    conn = _ConnRaportuD(wiersze)

    stan_uczenia.raport_drugiego_wyboru(conn)

    out = capsys.readouterr().out
    assert "pominięto 3 z 3 wierszy" in out
    assert "3 z nierozliczalnym wynikiem na tej pozycji" in out
    assert "nie ma aż 1 rynków" not in out  # to byla falszywa diagnoza sprzed fixu
    assert "brak rozliczalnych danych do werdyktu" in out


def test_raport_drugiego_wyboru_gdy_pozycja_1_bez_danych_nie_udaje_zwyciezcy(monkeypatch, capsys):
    """MEDIUM z review (finding 1): gdy #1 nie ma rozliczalnych danych,
    raport NIE MOZE twierdzic, ze "#1 ma najwyzsza przewage" — to byla
    dziura, w ktorej `1 not in dostepne` doklejalo brak danych do
    zwyciestwa #1."""
    import footstats.core.ranking_rynkow as rr
    from scripts import stan_uczenia

    wyniki = {
        1: {"n": 0, "trafnosc": None, "baza": None, "przewaga": None,
            "brak_pozycji": 0, "nierozliczalne": 10},
        2: {"n": 10, "trafnosc": 60.0, "baza": 40.0, "przewaga": 20.0,
            "brak_pozycji": 0, "nierozliczalne": 0},
        3: {"n": 10, "trafnosc": 50.0, "baza": 45.0, "przewaga": 5.0,
            "brak_pozycji": 0, "nierozliczalne": 0},
    }
    monkeypatch.setattr(rr, "przewaga_nad_baza", lambda rankingi, rank: wyniki[rank])
    monkeypatch.setattr(rr, "rozklad_z_przewaga", lambda rankingi, rank: [])
    monkeypatch.setattr(rr, "policz_nierozliczalne", lambda rankingi: 0)

    conn = _ConnRaportuD([_wiersz()])

    stan_uczenia.raport_drugiego_wyboru(conn)

    out = capsys.readouterr().out
    assert "#1 (typ główny) bez rozliczalnych danych" in out
    assert "ma najwyższą przewagę" not in out  # #1 NIE dostaje werdyktu o wygranej
    assert "#2" in out
    assert "+20.0pp" in out


def test_raport_drugiego_wyboru_werdykt_gdy_pozycja_1_wygrywa(monkeypatch, capsys):
    """Kontrprzyklad: #1 ma NIZSZA surowa trafnosc niz #2 (45.0% < 55.0%),
    ale WYZSZA przewage (25.0pp > 13.0pp) — celowo tak, zeby test odrozniał
    poprawna logike (sortowanie po przewadze) od bledu _pomijaj_btts
    (sortowanie po trafnosci wskazaloby #2). Liczenie samej przewagi ma juz
    osobny test wyzej — tu sprawdzamy WYLACZNIE formatowanie werdyktu, wiec
    `przewaga_nad_baza`/`rozklad_z_przewaga` sa zamockowane."""
    import footstats.core.ranking_rynkow as rr
    from scripts import stan_uczenia

    wyniki = {
        1: {"n": 50, "trafnosc": 45.0, "baza": 20.0, "przewaga": 25.0,
            "brak_pozycji": 0, "nierozliczalne": 0},
        2: {"n": 50, "trafnosc": 55.0, "baza": 42.0, "przewaga": 13.0,
            "brak_pozycji": 0, "nierozliczalne": 0},
        3: {"n": 50, "trafnosc": 30.0, "baza": 28.0, "przewaga": 2.0,
            "brak_pozycji": 0, "nierozliczalne": 0},
    }
    monkeypatch.setattr(rr, "przewaga_nad_baza", lambda rankingi, rank: wyniki[rank])
    monkeypatch.setattr(rr, "rozklad_z_przewaga", lambda rankingi, rank: [])
    monkeypatch.setattr(rr, "policz_nierozliczalne", lambda rankingi: 0)

    conn = _ConnRaportuD([_wiersz()])

    stan_uczenia.raport_drugiego_wyboru(conn)

    out = capsys.readouterr().out
    assert "pozycja #1 (typ główny) ma najwyższą przewagę (+25.0pp)" in out
    assert "NIE bije" in out
    assert "BIJE typ główny" not in out
