"""Siła drużyny liczona też ze strzałów celnych, nie z samych goli.

PO CO: gol to zdarzenie rzadkie (~1,4 na drużynę), więc średnia z 30 meczów jest
szumna — a to jest dokładnie ten brak ROZDZIELCZOŚCI, który zmierzyliśmy:
model nie odróżnia meczów, bo szacuje siłę z małej liczby zdarzeń. Strzał celny
pada 4-5 razy częściej, więc ta sama próbka daje stabilniejszą ocenę.

Zmierzone walk-forwardem na DWÓCH niezależnych próbach (waga 0 = stan poprzedni):

    waga   Brier top-4    Brier 6 innych lig   trafnosc
    0.0    0.6062         0.6290               47,4-48,6%
    0.5    0.6020         0.6197               48,0-50,3%
    0.7    0.6032         0.6180               48,1-50,8%
    1.0    0.6081         0.6176               48,3-48,4%
    rynek  0.5919         0.5978               52,2-52,7%

Obie próby zgadzają się co do kierunku, różnią się optimum (czołowe: 0.5,
niższe: 1.0). Wybrane 0.7 jest bliskie najlepszego na obu i unika ryzyka
czystych strzałów, które na ligach czołowych wypadały gorzej.
To POWTÓRZYŁO SIĘ poza próbką strojenia — inaczej niż korekta siłą rywala,
która była lepsza tylko tam, gdzie ją strojono, i dlatego nie weszła.

Dane: strzały ma 67 753 z 139 102 meczów; 21 lig powyżej 80% pokrycia.
Brak strzałów musi cicho wracać do samych goli — połowa datasetu ich nie ma.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core.form import sily_ligowe


def _liga(n: int = 6, *, ze_strzalami: bool = True) -> pd.DataFrame:
    """Mocny strzela duzo i celnie, Slaby odwrotnie."""
    wiersze = []
    for i in range(n):
        for g, a, gg, ga, sg, sa in (
            ("Mocny", "Slaby", 3, 0, 9, 2),
            ("Mocny", "Sredni", 2, 1, 8, 4),
            ("Sredni", "Slaby", 2, 0, 6, 3),
            ("Slaby", "Mocny", 0, 2, 2, 8),
            ("Sredni", "Mocny", 1, 2, 4, 7),
            ("Slaby", "Sredni", 1, 2, 3, 6),
        ):
            w = {"gospodarz": g, "goscie": a, "gole_g": gg, "gole_a": ga,
                 "data": f"2026-0{1 + i % 9}-01"}
            if ze_strzalami:
                w["hst"], w["ast"] = sg, sa
            wiersze.append(w)
    return pd.DataFrame(wiersze)


class TestWagaStrzalow:
    def test_waga_zero_daje_wynik_z_samych_goli(self):
        """Escape-hatch musi byc matematycznie bez efektu."""
        df = _liga()
        bez, _, _ = sily_ligowe(df, waga_strzalow=0.0)
        gole_only, _, _ = sily_ligowe(df.drop(columns=["hst", "ast"]))
        assert bez["Mocny"]["atak_dom"] == pytest.approx(gole_only["Mocny"]["atak_dom"])

    def test_strzaly_zmieniaja_rating(self):
        df = _liga()
        bez, _, _ = sily_ligowe(df, waga_strzalow=0.0)
        ze, _, _ = sily_ligowe(df, waga_strzalow=0.7)
        assert ze["Mocny"]["atak_dom"] != pytest.approx(bez["Mocny"]["atak_dom"])

    def test_kolejnosc_druzyn_zostaje_zachowana(self):
        """Zmiana wsadu nie moze odwrocic tego, kto jest mocniejszy."""
        tab, _, _ = sily_ligowe(_liga(), waga_strzalow=0.7)
        assert tab["Mocny"]["atak_dom"] > tab["Slaby"]["atak_dom"]
        assert tab["Slaby"]["obrona_dom"] > tab["Mocny"]["obrona_dom"]


class TestOdpornosc:
    def test_brak_kolumn_ze_strzalami_wraca_do_goli(self):
        """Polowa datasetu nie ma strzalow — to normalny stan, nie awaria."""
        df = _liga(ze_strzalami=False)
        tab, _, _ = sily_ligowe(df, waga_strzalow=0.7)
        assert tab["Mocny"]["atak_dom"] > 1.0

    def test_puste_strzaly_wracaja_do_goli(self):
        df = _liga()
        df["hst"] = None
        df["ast"] = None
        tab, _, _ = sily_ligowe(df, waga_strzalow=0.7)
        assert tab["Mocny"]["atak_dom"] > 1.0

    def test_liga_bez_ani_jednego_strzalu_celnego_nie_dzieli_przez_zero(self):
        df = _liga()
        df["hst"] = 0
        df["ast"] = 0
        wynik = sily_ligowe(df, waga_strzalow=0.7)
        assert wynik is not None
        assert wynik[0]["Mocny"]["atak_dom"] > 0

    def test_czesciowe_pokrycie_nie_wywala(self):
        """Ligi maja 88-100% pokrycia — brakujace mecze musza po prostu wypasc."""
        df = _liga()
        df.loc[df.index[:10], "hst"] = None
        tab, _, _ = sily_ligowe(df, waga_strzalow=0.7)
        assert tab["Mocny"]["atak_dom"] > 0


def test_domyslna_waga_jest_zmierzona():
    """0.7 nie jest z sufitu — jest bliskie optimum na obu probach."""
    from footstats.config import WAGA_STRZALOW

    assert 0.0 <= WAGA_STRZALOW <= 1.0
    assert WAGA_STRZALOW == pytest.approx(0.7)
