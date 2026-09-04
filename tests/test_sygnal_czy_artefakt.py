"""Sygnal czy artefakt — czy kontrole faktycznie kontroluja.

Ten skrypt ma orzec, czy jedyny dodatni wynik projektu jest prawdziwy. Jego
kontrole musza wiec byc sprawdzone tak samo mocno jak sam pomiar: kontrola,
ktora nie kontroluje, przepuscilaby artefakt z pieczatka „zweryfikowane".
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from ruch_linii import mnk  # noqa: E402
from sygnal_czy_artefakt import _clv, _kubelki  # noqa: E402


def test_kubelki_pokrywaja_caly_zakres_i_nie_sa_wspolliniowe():
    x = np.linspace(0.05, 0.95, 5000)
    K = _kubelki(x, ile=20)
    assert K.shape[0] == 5000
    # Ostatni kubelek jest pominiety, wiec wiersze z niego maja same zera —
    # inaczej suma kolumn = 1 i model ze stala bylby osobliwy.
    assert K.sum(axis=1).max() == 1.0
    assert (K.sum(axis=1) == 0).any(), "brak kategorii odniesienia"
    assert np.linalg.matrix_rank(np.column_stack([np.ones(len(K)), K])) == K.shape[1] + 1


def test_kubelki_pochlaniaja_artefakt_poziomu_TYLKO_CZESCIOWO():
    """Sedno badania A1 — i jego zmierzona GRANICA.

    Dryf zalezy KWADRATOWO od poziomu ceny, a „sygnal" jest deterministyczna
    funkcja tej samej ceny i nie niesie niczego wiecej. Kontrola LINIOWA daje
    tu ogromny falszywy wynik. Kubelkowa zbija go dziewieciokrotnie, ale NIE
    do zera: wewnatrz kubelka zaleznosc wciaz sie zmienia, a sygnal wciaz ja
    odtwarza.

    Test istnieje po to, zeby ta granica byla zapisana, a nie odkryta ponownie.
    Dlatego wlasnie A1 samo nie rozstrzyga i potrzebne jest placebo A2b.
    """
    rng = np.random.default_rng(3)
    n = 40000
    poziom = rng.uniform(0.1, 0.9, n)
    dryf = 0.4 * (poziom - 0.5) ** 2 + rng.normal(scale=0.005, size=n)
    sygnal = (poziom - 0.5) ** 2 * 0.9 + rng.normal(scale=0.001, size=n)

    beta_lin, se_lin = mnk(dryf, np.column_stack([sygnal, poziom]))
    beta_kub, se_kub = mnk(dryf, np.column_stack([sygnal, _kubelki(poziom)]))
    z_lin = abs(beta_lin[1] / se_lin[1])
    z_kub = abs(beta_kub[1] / se_kub[1])

    assert z_lin > 20, "scena nie odtwarza pulapki, ktorej test pilnuje"
    assert z_kub < z_lin / 5, "kubelki nie zbijaja artefaktu w ogole"
    assert z_kub > 3, ("kubelki zbijaja artefakt CALKOWICIE — jesli to sie"
                       " kiedys stanie, A2b przestaje byc konieczne i regule"
                       " decyzyjna badania 1 mozna uproscic")


def test_placebo_w_kubelku_ceny_ZABIJA_artefakt_ktorego_A1_nie_zabija():
    """Sedno badania A2b — placebo, ktore ma najwieksza moc obalenia.

    Ta sama scena co wyzej: sygnal jest wylacznie funkcja poziomu ceny.
    Przetasowanie sygnalu MIEDZY MECZAMI O TEJ SAMEJ CENIE nie zmienia wiec
    prawie nic — i wlasnie dlatego placebo musi tu wyjsc rownie „istotne"
    jak oryginal. To jest sygnatura artefaktu.
    """
    rng = np.random.default_rng(9)
    n = 40000
    poziom = rng.uniform(0.1, 0.9, n)
    dryf = 0.4 * (poziom - 0.5) ** 2 + rng.normal(scale=0.005, size=n)
    sygnal = (poziom - 0.5) ** 2 * 0.9 + rng.normal(scale=0.001, size=n)

    kub = np.digitize(poziom, np.quantile(poziom, np.linspace(0, 1, 101)[1:-1]))
    perm = np.arange(n)
    for g in np.unique(kub):
        i = np.flatnonzero(kub == g)
        perm[i] = rng.permutation(i)

    z_org = abs(mnk(dryf, np.column_stack([sygnal, _kubelki(poziom)]))[0][1]
                / mnk(dryf, np.column_stack([sygnal, _kubelki(poziom)]))[1][1])
    b_pl, se_pl = mnk(dryf, np.column_stack([sygnal[perm], _kubelki(poziom)]))
    z_pl = abs(b_pl[1] / se_pl[1])

    assert z_org > 3, "scena nie odtwarza artefaktu"
    assert z_pl > z_org / 3, (
        f"placebo w kubelku ceny NIE odtwarza artefaktu (z_org={z_org:.1f},"
        f" z_pl={z_pl:.1f}) — wtedy A2b nie wykrywalby go u nas")


def test_placebo_w_kubelku_ceny_NIE_odtwarza_prawdziwej_informacji():
    """Kontrola odwrotna. Gdy sygnal niesie tresc niezalezna od ceny,
    przetasowanie musi ja zniszczyc — inaczej A2b odrzucalby KAZDY wynik."""
    rng = np.random.default_rng(10)
    n = 40000
    poziom = rng.uniform(0.1, 0.9, n)
    prywatna = rng.normal(scale=0.05, size=n)
    dryf = 0.3 * (poziom - 0.5) ** 2 + 0.6 * prywatna + rng.normal(scale=0.01, size=n)

    kub = np.digitize(poziom, np.quantile(poziom, np.linspace(0, 1, 101)[1:-1]))
    perm = np.arange(n)
    for g in np.unique(kub):
        i = np.flatnonzero(kub == g)
        perm[i] = rng.permutation(i)

    b_org, se_org = mnk(dryf, np.column_stack([prywatna, _kubelki(poziom)]))
    b_pl, se_pl = mnk(dryf, np.column_stack([prywatna[perm], _kubelki(poziom)]))
    assert b_org[1] / se_org[1] > 20
    assert abs(b_pl[1] / se_pl[1]) < 3, "placebo zachowalo prawdziwa informacje"


def test_kubelki_nie_zjadaja_prawdziwego_sygnalu():
    """Kontrola odwrotna: kubelki nie moga kasowac realnej informacji,
    bo wtedy badanie 1 odrzucaloby KAZDY wynik, takze prawdziwy."""
    rng = np.random.default_rng(4)
    n = 40000
    poziom = rng.uniform(0.1, 0.9, n)
    prywatna = rng.normal(scale=0.05, size=n)          # niezalezna od poziomu
    dryf = 0.3 * (poziom - 0.5) ** 2 + 0.6 * prywatna + rng.normal(scale=0.01, size=n)
    beta, se = mnk(dryf, np.column_stack([prywatna, _kubelki(poziom)]))
    assert beta[1] / se[1] > 20
    assert beta[1] == pytest.approx(0.6, abs=0.05)


def test_clv_liczy_stosunek_kursow_wybranego_wyniku():
    otw = np.array([[2.00, 3.5, 4.0], [1.50, 4.0, 7.0]])
    zam = np.array([[1.90, 3.6, 4.2], [1.60, 3.9, 6.5]])
    r = _clv(otw, zam, np.array([0, 0]))
    # (2.00/1.90 - 1) = +5.26%,  (1.50/1.60 - 1) = -6.25%
    assert r["n"] == 2
    assert r["clv"] == pytest.approx((2.00 / 1.90 - 1 + 1.50 / 1.60 - 1) / 2)


def test_clv_pomija_kursy_niedodatnie():
    otw = np.array([[0.0, 3.5, 4.0], [2.0, 3.5, 4.0]])
    zam = np.array([[1.9, 3.6, 4.2], [1.9, 3.6, 4.2]])
    r = _clv(otw, zam, np.array([0, 0]))
    assert r["n"] == 1
    assert r["clv"] == pytest.approx(2.0 / 1.9 - 1)


def test_clv_zeruje_sie_gdy_cena_sie_nie_rusza():
    o = np.array([[2.0, 3.5, 4.0]] * 500)
    r = _clv(o, o.copy(), np.zeros(500, dtype=int))
    assert r["clv"] == pytest.approx(0.0)
