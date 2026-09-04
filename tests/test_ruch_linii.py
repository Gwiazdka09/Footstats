"""Ruch linii — czy regresja mierzy to, co deklaruje.

Test A jest jedynym pomiarem w tym projekcie, ktory moze dac wynik DODATNI,
wiec jego kontrola musi byc mocniejsza niz zwykle: wynik zerowy z zepsutej
regresji wyglada identycznie jak wynik zerowy z braku informacji, a wynik
dodatni z zepsutej regresji bylby najgorszy z mozliwych.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ruch_linii import devig, mnk  # noqa: E402


def test_devig_zdejmuje_marze_i_sumuje_sie_do_jedynki():
    o = np.array([[2.0, 3.5, 4.0], [1.5, 4.0, 7.0]])
    p = devig(o)
    assert np.allclose(p.sum(axis=1), 1.0)
    assert p[0, 0] > p[0, 1] > p[0, 2]


def test_devig_odrzuca_kurs_niedodatni():
    p = devig(np.array([[0.0, 3.5, 4.0], [2.0, 3.5, 4.0]]))
    assert np.isnan(p[0]).all()
    assert np.isfinite(p[1]).all()


def test_mnk_odtwarza_znane_wspolczynniki():
    rng = np.random.default_rng(1)
    x1, x2 = rng.normal(size=5000), rng.normal(size=5000)
    y = 0.3 + 1.5 * x1 - 0.7 * x2 + rng.normal(scale=0.1, size=5000)
    beta, se = mnk(y, np.column_stack([x1, x2]))
    assert beta[0] == pytest.approx(0.3, abs=0.01)
    assert beta[1] == pytest.approx(1.5, abs=0.01)
    assert beta[2] == pytest.approx(-0.7, abs=0.01)
    assert (se > 0).all()


def test_mnk_daje_zerowy_wspolczynnik_dla_zmiennej_bez_zwiazku():
    rng = np.random.default_rng(2)
    x1, szum = rng.normal(size=8000), rng.normal(size=8000)
    y = 2.0 * x1 + rng.normal(scale=0.5, size=8000)
    beta, se = mnk(y, np.column_stack([szum, x1]))
    assert abs(beta[1] / se[1]) < 2.5, "regresja widzi sygnal w czystym szumie"


def _scena(sila_sygnalu: float, ziarno: int, n: int = 20000):
    """Rynek, ktory OTWIERA sie z bledem i ZAMYKA blizej prawdy.

    Model widzi prawde z waga `sila_sygnalu`. Przy 1.0 wie dokladnie to, czego
    rynek dowie sie do zamkniecia — wiec `b` musi wyjsc mocno dodatnie.
    Przy 0.0 model to czysty szum wzgledem prawdy i `b` musi zniknac.
    """
    rng = np.random.default_rng(ziarno)
    prawda = rng.uniform(0.2, 0.7, n)
    otw = prawda + rng.normal(scale=0.05, size=n)       # otwarcie z bledem
    zam = otw + 0.6 * (prawda - otw)                    # zamkniecie sie zbliza
    model = (otw + sila_sygnalu * (prawda - otw)
             + rng.normal(scale=0.05, size=n))
    return otw, zam, model


def _wspolczynnik(otw, zam, model):
    dryf = zam - otw
    beta, se = mnk(dryf, np.column_stack([model - otw, otw]))
    return beta[1], beta[1] / se[1]


def test_regresja_WYKRYWA_model_ktory_wyprzedza_rynek():
    b, z = _wspolczynnik(*_scena(sila_sygnalu=1.0, ziarno=7))
    assert b > 0 and z > 10, f"nie wykryla realnego wyprzedzania: b={b}, z={z}"


def test_regresja_NIE_WYKRYWA_sygnalu_w_modelu_bez_informacji():
    b, z = _wspolczynnik(*_scena(sila_sygnalu=0.0, ziarno=7))
    assert abs(z) < 3, f"halas udaje wyprzedzanie: b={b}, z={z}"


def test_kontrola_poziomu_ceny_jest_konieczna():
    """Bez `p_otw` w regresji wspolczynnik lapie wspolna zaleznosc od poziomu
    ceny i wychodzi dodatni mimo ZERA informacji po naszej stronie.

    Ten test istnieje, zeby kontrola nie zostala kiedys usunieta jako zbedna.
    """
    rng = np.random.default_rng(5)
    n = 20000
    poziom = rng.uniform(0.2, 0.7, n)
    # Dryf zalezy WYLACZNIE od poziomu ceny; model tez, ale prawdy nie zna.
    otw = poziom
    zam = otw + 0.10 * (poziom - 0.45)
    model = otw + 0.50 * (poziom - 0.45) + rng.normal(scale=0.02, size=n)

    dryf = zam - otw
    sygnal = model - otw
    bez_kontroli, se1 = mnk(dryf, sygnal.reshape(-1, 1))
    z_bez = bez_kontroli[1] / se1[1]
    z_kontrola = _wspolczynnik(otw, zam, model)[1]

    assert z_bez > 10, "scena nie odtwarza pulapki, ktorej test pilnuje"
    assert abs(z_kontrola) < abs(z_bez) / 5, (
        "kontrola poziomu ceny nie usuwa pozornego sygnalu")
