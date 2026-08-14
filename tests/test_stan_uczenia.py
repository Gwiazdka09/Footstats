"""Raport stanu pętli uczenia — liczy to, co trzeba, i nie pisze do bazy.

PO CO: ten skrypt jest narzędziem diagnostycznym, którym podejmuje się decyzje
o modelu („czy RAG ma paliwo", „czy można ogłosić werdykt"). Jeśli policzy źle,
podejmiemy złą decyzję i nie dowiemy się o tym — dokładnie tak jak przy
`json_each`, które zwracało pusty string zamiast błędu.

Dwie rzeczy pilnowane twardo:
  * `factors = '[]'` to BRAK czynników, nie czynnik. Zliczenie tego jako
    „wypełnione" pokazałoby pętlę jako działającą, gdy stoi.
  * raport jest READ-ONLY — ma prawo dotknąć produkcji, więc nie może do niej pisać.
"""
from __future__ import annotations

import ast
from pathlib import Path

from scripts import stan_uczenia

ROOT = Path(__file__).resolve().parents[1]
SKRYPT = ROOT / "scripts" / "stan_uczenia.py"


class _Conn:
    """Minimalne połączenie zwracające zaplanowane wiersze po kolei."""

    def __init__(self, odpowiedzi: list[list[dict]]):
        self.odpowiedzi = list(odpowiedzi)
        self.zapytania: list[str] = []

    def execute(self, zapytanie, params=None):
        self.zapytania.append(zapytanie)
        wiersze = self.odpowiedzi.pop(0) if self.odpowiedzi else []
        return _Kursor(wiersze)


class _Kursor:
    def __init__(self, wiersze):
        self._w = wiersze

    def fetchall(self):
        return self._w


def test_puste_factors_nie_licza_sie_jako_wypelnione():
    """Sedno: '[]' to brak czynnikow. Zapytanie musi je wykluczac."""
    conn = _Conn([[{"model_source": "poisson-dc", "wszystkie": 9,
                    "z_faktorami": 0, "rozliczone": 9, "trafione": 2}]])

    stan_uczenia.raport_predykcji(conn)

    sql = conn.zapytania[0]
    assert "factors <> '[]'" in sql, "raport policzylby puste factors jako wypelnione"


def test_raport_predykcji_zwraca_mape_po_modelu():
    conn = _Conn([[
        {"model_source": "poisson-dc", "wszystkie": 9, "z_faktorami": 1,
         "rozliczone": 9, "trafione": 2},
        {"model_source": "bzzoiro-ml", "wszystkie": 214, "z_faktorami": 0,
         "rozliczone": 121, "trafione": 47},
    ]])

    wynik = stan_uczenia.raport_predykcji(conn)

    assert wynik["poisson-dc"]["rozliczone"] == 9
    assert wynik["bzzoiro-ml"]["trafione"] == 47


def test_gotowosc_liczy_ile_brakuje_do_progu(capsys):
    stan_uczenia.raport_gotowosci({
        "poisson-dc": {"rozliczone": 9},
        "bzzoiro-ml": {"rozliczone": 121},
    })

    wyjscie = capsys.readouterr().out
    assert f"brakuje {stan_uczenia.MIN_ROZLICZONYCH - 9}" in wyjscie
    assert "gotowe" in wyjscie


def test_brak_modelu_w_danych_nie_wywala_raportu(capsys):
    """Model, ktory jeszcze nic nie wyprodukowal, ma sie pokazac jako 0, nie krzyknac."""
    stan_uczenia.raport_gotowosci({})

    assert "poisson-dc" in capsys.readouterr().out


def test_wzorce_mowia_wprost_ze_to_brak_paliwa_nie_awaria(capsys):
    conn = _Conn([[{"gotowe": 0}]])

    stan_uczenia.raport_wzorcow(conn)

    wyjscie = capsys.readouterr().out
    assert "brak paliwa" in wyjscie.lower()


def test_skrypt_nie_pisze_do_bazy():
    """Raport diagnostyczny biegnie po PRODUKCJI — ma prawo tylko czytac.

    Sprawdzamy LITERALY tekstowe wygladajace na SQL, nie caly plik: naiwne
    szukanie podciagu "INSERT" lapie `sys.path.insert` i test staje sie
    bezwartosciowy (dokladnie to zrobil przy pierwszym uruchomieniu).
    """
    zabronione = ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ")
    drzewo = ast.parse(SKRYPT.read_text(encoding="utf-8"))

    literaly = [w.value for w in ast.walk(drzewo)
                if isinstance(w, ast.Constant) and isinstance(w.value, str)]
    sql = [s for s in literaly if "SELECT" in s.upper()]
    assert sql, "test stracil sens — skrypt nie ma juz zapytan"

    for zapytanie in sql:
        gorne = zapytanie.upper()
        znalezione = [z for z in zabronione if z in gorne]
        assert not znalezione, f"zapytanie modyfikuje dane ({znalezione}): {zapytanie[:60]}"


def test_skrypt_parsuje_sie_i_ma_main():
    drzewo = ast.parse(SKRYPT.read_text(encoding="utf-8"))
    nazwy = {w.name for w in ast.walk(drzewo) if isinstance(w, ast.FunctionDef)}
    assert {"main", "raport_predykcji", "raport_lekcji", "raport_wzorcow"} <= nazwy


# ── Dziennik kalibracyjny (model_log) ─────────────────────────────────────────
#
# PO CO TE TESTY: raport pytał wyłącznie `predictions`, czyli tabelę zapisywaną
# DOPIERO po filtrach wartości. 2026-08-13 na produkcji: `kandydaci=45,
# po filtrach=0` — zero predykcji trzeci dzień z rzędu, więc raport pokazywał
# pętlę jako martwą. W tym samym czasie `model_log` zebrał 202 oceny modelu,
# z czego 105 rozliczonych (poisson-dc 65.2%, bzzoiro-ml 50.0%). Dane były,
# tylko nikt ich nie czytał.


def test_dziennik_czyta_model_log_a_nie_predictions():
    """Sedno: `predictions` gubi dni z zerem kuponów, `model_log` nie."""
    conn = _Conn([[{"model_source": "poisson-dc", "wpisow": 23,
                    "rozliczone": 23, "trafione": 15}]])

    stan_uczenia.raport_dziennika(conn)

    sql = conn.zapytania[0]
    assert "model_log" in sql, "raport dalej pyta tylko `predictions`"
    assert "predictions" not in sql


def test_dziennik_liczy_skutecznosc_per_model(capsys):
    conn = _Conn([[
        {"model_source": "poisson-dc", "wpisow": 23, "rozliczone": 23, "trafione": 15},
        {"model_source": "bzzoiro-ml", "wpisow": 179, "rozliczone": 82, "trafione": 41},
    ]])

    wynik = stan_uczenia.raport_dziennika(conn)

    assert wynik["poisson-dc"]["rozliczone"] == 23
    wyjscie = capsys.readouterr().out
    assert "65.2%" in wyjscie, "brak skutecznosci poisson-dc (15/23)"
    assert "50.0%" in wyjscie, "brak skutecznosci bzzoiro-ml (41/82)"


def test_dziennik_bez_rozliczen_nie_dzieli_przez_zero(capsys):
    """Świeży model ma 0 rozliczonych — raport ma to pokazać, nie wybuchnąć."""
    conn = _Conn([[{"model_source": "poisson-dc", "wpisow": 10,
                    "rozliczone": 0, "trafione": 0}]])

    stan_uczenia.raport_dziennika(conn)

    assert "poisson-dc" in capsys.readouterr().out


def test_dziennik_pusty_mowi_ze_to_awaria_a_nie_brak_paliwa(capsys):
    """Rozróżnienie, które kosztowało trzy dni: pusty `model_log` to awaria.

    `predictions` bywa puste legalnie (filtry odrzuciły wszystko). `model_log`
    zapisuje się PRZED filtrami, więc pustka oznacza, że job nie doszedł do
    modelu — i tak ma być zaraportowana.
    """
    conn = _Conn([[]])

    stan_uczenia.raport_dziennika(conn)

    wyjscie = capsys.readouterr().out.lower()
    assert "awaria" in wyjscie


def test_gotowosc_liczy_z_dziennika_gdy_ten_ma_wiecej(capsys):
    """Werdykt ma używać większej próby — inaczej czekamy na dane, które mamy."""
    stan_uczenia.raport_gotowosci(
        {"poisson-dc": {"rozliczone": 10}},
        dziennik={"poisson-dc": {"rozliczone": 23}},
    )

    wyjscie = capsys.readouterr().out
    assert "23" in wyjscie, "gotowosc zignorowala wieksza probe z model_log"


def test_raport_kursow_pokazuje_udzial_zweryfikowanych(capsys):
    """Kurs zapisuje sie PRZED weryfikacja — raport ma to widzieć, nie przemilczeć."""
    conn = _Conn([
        [{"model_source": "poisson-dc", "wszystkie": 10, "z_faktorami": 0,
          "rozliczone": 10, "trafione": 4}],
        [{"wszystkie": 10, "zweryfikowane": 6, "poza_filtrem": 3}],
    ])

    stan_uczenia.raport_predykcji(conn)

    out = capsys.readouterr().out
    assert "kurs zweryfikowany: 6/10 (60%)" in out
    assert "poza filtrem longshotow" in out
    assert "ROI i CLV licz wylacznie na zweryfikowanych" in out


def test_raport_kursow_milczy_gdy_wszystko_zweryfikowane(capsys):
    """Bez szumu, gdy dane są zdrowe — ostrzeżenie ma coś znaczyć."""
    conn = _Conn([
        [{"model_source": "poisson-dc", "wszystkie": 5, "z_faktorami": 0,
          "rozliczone": 5, "trafione": 3}],
        [{"wszystkie": 5, "zweryfikowane": 5, "poza_filtrem": 0}],
    ])

    stan_uczenia.raport_predykcji(conn)

    out = capsys.readouterr().out
    assert "kurs zweryfikowany: 5/5 (100%)" in out
    assert "ROI i CLV licz wylacznie" not in out


def test_raport_kursow_znosi_brak_wiersza():
    """Puste zapytanie nie moze wywalic calego raportu diagnostycznego."""
    conn = _Conn([[{"model_source": "x", "wszystkie": 1, "z_faktorami": 0,
                    "rozliczone": 0, "trafione": 0}]])

    stan_uczenia.raport_predykcji(conn)   # brak drugiej odpowiedzi → [] 
