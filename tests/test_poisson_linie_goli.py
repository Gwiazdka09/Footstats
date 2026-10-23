"""Linie goli z tej samej macierzy co predykcja (krok 1 odmrożenia, 23.10).

`model_log` trzyma lambdy, więc Over 0.5/1.5/3.5/4.5 można policzyć wstecz —
ale tylko jeśli macierz jest DOKŁADNIE ta, z której predykcja liczy Over 2.5.
"""
import pytest

from footstats.config import DC_RHO_CLASSIC, MAX_GOLE
from footstats.core.poisson import _macierz, _macierz_wynikow, prob_linii_goli

_LAMBDY = [(1.5, 1.1), (2.4, 0.7), (0.6, 0.5)]


@pytest.mark.parametrize("lg, la", _LAMBDY)
def test_over25_zgodne_z_macierza_predykcji(lg, la):
    over25_raw = _macierz(round(lg, 4), round(la, 4), MAX_GOLE + 1, DC_RHO_CLASSIC)[4]
    assert prob_linii_goli(lg, la)[2.5] == pytest.approx(over25_raw, abs=1e-12)


@pytest.mark.parametrize("lg, la", _LAMBDY)
def test_linie_maleja(lg, la):
    p = prob_linii_goli(lg, la)
    assert 1.0 > p[0.5] > p[1.5] > p[2.5] > p[3.5] > p[4.5] > 0.0


def test_over05_to_jeden_minus_wynik_0_0():
    M, _, _ = _macierz_wynikow(1.5, 1.1, MAX_GOLE + 1, DC_RHO_CLASSIC)
    assert prob_linii_goli(1.5, 1.1)[0.5] == pytest.approx(1.0 - M[0, 0], abs=1e-12)
