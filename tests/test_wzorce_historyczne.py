"""Wzorce z historii — paliwo dla RAG, którego dziś nie ma wcale.

PO CO: `pobierz_rag_wzorce` liczy skuteczność czynników z tabeli `predictions`.
Zmierzone na produkcji 09.08.2026: **0 rozliczonych predykcji z niepustymi
`factors`**, więc funkcja zwraca pusty string niezależnie od zapytania i będzie
tak robić tygodniami — przy ~4 predykcjach dziennie i 29% trafień czynnika.

A obok leży 139 102 mecze historii, z których ta warstwa nigdy nie skorzystała.
Zmierzone walk-forwardem na 2492 meczach 10 lig (baza: trafność typu 47,5%):

    PATENT    n=170  57,6%  (+10,1 pp)
    TWIERDZA  n=496  53,4%  (+5,9 pp)
    ZEMSTA    n=199  45,7%  (−1,8 pp), ale gospodarz wygrywa 31,7% vs 43,0%

Czynniki niosą sygnał, więc tablica historyczna to nie proteza — to lepsze
źródło niż garstka własnych predykcji.

LOOKAHEAD: tablica agreguje mecze do daty budowy i służy do predykcji meczów
PÓŹNIEJSZYCH. Dlatego plik MUSI nieść `zbudowano_do` — bez tej daty nie da się
stwierdzić, czy backtest na starym oknie nie czyta własnej przyszłości.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from footstats.core.wzorce_historyczne import (
    buduj_tablice,
    formatuj_wzorce,
    wczytaj_tablice,
)


def _mecze(pary: list[tuple[str, list[str], str]]) -> list[dict]:
    """(typ modelu, czynniki, faktyczny wynik) → rekordy jak z walk-forwardu."""
    return [{"typ": t, "czynniki": cz, "wynik": w} for t, cz, w in pary]


class TestBudowanie:
    def test_liczy_trafienia_per_czynnik_i_typ(self):
        dane = _mecze([
            ("H", ["PATENT"], "H"), ("H", ["PATENT"], "H"),
            ("H", ["PATENT"], "A"), ("H", ["TWIERDZA"], "H"),
        ])

        tab = buduj_tablice(dane, min_probek=1)

        assert tab["wzorce"]["PATENT->H"] == {"n": 3, "trafien": 2}
        assert tab["wzorce"]["TWIERDZA->H"] == {"n": 1, "trafien": 1}

    def test_kombinacja_czynnikow_jest_osobnym_wzorcem(self):
        """Dwa czynniki naraz to mocniejszy sygnal niz kazdy z osobna."""
        dane = _mecze([("H", ["PATENT", "TWIERDZA"], "H")] * 4)

        tab = buduj_tablice(dane, min_probek=1)

        assert "PATENT+TWIERDZA->H" in tab["wzorce"]

    def test_wzorce_ponizej_progu_wypadaja(self):
        """Wzorzec z dwoch meczow to szum udajacy wiedze."""
        dane = _mecze([("H", ["PATENT"], "H")] * 2 + [("H", ["TWIERDZA"], "H")] * 10)

        tab = buduj_tablice(dane, min_probek=5)

        assert "PATENT->H" not in tab["wzorce"]
        assert "TWIERDZA->H" in tab["wzorce"]

    def test_mecze_bez_czynnikow_nie_tworza_wzorca(self):
        tab = buduj_tablice(_mecze([("H", [], "H")] * 20), min_probek=1)
        assert not tab["wzorce"]

    def test_tablica_niesie_date_do_ktorej_zbudowano(self):
        """Bez tego nie da sie wykryc lookaheadu w backtescie."""
        tab = buduj_tablice(_mecze([("H", ["PATENT"], "H")] * 5), min_probek=1,
                            zbudowano_do="2026-08-09")
        assert tab["zbudowano_do"] == "2026-08-09"

    def test_zapisuje_liczbe_meczow_zrodlowych(self):
        tab = buduj_tablice(_mecze([("H", ["PATENT"], "H")] * 7), min_probek=1)
        assert tab["n_meczow"] == 7


class TestFormatowanie:
    def test_zwraca_format_oczekiwany_przez_prompt(self):
        tab = {"wzorce": {"PATENT->1": {"n": 170, "trafien": 98}}}

        wynik = formatuj_wzorce(tab, ["PATENT"], "1")

        assert "PATENT->1" in wynik
        assert "98/170" in wynik
        assert "58%" in wynik

    def test_bez_pasujacych_czynnikow_zwraca_pusto(self):
        tab = {"wzorce": {"PATENT->1": {"n": 170, "trafien": 98}}}
        assert formatuj_wzorce(tab, ["ZEMSTA"], "1") == ""

    def test_pusta_tablica_nie_wywala(self):
        assert formatuj_wzorce({}, ["PATENT"], "1") == ""

    def test_wynik_jest_krotki(self):
        """Wzorce jada do promptu, ktory 09.08 pekl na limicie tokenow."""
        tab = {"wzorce": {f"F{i}->1": {"n": 100, "trafien": 50} for i in range(20)}}

        wynik = formatuj_wzorce(tab, [f"F{i}" for i in range(20)], "1")

        assert len(wynik) < 200, f"za dlugie ({len(wynik)} znakow) jak na prompt"


class TestWczytywanie:
    def test_brak_pliku_zwraca_pusta_tablice(self, tmp_path, monkeypatch):
        """Brak pliku ma degradowac RAG, nie wywracac predykcji."""
        monkeypatch.setattr("footstats.core.wzorce_historyczne.SCIEZKA",
                            tmp_path / "nie_ma.json")
        assert wczytaj_tablice() == {}

    def test_uszkodzony_plik_zwraca_pusta_tablice(self, tmp_path, monkeypatch):
        plik = tmp_path / "wzorce.json"
        plik.write_text("{to nie json", encoding="utf-8")
        monkeypatch.setattr("footstats.core.wzorce_historyczne.SCIEZKA", plik)
        assert wczytaj_tablice() == {}

    def test_wczytuje_zapisana_tablice(self, tmp_path, monkeypatch):
        plik = tmp_path / "wzorce.json"
        plik.write_text(json.dumps({"wzorce": {"PATENT->1": {"n": 5, "trafien": 3}}}),
                        encoding="utf-8")
        monkeypatch.setattr("footstats.core.wzorce_historyczne.SCIEZKA", plik)

        assert wczytaj_tablice()["wzorce"]["PATENT->1"]["n"] == 5


class TestOdpornosc:
    def test_zero_meczow_daje_pusta_tablice_bez_wyjatku(self):
        assert buduj_tablice([], min_probek=1)["wzorce"] == {}

    @pytest.mark.parametrize("brak", ["typ", "wynik"])
    def test_niepelny_rekord_jest_pomijany(self, brak):
        rekord = {"typ": "H", "czynniki": ["PATENT"], "wynik": "H"}
        del rekord[brak]

        tab = buduj_tablice([rekord] * 10, min_probek=1)

        assert tab["wzorce"] == {}

    def test_nie_dzieli_przez_zero_przy_formatowaniu(self):
        tab = {"wzorce": {"PATENT->1": {"n": 0, "trafien": 0}}}
        assert formatuj_wzorce(tab, ["PATENT"], "1") == ""


def test_ramka_pandas_tez_dziala():
    """Generator karmi to walk-forwardem, ktory naturalnie trzyma dane w ramce."""
    df = pd.DataFrame(_mecze([("H", ["PATENT"], "H")] * 6))

    tab = buduj_tablice(df.to_dict("records"), min_probek=3)

    assert tab["wzorce"]["PATENT->H"]["n"] == 6
