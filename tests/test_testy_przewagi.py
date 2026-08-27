"""ZADANIE S — dwa raporty pisane dziś ad hoc mają zamieszkać w kodzie.

RAPORT 1 (`raport_kalibracji_1x2`): czy pewność modelu we WŁASNYM typie
(GREATEST z trzech prawdopodobieństw 1X2) jest wiarygodna — koszyki pewności
zestawione z realną trafnością, jak w `raport_rynkow_golowych`/`raport_remisow`.

RAPORT 2 (`policz_przewage` + `raport_przewagi_nad_kursem`): TO JEST LICZBA,
KTÓRA PRZESĄDZA O FLAGACH SELEKCJI. Wszystkie pozostałe raporty w tym pliku
mierzą przewagę modelu nad WŁASNĄ bazą częstości. Ten mierzy, czy bijemy CENĘ
bukmachera — jedyna poprzeczka mająca związek z pieniędzmi (patrz
`.claude/rules/wypuszczenie-pl.md`).
"""
from __future__ import annotations

import json

import pytest

# UWAGA na nazewnictwo: funkcja produkcyjna nazywa sie `policz_przewage`, a nie
# `test_przewagi`, celowo. Pytest kolekcjonuje kazda nazwe `test_*` widoczna w pliku
# testowym — takze zaimportowana — i probowalby uruchomic funkcje produkcyjna jako test,
# wywalajac sie na braku fixture `kupony`. Nie nazywaj tak funkcji w `src/`.
from footstats.core.testy_przewagi import (
    korekta_sidaka,
    kupon_z_legs,
    poisson_binomial_cdf,
    policz_przewage,
)
from scripts import stan_uczenia

ROOT_TEKST = stan_uczenia.__file__


# ── poisson_binomial_cdf ────────────────────────────────────────────────────

def test_cdf_wartosc_znana_analitycznie_p_rowne():
    """Binomial(4, 0.5): P(X<=2) = (C(4,0)+C(4,1)+C(4,2))/16 = 11/16 dokladnie."""
    assert poisson_binomial_cdf([0.5, 0.5, 0.5, 0.5], 2) == pytest.approx(11 / 16)


def test_cdf_wartosc_znana_analitycznie_drugi_przypadek():
    """Binomial(3, 0.3): P(X<=1) = 0.7**3 + 3*0.3*0.7**2 = 0.343 + 0.441 = 0.784."""
    assert poisson_binomial_cdf([0.3, 0.3, 0.3], 1) == pytest.approx(0.784)


def test_cdf_k_rowne_n_daje_jeden():
    assert poisson_binomial_cdf([0.2, 0.5, 0.8], 3) == pytest.approx(1.0)


def test_cdf_k_minus_jeden_daje_zero():
    assert poisson_binomial_cdf([0.2, 0.5, 0.8], -1) == 0.0


def test_cdf_z_roznymi_p():
    """P(X<=1) dla p=[0.2, 0.5, 0.8] policzone recznie:

    P(0) = 0.8*0.5*0.2 = 0.08
    P(1) = 0.2*0.5*0.2 + 0.8*0.5*0.2 + 0.8*0.5*0.8 = 0.02 + 0.08 + 0.32 = 0.42
    P(X<=1) = 0.08 + 0.42 = 0.50
    """
    assert poisson_binomial_cdf([0.2, 0.5, 0.8], 1) == pytest.approx(0.50)


# ── korekta_sidaka ───────────────────────────────────────────────────────────

def test_korekta_sidaka_jednego_porownania_nie_zmienia_p():
    assert korekta_sidaka(0.05, 1) == pytest.approx(0.05)


def test_korekta_sidaka_rosnie_z_liczba_porownan():
    a = korekta_sidaka(0.05, 1)
    b = korekta_sidaka(0.05, 5)
    c = korekta_sidaka(0.05, 20)
    assert a < b < c, "korekta ma rosnac wraz z liczba testowanych rynkow"


def test_korekta_sidaka_zera_zostaje_zerem():
    assert korekta_sidaka(0.0, 7) == 0.0


# ── kupon_z_legs: parsowanie rynku, grupowanie 1X2 ─────────────────────────

@pytest.mark.parametrize("tip", ["1", "X", "2"])
def test_kupon_z_legs_grupuje_1x2(tip):
    rekord = {"legs_json": json.dumps([{"tip": tip}])}
    assert kupon_z_legs(rekord)["rynek"] == "1X2"


def test_kupon_z_legs_zostawia_inne_rynki_bez_zmian():
    rekord = {"legs_json": json.dumps([{"tip": "BTTS"}])}
    assert kupon_z_legs(rekord)["rynek"] == "BTTS"


@pytest.mark.parametrize("legs_json", [None, "", "nie jest jsonem", "[]",
                                        json.dumps([{"brak_tip": 1}])])
def test_kupon_z_legs_uszkodzony_lub_pusty_zwraca_none(legs_json):
    assert kupon_z_legs({"legs_json": legs_json}) is None


# ── policz_przewage: budowa kuponów pomocnicza ────────────────────────────────

def _kupon(status: str, total_odds: float, tip: str = "1",
           stake: float = 10.0, payout: float | None = None) -> dict:
    if payout is None:
        payout = round(stake * total_odds, 2) if status == "WON" else 0.0
    return {
        "status": status,
        "total_odds": total_odds,
        "stake_pln": stake,
        "payout_pln": payout,
        "legs_json": json.dumps([{"tip": tip}]),
    }


def test_test_przewagi_trafnosc_rowna_hipotezie_zerowej_daje_p_i_roi_blisko_zera():
    """Rynek, w ktorym rzeczywista trafnosc = DOKLADNIE 1/kurs (hipoteza zerowa
    prawdziwa), ma dac p bliskie 0.5 (brak sygnalu w zadna strone) i ROI
    bliskie 0% (w tym syntetycznym przykladzie kurs = dokladna odwrotnosc p,
    wiec zero marzy ksiegarni — realny rynek dawalby ROI lekko ujemne)."""
    kupony = [_kupon("WON" if i < 50 else "LOST", 2.0, tip="BTTS") for i in range(100)]

    wynik = policz_przewage(kupony)

    dane = wynik["rynki"]["BTTS"]
    assert dane["n"] == 100
    assert dane["trafienia"] == 50
    assert abs(dane["p_surowe"] - 0.5) < 0.1, dane["p_surowe"]
    assert abs(dane["roi"]) < 1.0, dane["roi"]


def test_test_przewagi_zero_kuponow_nie_wywala_sie():
    wynik = policz_przewage([])

    assert wynik["rynki"] == {}
    assert wynik["n_wejsciowe"] == 0
    assert wynik["pominieto_kurs"] == 0
    assert wynik["pominieto_legs"] == 0


def test_test_przewagi_pomija_kurs_ponizej_lub_rownej_jeden_i_liczy_ile():
    kupony = [
        _kupon("WON", 1.0, tip="1"),
        _kupon("LOST", 0.5, tip="1"),
        _kupon("WON", 2.0, tip="1"),
    ]

    wynik = policz_przewage(kupony)

    assert wynik["pominieto_kurs"] == 2
    assert wynik["rynki"]["1X2"]["n"] == 1


def test_test_przewagi_pomija_uszkodzony_legs_json_bez_wyjatku_i_liczy_ile():
    zle = [
        {"status": "WON", "total_odds": 2.0, "stake_pln": 10, "payout_pln": 20,
         "legs_json": None},
        {"status": "WON", "total_odds": 2.0, "stake_pln": 10, "payout_pln": 20,
         "legs_json": ""},
        {"status": "WON", "total_odds": 2.0, "stake_pln": 10, "payout_pln": 20,
         "legs_json": "smiec"},
        {"status": "WON", "total_odds": 2.0, "stake_pln": 10, "payout_pln": 20,
         "legs_json": "[]"},
        {"status": "WON", "total_odds": 2.0, "stake_pln": 10, "payout_pln": 20,
         "legs_json": json.dumps([{"brak_tip": 1}])},
    ]

    wynik = policz_przewage(zle)

    assert wynik["pominieto_legs"] == 5
    assert wynik["rynki"] == {}


def test_test_przewagi_p_po_korekcie_uzywa_liczby_rynkow():
    """Sidak na 2 rynki ma dac inna wartosc niz surowe p — sprawdzone wprost
    formula, zeby nie byla to tautologia (p_po_korekcie != p_surowe, gdy
    liczba rynkow > 1 i p_surowe nie jest ani 0 ani 1)."""
    kupony = (
        [_kupon("LOST", 2.0, tip="BTTS") for _ in range(10)]
        + [_kupon("WON", 2.0, tip="Over 2.5") for _ in range(10)]
    )

    wynik = policz_przewage(kupony)

    btts = wynik["rynki"]["BTTS"]
    assert btts["p_po_korekcie"] == pytest.approx(korekta_sidaka(btts["p_surowe"], 2))
    assert btts["p_po_korekcie"] > btts["p_surowe"]


# ── raport_kalibracji_1x2 (scripts/stan_uczenia.py) ─────────────────────────

class _ConnKalibracji:
    """Minimalne polaczenie zwracajace ustalone wiersze i notujace zapytania."""

    def __init__(self, wiersze: list[dict]):
        self.wiersze = wiersze
        self.zapytania: list[str] = []

    def execute(self, zapytanie, params=None):
        self.zapytania.append(zapytanie)
        return _KursorKalibracji(self.wiersze)


class _KursorKalibracji:
    def __init__(self, wiersze):
        self._w = wiersze

    def fetchall(self):
        return self._w


def _linia(tekst: str, etykieta: str) -> str:
    return next(w for w in tekst.splitlines() if w.strip().startswith(etykieta))


def test_raport_kalibracji_1x2_brak_danych(capsys):
    conn = _ConnKalibracji([])

    stan_uczenia.raport_kalibracji_1x2(conn)

    assert "BRAK DANYCH" in capsys.readouterr().out


def test_raport_kalibracji_1x2_zapytanie_wyklucza_null(capsys):
    conn = _ConnKalibracji([])

    stan_uczenia.raport_kalibracji_1x2(conn)

    zapytanie = " ".join(conn.zapytania[0].split()).upper()
    assert "PROB_HOME IS NOT NULL" in zapytanie, zapytanie


def test_raport_kalibracji_1x2_koszyki_maja_poprawne_granice(capsys):
    """40.0/50.0/60.0/70.0 musza trafiac do WYZSZEGO koszyka (przedzialy
    domkniete od dolu, otwarte od gory) — test dobrany tak, ze zle domkniecie
    ktoregokolwiek progu przesuwa liczebnosc miedzy koszykami i test pada."""
    wiersze = [
        {"pewnosc": 39.9, "tip_correct": 1},
        {"pewnosc": 40.0, "tip_correct": 0},
        {"pewnosc": 49.9, "tip_correct": 1},
        {"pewnosc": 50.0, "tip_correct": 0},
        {"pewnosc": 59.9, "tip_correct": 1},
        {"pewnosc": 60.0, "tip_correct": 0},
        {"pewnosc": 69.9, "tip_correct": 1},
        {"pewnosc": 70.0, "tip_correct": 1},
    ]
    conn = _ConnKalibracji(wiersze)

    stan_uczenia.raport_kalibracji_1x2(conn)

    out = capsys.readouterr().out
    assert "n=   1" in _linia(out, "<40%")
    assert "n=   2" in _linia(out, "40-50%")
    assert "n=   2" in _linia(out, "50-60%")
    assert "n=   2" in _linia(out, "60-70%")
    assert "n=   1" in _linia(out, "70%+")


def test_raport_kalibracji_1x2_liczy_roznice_realna_minus_deklarowana(capsys):
    """roznica = REALNA minus DEKLAROWANA — kolejnosc odjecia jest sednem
    raportu (mowi, czy model jest zbyt pewny czy niedoszacowany).
    n=5: model=(44*3+46*2)/5=44.8, realnie=100*3/5=60.0 -> roznica=+15.2."""
    wiersze = ([{"pewnosc": 44.0, "tip_correct": 1}] * 3
               + [{"pewnosc": 46.0, "tip_correct": 0}] * 2)
    conn = _ConnKalibracji(wiersze)

    stan_uczenia.raport_kalibracji_1x2(conn)

    linia = _linia(capsys.readouterr().out, "40-50%")
    assert "model=44.8%" in linia, linia
    assert "realnie=60.0%" in linia, linia
    assert "roznica=+15.2pp" in linia, linia


def test_raport_kalibracji_1x2_werdykt_rosnie_i_rozpietosc(capsys):
    wiersze = (
        [{"pewnosc": 35.0, "tip_correct": 0}] * 60
        + [{"pewnosc": 35.0, "tip_correct": 1}] * 25   # <40%: realnie 25/85
        + [{"pewnosc": 45.0, "tip_correct": 1}] * 60
        + [{"pewnosc": 45.0, "tip_correct": 0}] * 40   # 40-50%: realnie 60/100
    )
    conn = _ConnKalibracji(wiersze)

    stan_uczenia.raport_kalibracji_1x2(conn)

    out = capsys.readouterr().out
    assert "ROSNIE" in out
    assert "rozpietosc" in out


def test_raport_kalibracji_1x2_oznacza_mala_probe(capsys):
    wiersze = ([{"pewnosc": 35.0, "tip_correct": 1}] * 5
               + [{"pewnosc": 75.0, "tip_correct": 1}] * 35)
    conn = _ConnKalibracji(wiersze)

    stan_uczenia.raport_kalibracji_1x2(conn)

    out = capsys.readouterr().out
    assert "mala proba" in _linia(out, "<40%")
    assert "mala proba" not in _linia(out, "70%+")


# ── raport_przewagi_nad_kursem (scripts/stan_uczenia.py) ────────────────────

class _ConnPrzewagi:
    """Zwraca po kolei zaplanowane odpowiedzi (lista list wierszy)."""

    def __init__(self, odpowiedzi: list[list[dict]]):
        self.odpowiedzi = list(odpowiedzi)
        self.zapytania: list[str] = []

    def execute(self, zapytanie, params=None):
        self.zapytania.append(zapytanie)
        wiersze = self.odpowiedzi.pop(0) if self.odpowiedzi else []
        return _KursorPrzewagi(wiersze)


class _KursorPrzewagi:
    def __init__(self, wiersze):
        self._w = wiersze

    def fetchall(self):
        return self._w


def test_raport_przewagi_zapytanie_filtruje_single_i_status():
    conn = _ConnPrzewagi([[]])

    stan_uczenia.raport_przewagi_nad_kursem(conn)

    zapytanie = " ".join(conn.zapytania[0].split()).upper()
    assert "KUPON_TYPE = 'SINGLE'" in zapytanie, zapytanie
    assert "STATUS IN ('WON', 'LOST')" in zapytanie, zapytanie


def test_raport_przewagi_brak_wierszy_w_bazie_mowi_o_braku_danych(capsys):
    """Brak danych w bazie to INNA diagnoza niz 'wszystko odfiltrowane' —
    zlepienie ich dawaloby falszywy trop (patrz zasady zadania)."""
    conn = _ConnPrzewagi([[]])

    stan_uczenia.raport_przewagi_nad_kursem(conn)

    out = capsys.readouterr().out
    assert "BRAK DANYCH" in out
    assert "ODFILTROWANE" not in out


def test_raport_przewagi_wszystko_odfiltrowane_to_inna_diagnoza_niz_brak_danych(capsys):
    wiersze = [
        {"status": "WON", "total_odds": 1.0, "stake_pln": 10, "payout_pln": 10,
         "legs_json": json.dumps([{"tip": "1"}])},
    ]
    conn = _ConnPrzewagi([wiersze])

    stan_uczenia.raport_przewagi_nad_kursem(conn)

    out = capsys.readouterr().out
    assert "ODFILTROWANE" in out
    assert "BRAK DANYCH" not in out


def test_raport_przewagi_pomija_kurs_i_legs_i_je_liczy(capsys):
    wiersze = [
        _kupon("WON", 1.0, tip="1"),
        {"status": "WON", "total_odds": 2.0, "stake_pln": 10, "payout_pln": 20,
         "legs_json": "smiec"},
        _kupon("WON", 2.0, tip="1"),
        _kupon("LOST", 2.0, tip="1"),
    ]
    conn = _ConnPrzewagi([wiersze])

    stan_uczenia.raport_przewagi_nad_kursem(conn)

    out = capsys.readouterr().out.lower()
    assert "kurs" in out and "1" in out
    assert "legs_json" in out


def test_raport_przewagi_pelny_przebieg_pokazuje_korekte_i_zastrzezenia(capsys):
    wiersze = (
        [_kupon("WON" if i % 2 == 0 else "LOST", 2.0, "1") for i in range(6)]
        + [_kupon("LOST", 1.5, "BTTS") for _ in range(4)]
    )
    conn = _ConnPrzewagi([wiersze])

    stan_uczenia.raport_przewagi_nad_kursem(conn)

    out = capsys.readouterr().out
    assert "1X2" in out
    assert "BTTS" in out
    assert "korekta" in out.lower() and "sidak" in out.lower()
    assert "NAJGORSZEGO" in out
    assert "NIE oznacza zysku" in out


# ── main(): kolejnosc wywolan ────────────────────────────────────────────────

def test_main_wywoluje_raporty_we_wlasciwej_kolejnosci():
    tekst = open(ROOT_TEKST, encoding="utf-8").read()
    cialo_main = tekst.split("def main() -> None:", 1)[1]

    poz_kalibracja = cialo_main.index("raport_kalibracji_1x2(")
    poz_golowe = cialo_main.index("raport_rynkow_golowych(")
    poz_drugi_wybor = cialo_main.index("raport_drugiego_wyboru(")
    poz_przewaga = cialo_main.index("raport_przewagi_nad_kursem(")
    poz_gotowosc = cialo_main.index("raport_gotowosci(")

    assert poz_kalibracja < poz_golowe, "kalibracja 1X2 ma isc PRZED rynkami golowymi"
    assert poz_drugi_wybor < poz_przewaga, "przewaga nad kursem ma byc NA KONCU raportow"
    assert poz_przewaga < poz_gotowosc, "przewaga nad kursem ma isc PRZED gotowoscia"
