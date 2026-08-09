"""Siła drużyny liczona wobec LIGI, nie wobec własnej próbki.

PO CO — to jest sedno braku rozdzielczości modelu. Dotąd `predict_match` brał
15 ostatnich meczów TEJ PARY i liczył `atak = gole / srednia`, gdzie `srednia`
była średnią z tej samej piętnastki. Drużyna dużo strzelająca dzieliła swoje
gole przez średnią, którą sama zawyżyła — sygnał się kasował, a ratingi
ściągały do 1.0. Do tego ~7 meczów na drużynę to czysty szum.

Zmierzone 09.08.2026 walk-forwardem, dwie niezależne próby:
                       Brier (4 ligi top)   Brier (6 innych lig)   trafnosc
    obecny                 0.6557               0.6639             43.9-45.8%
    ligowy (okno 30)       0.6089               0.6142             47.8-48.1%
    rynek (devig)          0.6001               0.5924             51.2-53.3%

Luka do rynku spadła z 0.0556 do 0.0088 Briera — 84% dystansu. Korekta siłą
rywala i shrinkage NIE powtórzyły się poza próbą strojenia, więc ich nie ma:
lepsze na zbiorze, na którym je strojono, gorsze na nowym.

Osobne współczynniki dom/wyjazd, bo średnia ligowa u siebie już zawiera atut
własnego boiska — mnożenie jeszcze raz przez BONUS_DOMOWY liczyłoby go dwa razy.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core.form import sily_ligowe


def _liga(mecze: list[tuple[str, str, int, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"gospodarz": g, "goscie": a, "gole_g": hg, "gole_a": ag,
          "data": f"2026-0{1 + i % 9}-01"}
         for i, (g, a, hg, ag) in enumerate(mecze)]
    )


def _liga_z_dominatorem(powtorzen: int = 5) -> pd.DataFrame:
    """Mocny strzela dużo wszystkim, Slaby traci dużo wszystkim."""
    mecze = []
    for _ in range(powtorzen):
        mecze += [
            ("Mocny", "Slaby", 4, 0), ("Mocny", "Sredni", 3, 1),
            ("Sredni", "Slaby", 2, 0), ("Slaby", "Mocny", 0, 3),
            ("Sredni", "Mocny", 1, 2), ("Slaby", "Sredni", 1, 2),
        ]
    return _liga(mecze)


class TestPodstawy:
    def test_zwraca_none_dla_pustej_ligi(self):
        assert sily_ligowe(pd.DataFrame()) is None

    def test_zwraca_none_gdy_brak_kolumn(self):
        assert sily_ligowe(pd.DataFrame({"cos": [1, 2]})) is None

    def test_druzyna_ponizej_progu_meczow_wypada(self):
        """Rating z dwóch meczów to szum udający wiedzę."""
        df = _liga([("A", "B", 1, 0), ("B", "A", 2, 2)])
        wynik = sily_ligowe(df)
        assert wynik is None or "A" not in wynik[0]

    def test_srednie_ligowe_licza_sie_z_calej_ligi(self):
        df = _liga_z_dominatorem()
        _, sr_dom, sr_wyj = sily_ligowe(df)
        assert sr_dom == pytest.approx(df["gole_g"].mean())
        assert sr_wyj == pytest.approx(df["gole_a"].mean())


class TestRozdzielczosc:
    """Sedno: ratingi MUSZĄ się od siebie różnić, gdy drużyny się różnią."""

    def test_mocny_ma_wyzszy_atak_niz_slaby(self):
        tab, _, _ = sily_ligowe(_liga_z_dominatorem())
        assert tab["Mocny"]["atak_dom"] > tab["Slaby"]["atak_dom"]

    def test_slaby_ma_gorsza_obrone(self):
        """Wyższa wartość obrony = więcej traci."""
        tab, _, _ = sily_ligowe(_liga_z_dominatorem())
        assert tab["Slaby"]["obrona_dom"] > tab["Mocny"]["obrona_dom"]

    def test_ratingi_nie_sciagaja_do_jedynki(self):
        """Regresja, którą naprawiamy: dzielenie przez własną średnią kasowało sygnał."""
        tab, _, _ = sily_ligowe(_liga_z_dominatorem())
        assert tab["Mocny"]["atak_dom"] > 1.3
        assert tab["Slaby"]["atak_dom"] < 0.8

    def test_dom_i_wyjazd_licza_sie_osobno(self):
        """Drużyna grająca inaczej u siebie niż na wyjeździe ma to widoczne."""
        mecze = []
        for _ in range(5):
            mecze += [
                ("Domator", "X", 4, 0), ("Domator", "Y", 3, 0),
                ("X", "Domator", 2, 0), ("Y", "Domator", 2, 0),
                ("X", "Y", 1, 1), ("Y", "X", 1, 1),
            ]
        tab, _, _ = sily_ligowe(_liga(mecze))
        assert tab["Domator"]["atak_dom"] > tab["Domator"]["atak_wyj"]


class TestOkno:
    def test_okno_ogranicza_historie(self):
        """Stare mecze nie mogą ciągnąć ratingu w nieskończoność."""
        stare = [("A", "B", 5, 1)] * 20
        nowe = [("A", "B", 0, 1)] * 10
        df = _liga(stare + nowe)

        tab_dlugie, _, _ = sily_ligowe(df, okno=40)
        tab_krotkie, _, _ = sily_ligowe(df, okno=10)

        assert tab_krotkie["A"]["atak_dom"] < tab_dlugie["A"]["atak_dom"]

    def test_okno_bierze_NAJNOWSZE_mecze(self):
        """Kolejność ramki to chronologia — okno tnie od końca, nie od początku."""
        df = _liga([("A", "B", 5, 0)] * 8 + [("A", "B", 0, 3)] * 8)
        tab, _, _ = sily_ligowe(df, okno=8)
        assert tab["A"]["atak_dom"] < 0.5


class TestOdpornosc:
    def test_zero_goli_w_lidze_nie_dzieli_przez_zero(self):
        df = _liga([("A", "B", 0, 0)] * 10 + [("B", "A", 0, 0)] * 10)
        assert sily_ligowe(df) is None

    def test_nie_mutuje_wejscia(self):
        df = _liga_z_dominatorem()
        kopia = df.copy()
        sily_ligowe(df)
        pd.testing.assert_frame_equal(df, kopia)
