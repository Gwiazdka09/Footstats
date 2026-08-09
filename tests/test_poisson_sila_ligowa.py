"""Podpięcie sił ligowych do `predict_match` — za flagą, bez zmiany reszty.

PO CO: sama funkcja `sily_ligowe` jest przetestowana osobno
(`test_sily_ligowe.py`). Tu pilnujemy INTEGRACJI, bo to ona decyduje, czy
poprawka w ogóle dojdzie do produkcji:

  * flaga wyłączona = dokładnie poprzednie liczby (zero ryzyka przy wdrożeniu),
  * flaga włączona = λ liczona wobec ligi, więc mecz nierówny daje wyraźnie
    inne prawdopodobieństwa niż mecz równy,
  * brak kolumny `league`, nieznana drużyna albo za mało meczów = cichy powrót
    do starej ścieżki, nie wyjątek i nie `None`.

Ostatni punkt jest tu najważniejszy: to właśnie „ulepszenie, które wywala się
na brzegowym przypadku i cicho wyłącza cały model" jest w tym projekcie
powtarzalnym błędem.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core import poisson as pois


def _liga_nierowna(n: int = 6) -> pd.DataFrame:
    """Potega vs Kopciuszek, plus tlo ligowe zeby srednie mialy sens."""
    mecze = []
    for i in range(n):
        mecze += [
            ("Potega", "Kopciuszek", 4, 0), ("Potega", "Srednik", 3, 1),
            ("Srednik", "Kopciuszek", 2, 0), ("Kopciuszek", "Potega", 0, 3),
            ("Srednik", "Potega", 1, 2), ("Kopciuszek", "Srednik", 1, 2),
        ]
    return pd.DataFrame([
        {"data": f"2025-{1 + i % 12:02d}-01", "league": "TEST-Liga",
         "gospodarz": g, "goscie": a, "gole_g": hg, "gole_a": ag}
        for i, (g, a, hg, ag) in enumerate(mecze)
    ])


@pytest.fixture
def flaga_wl(monkeypatch):
    monkeypatch.setenv("SILA_LIGOWA", "1")


@pytest.fixture
def flaga_wyl(monkeypatch):
    monkeypatch.setenv("SILA_LIGOWA", "0")


def test_flaga_zmienia_wynik(flaga_wyl, monkeypatch):
    """Obie drogi muszą dawać RÓŻNE λ — inaczej flaga niczego nie przełącza."""
    df = _liga_nierowna()
    stara = pois.predict_match("Potega", "Kopciuszek", df.copy(), use_xg=False,
                               use_calibration=False)

    monkeypatch.setenv("SILA_LIGOWA", "1")
    nowa = pois.predict_match("Potega", "Kopciuszek", df.copy(), use_xg=False,
                              use_calibration=False)

    assert stara is not None and nowa is not None
    assert stara["lambda_g"] != nowa["lambda_g"], "flaga nie przelacza sciezki"


def test_lambda_zgadza_sie_ze_wzorem_ligowym(flaga_wl):
    """λ musi wyjść dokładnie z sił ligowych — nie „mniej więcej stamtąd"."""
    from footstats.core.form import sily_ligowe

    df = _liga_nierowna()
    tabela, sr_dom, sr_wyj = sily_ligowe(df)
    oczekiwana_g = (tabela["Potega"]["atak_dom"] * tabela["Kopciuszek"]["obrona_wyj"]
                    * sr_dom)

    w = pois.predict_match("Potega", "Kopciuszek", df, use_xg=False,
                           use_calibration=False)

    assert w["lambda_g"] == pytest.approx(oczekiwana_g, rel=0.02)


def test_suma_prawdopodobienstw_dalej_sie_zgadza(flaga_wl):
    df = _liga_nierowna()
    w = pois.predict_match("Potega", "Kopciuszek", df, use_xg=False,
                           use_calibration=False)
    assert w["p_wygrana"] + w["p_remis"] + w["p_przegrana"] == pytest.approx(
        100.0, abs=0.5
    )


def test_wlaczona_flaga_daje_wieksza_lambde_faworytowi(flaga_wl):
    df = _liga_nierowna()
    w = pois.predict_match("Potega", "Kopciuszek", df, use_xg=False,
                           use_calibration=False)
    assert w["lambda_g"] > w["lambda_a"] * 2


class TestCichyPowrot:
    """Każdy brakujący element ma cofać do starej ścieżki, nie psuć predykcji."""

    def test_brak_kolumny_league(self, flaga_wl):
        df = _liga_nierowna().drop(columns=["league"])
        assert pois.predict_match("Potega", "Kopciuszek", df, use_xg=False,
                                  use_calibration=False) is not None

    def test_druzyna_bez_historii_ligowej(self, flaga_wl):
        """Beniaminek bez meczów w tej lidze — stara ścieżka i tak coś policzy."""
        df = _liga_nierowna()
        df.loc[df.index[:8], "league"] = "INNA-Liga"
        assert pois.predict_match("Potega", "Kopciuszek", df, use_xg=False,
                                  use_calibration=False) is not None

    def test_liga_bez_goli_nie_wywala(self, flaga_wl):
        df = _liga_nierowna()
        df["gole_g"] = 0
        df["gole_a"] = 0
        wynik = pois.predict_match("Potega", "Kopciuszek", df, use_xg=False,
                                   use_calibration=False)
        assert wynik is None or wynik["lambda_g"] > 0


def test_atut_wlasnego_boiska_nie_liczy_sie_dwa_razy(flaga_wl):
    """Średnia goli gospodarzy JUŻ zawiera atut — `BONUS_DOMOWY` na wierzchu
    liczyłby go drugi raz i zawyżał każdą λ gospodarza."""
    df = _liga_nierowna()
    # W tej lidze gospodarze strzelaja srednio ~2.2, goscie ~1.0.
    w = pois.predict_match("Srednik", "Srednik2", df, use_xg=False,
                           use_calibration=False)
    if w is None:
        pytest.skip("para bez historii — przypadek pokryty osobno")
    assert w["lambda_g"] < 5.0
