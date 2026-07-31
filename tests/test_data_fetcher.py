"""test_data_fetcher.py — pobieranie danych ligi (MODUL 17).

PO CO: modul mial 0% pokrycia, a `_generuj_tabele_z_wynikow` liczy PUNKTY
i bilans bramek — to z tego powstaje tabela, gdy API nie odda standings.
Blad w tym liczeniu przechodzi cicho do modelu (ImportanceIndex czyta pozycje).

`time.sleep` mockowany wszedzie — produkcja czeka 3s miedzy zapytaniami
API-Football (limit 100 req/dzien).
"""
from __future__ import annotations

import pandas as pd
import pytest

import footstats.data_fetcher as dfetch


@pytest.fixture(autouse=True)
def bez_spania(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)


class _FakeAPI:
    """Atrapa APIClient / APIFootball — zapisuje wywolania."""

    def __init__(self, tab=None, wyn=None, nad=None):
        self._tab, self._wyn, self._nad = tab, wyn, nad
        self.wywolania: list[str] = []

    # football-data.org
    def tabela(self, kod):
        self.wywolania.append(f"tabela:{kod}")
        return self._tab

    def wyniki(self, kod, n):
        self.wywolania.append(f"wyniki:{kod}:{n}")
        return self._wyn

    def nadchodzace(self, kod, n):
        self.wywolania.append(f"nadchodzace:{kod}:{n}")
        return self._nad

    # api-sports.io
    def tabela_liga(self, api_id):
        self.wywolania.append(f"tabela_liga:{api_id}")
        return self._tab

    def wyniki_liga(self, api_id):
        self.wywolania.append(f"wyniki_liga:{api_id}")
        return self._wyn

    def nadchodzace_liga(self, api_id):
        self.wywolania.append(f"nadchodzace_liga:{api_id}")
        return self._nad


def _wyniki(*mecze) -> pd.DataFrame:
    return pd.DataFrame(
        [{"gospodarz": g, "goscie": a, "gole_g": gg, "gole_a": ga}
         for g, a, gg, ga in mecze]
    )


# ── pobierz_dane (football-data.org) ────────────────────────────────────────

def test_pobiera_trzy_zestawy_w_kolejnosci():
    api = _FakeAPI(tab="T", wyn="W", nad="N")
    tab, wyn, nad = dfetch.pobierz_dane(api, "E0", "Premier League")

    assert (tab, wyn, nad) == ("T", "W", "N")
    assert api.wywolania == ["tabela:E0", "wyniki:E0:100", "nadchodzace:E0:40"]


def test_brak_danych_zwraca_none_bez_wyjatku():
    api = _FakeAPI()
    assert dfetch.pobierz_dane(api, "E0", "x") == (None, None, None)


# ── pobierz_dane_apisports ──────────────────────────────────────────────────

def test_apisports_pobiera_komplet():
    af = _FakeAPI(tab="T", wyn="W", nad="N")
    tab, wyn, nad = dfetch.pobierz_dane_apisports(af, 106, "Ekstraklasa")

    assert (tab, wyn, nad) == ("T", "W", "N")
    assert af.wywolania == ["tabela_liga:106", "wyniki_liga:106", "nadchodzace_liga:106"]


def test_brak_tabeli_generuje_ja_z_wynikow(capsys):
    """Sedno fallbacku: API bez standings nie moze zostawic modelu bez tabeli."""
    wyniki = _wyniki(("Legia", "Lech", 2, 0), ("Lech", "Legia", 1, 1))
    af = _FakeAPI(tab=None, wyn=wyniki, nad=None)

    tab, _, _ = dfetch.pobierz_dane_apisports(af, 106, "Ekstraklasa")

    assert tab is not None and not tab.empty
    assert "generuje z wynikow" in capsys.readouterr().out


def test_brak_tabeli_i_wynikow_zostawia_none():
    af = _FakeAPI(tab=None, wyn=None, nad=None)
    assert dfetch.pobierz_dane_apisports(af, 106, "x")[0] is None


# ── _generuj_tabele_z_wynikow ───────────────────────────────────────────────

def test_pusty_wejsciowy_daje_pusta_tabele():
    assert dfetch._generuj_tabele_z_wynikow(pd.DataFrame()).empty
    assert dfetch._generuj_tabele_z_wynikow(None).empty


def test_punkty_liczone_3_za_zwyciestwo_1_za_remis():
    # Legia: wygrana u siebie (3) + remis na wyjezdzie (1) = 4 pkt
    # Lech:  przegrana (0) + remis (1) = 1 pkt
    tab = dfetch._generuj_tabele_z_wynikow(
        _wyniki(("Legia", "Lech", 2, 0), ("Lech", "Legia", 1, 1))
    )
    legia = tab[tab["Druzyna"] == "Legia"].iloc[0]
    lech = tab[tab["Druzyna"] == "Lech"].iloc[0]

    assert legia["Pkt"] == 4 and legia["W"] == 1 and legia["R"] == 1 and legia["P"] == 0
    assert lech["Pkt"] == 1 and lech["W"] == 0 and lech["R"] == 1 and lech["P"] == 1


def test_wygrana_na_wyjezdzie_liczona_poprawnie():
    """Regresja: na wyjezdzie wygrywa ten, kto ma WIECEJ goli jako `gole_a`."""
    tab = dfetch._generuj_tabele_z_wynikow(_wyniki(("Legia", "Lech", 0, 3)))
    lech = tab[tab["Druzyna"] == "Lech"].iloc[0]
    assert lech["W"] == 1 and lech["Pkt"] == 3


def test_bilans_bramek_z_obu_stron():
    tab = dfetch._generuj_tabele_z_wynikow(
        _wyniki(("Legia", "Lech", 3, 1), ("Lech", "Legia", 2, 0))
    )
    legia = tab[tab["Druzyna"] == "Legia"].iloc[0]
    assert legia["BZ"] == 3 and legia["BS"] == 3      # 3+0 strzelone, 1+2 stracone
    assert legia["Bramki"] == "3:3"
    assert legia["+/-"] == 0


def test_sortowanie_malejaco_po_punktach_i_numeracja():
    tab = dfetch._generuj_tabele_z_wynikow(
        _wyniki(("A", "B", 5, 0), ("C", "D", 0, 0))
    )
    assert list(tab["Poz."]) == [1, 2, 3, 4]
    assert tab.iloc[0]["Druzyna"] == "A"          # jedyny z 3 pkt
    assert tab.iloc[0]["Pkt"] >= tab.iloc[-1]["Pkt"]


def test_liczba_meczow_sumuje_dom_i_wyjazd():
    tab = dfetch._generuj_tabele_z_wynikow(
        _wyniki(("A", "B", 1, 0), ("B", "A", 2, 2), ("A", "C", 0, 1))
    )
    a = tab[tab["Druzyna"] == "A"].iloc[0]
    assert a["M"] == 3


def test_tabela_ma_komplet_kolumn():
    tab = dfetch._generuj_tabele_z_wynikow(_wyniki(("A", "B", 1, 0)))
    for kol in ("Poz.", "Druzyna", "M", "W", "R", "P", "BZ", "BS", "Bramki", "+/-", "Pkt"):
        assert kol in tab.columns
