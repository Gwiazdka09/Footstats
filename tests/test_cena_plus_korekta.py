"""Cena plus korekta — czy zagniezdzone porownanie cokolwiek wykrywa.

Wynik zerowy z zepsutego dopasowania wyglada identycznie jak wynik zerowy
z kompletnej ceny. Te testy odrozniaja jedno od drugiego na danych, w ktorych
odpowiedz jest znana z konstrukcji.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from cena_plus_korekta import log_ilorazy, porownaj  # noqa: E402

BAZA = np.array([0.45, 0.27, 0.28])


def test_log_ilorazy_odwracaja_sie_do_softmaxu():
    p = np.array([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
    L = log_ilorazy(p)
    logity = np.column_stack([L[:, 0], np.zeros(len(L)), L[:, 1]])
    e = np.exp(logity - logity.max(axis=1, keepdims=True))
    assert np.allclose(e / e.sum(axis=1, keepdims=True), p, atol=1e-9)


def _scena(waga_dodatku: float, ziarno: int, n: int = 20000):
    """Prawda = mieszanka bazy i dodatku. `waga_dodatku`=0 -> dodatek zbedny."""
    rng = np.random.default_rng(ziarno)
    szum_b = rng.normal(scale=0.6, size=(n, 2))
    szum_d = rng.normal(scale=0.6, size=(n, 2))
    l_baza = np.log(BAZA[[0, 2]] / BAZA[1])[None, :] + szum_b
    l_dod = np.log(BAZA[[0, 2]] / BAZA[1])[None, :] + szum_d
    l_praw = (1 - waga_dodatku) * l_baza + waga_dodatku * l_dod

    logity = np.column_stack([l_praw[:, 0], np.zeros(n), l_praw[:, 1]])
    e = np.exp(logity - logity.max(axis=1, keepdims=True))
    p = e / e.sum(axis=1, keepdims=True)
    y = np.array([rng.choice(3, p=w) for w in p])
    tren = np.arange(n) < n // 2
    return l_baza, l_dod, y, tren


def test_wykrywa_dodatek_ktory_naprawde_niesie_informacje():
    l_baza, l_dod, y, tren = _scena(waga_dodatku=0.5, ziarno=3)
    w = porownaj("test", l_baza, l_dod, y, tren)
    assert w["logloss"]["z"] > 5, f"nie wykryl realnego dodatku: {w['logloss']}"
    assert w["logloss"]["roznica"] > 0
    assert w["brier"]["z"] > 0, "log-loss i Brier wskazuja przeciwne kierunki"


def test_NIE_wykrywa_dodatku_bez_informacji():
    l_baza, l_dod, y, tren = _scena(waga_dodatku=0.0, ziarno=3)
    w = porownaj("test", l_baza, l_dod, y, tren)
    assert abs(w["logloss"]["z"]) < 2.5, f"halas udaje sygnal: {w['logloss']}"


def test_dodatek_identyczny_z_baza_nie_poprawia_niczego():
    """Wspolliniowosc doskonala. Dopasowanie ma tego nie przeliczyc na zysk —
    inaczej KAZDE porownanie wychodziloby dodatnie."""
    l_baza, _, y, tren = _scena(waga_dodatku=0.3, ziarno=4)
    w = porownaj("test", l_baza, l_baza.copy(), y, tren)
    assert abs(w["logloss"]["z"]) < 2.5, (
        f"kopia bazy 'poprawia' prognoze: {w['logloss']}")


def test_wspolczynniki_widza_TYLKO_trening():
    """Gdyby fit widzial holdout, dodatek bez informacji wychodzilby dodatni.

    Kontrola przez konstrukcje: `y` na holdoucie zamienione na czysty szum.
    Model uczony na treningu nie moze na tym zyskac.
    """
    l_baza, l_dod, y, tren = _scena(waga_dodatku=0.5, ziarno=5)
    rng = np.random.default_rng(6)
    y = y.copy()
    y[~tren] = rng.integers(0, 3, int((~tren).sum()))
    w = porownaj("test", l_baza, l_dod, y, tren)
    assert w["logloss"]["z"] < 2.5, (
        "dodatek 'pomaga' na holdoucie o losowych wynikach — fit widzi holdout")


def test_liczba_wierszy_holdoutu_zgadza_sie_z_podzialem():
    l_baza, l_dod, y, tren = _scena(waga_dodatku=0.2, ziarno=7)
    w = porownaj("test", l_baza, l_dod, y, tren)
    assert w["n"] == int((~tren).sum())
    assert w["logloss"]["n"] == w["n"]
