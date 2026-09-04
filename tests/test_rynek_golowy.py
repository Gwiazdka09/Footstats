"""Rynek golowy — czy pomiar liczy to, co deklaruje.

Najgroźniejszy błąd w tym skrypcie nie jest błędem arytmetyki, tylko KONWENCJI:
Brier dwóch wyjść liczony jednostronnie `(p-y)^2` jest o połowę mniejszy niż
suma po obu wyjściach, a deficyt znormalizowany wyszedłby wtedy dwa razy
lepszy bez żadnej zmiany w danych. Dlatego konwencja ma tu własne testy.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from rynek_golowy import (  # noqa: E402
    brier_dwuwyjsciowy, devig_dwustronny, ev_najlepsza_cena,
    niepewnosc_dwuwyjsciowa, niepewnosc_wieloklasowa, zmierz_lige,
)


def test_devig_zdejmuje_marze():
    """Para 1.90/1.90 to 105.3% ksiazki; po zdjeciu marzy ma byc rowno 0.5."""
    p = devig_dwustronny(np.array([1.90]), np.array([1.90]))
    assert p[0] == pytest.approx(0.5)


def test_devig_faworyt_ma_wyzsze_prawdopodobienstwo():
    p = devig_dwustronny(np.array([1.50]), np.array([2.50]))
    assert p[0] == pytest.approx((1 / 1.5) / (1 / 1.5 + 1 / 2.5))
    assert p[0] > 0.5


def test_brier_dwuwyjsciowy_to_SUMA_po_obu_wyjsciach():
    """2*(p-y)^2, nie (p-y)^2. Ta stala decyduje o deficycie znormalizowanym."""
    p, y = np.array([0.7]), np.array([1.0])
    assert brier_dwuwyjsciowy(p, y)[0] == pytest.approx(2 * (0.7 - 1.0) ** 2)


def test_brier_dwuwyjsciowy_zeruje_sie_na_prognozie_doskonalej():
    b = brier_dwuwyjsciowy(np.array([1.0, 0.0]), np.array([1.0, 0.0]))
    assert b.tolist() == pytest.approx([0.0, 0.0])


def test_niepewnosc_zgadza_sie_z_czestoscia_bazowa():
    y = np.array([1.0] * 60 + [0.0] * 40)
    assert niepewnosc_dwuwyjsciowa(y) == pytest.approx(2 * 0.6 * 0.4)
    ym = np.array([0] * 45 + [1] * 25 + [2] * 30)
    assert niepewnosc_wieloklasowa(ym) == pytest.approx(
        0.45 * 0.55 + 0.25 * 0.75 + 0.30 * 0.70)


def _ramka(n: int, p_model_over: np.ndarray, p_prawdziwe: np.ndarray,
           ziarno: int = 3) -> pd.DataFrame:
    """Mecze, w ktorych cena zna prawdziwe p, a model dostaje `p_model_over`.

    Kurs rynku budowany Z prawdziwego prawdopodobienstwa i marzy 4%, wiec
    po zdewigowaniu cena wraca DOKLADNIE do prawdy — dzieki temu wiadomo
    z konstrukcji, kto powinien wygrac.
    """
    rng = np.random.default_rng(ziarno)
    y = (rng.random(n) < p_prawdziwe).astype(float)
    marza = 1.04
    return pd.DataFrame({
        "league": "L1",
        "match_date": "2024-01-01",
        "actual_res": rng.choice(["H", "D", "A"], size=n),
        "pw": 40.0, "pr": 27.0, "pp": 33.0,
        "odds_h": 2.4, "odds_d": 3.4, "odds_a": 3.1,
        "p_over25": p_model_over * 100,
        "actual_over25": y,
        "odds_over25_pinn": 1.0 / (p_prawdziwe * marza),
        "odds_under25_pinn": 1.0 / ((1 - p_prawdziwe) * marza),
        "odds_over25_max": 1.0 / (p_prawdziwe * marza),
        "odds_under25_max": 1.0 / ((1 - p_prawdziwe) * marza),
    })


def test_model_rowny_cenie_daje_zerowa_roznice():
    """Kontrola negatywna: identyczne prognozy musza dac T_gole == 0 co do bitu."""
    p = np.full(3000, 0.55)
    w = zmierz_lige(_ramka(3000, p, p))
    assert w is not None
    assert w["T_gole"]["roznica"] == pytest.approx(0.0, abs=1e-12)
    assert w["deficyt_gole"] == pytest.approx(0.0, abs=1e-12)


def test_model_gorszy_od_ceny_wychodzi_UJEMNY():
    """Kontrola pozytywna. Bez niej wynik zerowy z zepsutego kodu wyglada
    identycznie jak wynik zerowy z rownej sily."""
    rng = np.random.default_rng(11)
    p_praw = rng.uniform(0.35, 0.75, 4000)
    p_mod = np.full(4000, 0.5)          # model ignoruje wszystko
    w = zmierz_lige(_ramka(4000, p_mod, p_praw))
    assert w is not None
    assert w["T_gole"]["roznica"] < 0
    assert w["T_gole"]["z"] < -2
    assert w["deficyt_gole"] < 0


def test_model_lepszy_od_ceny_wychodzi_DODATNI():
    rng = np.random.default_rng(11)
    p_praw = rng.uniform(0.35, 0.75, 4000)
    ramka = _ramka(4000, p_praw, p_praw)
    # Cena zostaje przy 0.5, model zna prawde — odwrotnosc poprzedniego testu.
    ramka["odds_over25_pinn"] = 2.0
    ramka["odds_under25_pinn"] = 2.0
    w = zmierz_lige(ramka)
    assert w is not None
    assert w["T_gole"]["z"] > 2


def test_liga_ponizej_progu_jest_pomijana():
    p = np.full(50, 0.55)
    assert zmierz_lige(_ramka(50, p, p)) is None


def test_1x2_liczone_na_TYCH_SAMYCH_meczach():
    """n rynku golowego i n 1X2 musza byc rowne — inaczej roznica moglaby
    pochodzic z proby, a nie z rynku."""
    p = np.full(3000, 0.55)
    w = zmierz_lige(_ramka(3000, p, p))
    assert w is not None
    assert w["d_n"] == w["m_n"] == w["n"]


def test_ev_placi_podatek_od_stawki():
    """Zakład o EV dokładnie zerowym musi dać ROI brutto ~0 i po podatku ~-12%."""
    rng = np.random.default_rng(5)
    p_praw = rng.uniform(0.4, 0.6, 6000)
    ramka = _ramka(6000, p_praw, p_praw)
    # Kurs UCZCIWY (bez marzy) => EV dokladnie zero przy prawdziwym p.
    ramka["odds_over25_max"] = 1.0 / p_praw + 1e-9
    ramka["odds_under25_max"] = 1.0 / (1 - p_praw) + 1e-9
    ev = ev_najlepsza_cena(ramka)
    assert ev is not None
    assert ev["roi"] == pytest.approx(0.0, abs=3.0)
    assert ev["roi_po"] == pytest.approx(ev["roi"] - 12.0, abs=1e-6)


def test_kurs_niedodatni_wypada_z_proby():
    """W zrzucie SA kursy 0.0 — pierwszy przebieg wywalil sie na dzieleniu.

    Kurs <= 1.0 nie jest cena, tylko dziura w danych. Zostawiony daje
    nieskonczonosc w odwrotnosci i zatruwa cala kolumne prawdopodobienstw,
    a w EV wchodzi jako zaklad o dowolnie wysokiej wartosci oczekiwanej.
    """
    p = np.full(1200, 0.55)
    ramka = _ramka(1200, p, p)
    ramka.loc[:99, "odds_over25_pinn"] = 0.0
    ramka.loc[100:199, "odds_h"] = 1.0

    w = zmierz_lige(ramka)
    assert w is not None
    assert w["n"] == 1000, "wiersze z kursem <= 1.0 nie zostaly odsiane"
    assert np.isfinite(w["T_gole"]["roznica"])
    assert np.isfinite(w["deficyt_gole"])


def test_kurs_niedodatni_nie_wchodzi_do_EV():
    """Kurs 0.5 przy p=0.55 ma EV UJEMNE, wiec sam prog EV>0 by go odsial
    i test niczego by nie dowiodl. Dlatego zle kursy dostaja tu wartosc,
    ktora BY weszla do stawki, gdyby guard ich nie zlapal."""
    p = np.full(1200, 0.55)
    ramka = _ramka(1200, p, p)
    ramka["odds_over25_max"] = 3.0          # EV = 0.55*3-1 = +0.65 -> obstawiamy
    ramka.loc[:299, "odds_over25_max"] = 0.0    # dziura: 1/0 = nieskonczonosc
    ramka.loc[300:399, "odds_under25_max"] = 1.0

    ev = ev_najlepsza_cena(ramka)
    assert ev is not None
    assert ev["n"] == 800, "wiersze z kursem <= 1.0 weszly do stawki"
    assert np.isfinite(ev["roi"]) and np.isfinite(ev["roi_po"])


def test_bez_kursu_niedodatniego_guard_nic_nie_usuwa():
    """Kontrola: guard nie moze odsiewac zdrowych wierszy."""
    p = np.full(1200, 0.55)
    ramka = _ramka(1200, p, p)
    ramka["odds_over25_max"] = 3.0
    ev = ev_najlepsza_cena(ramka)
    assert ev is not None
    assert ev["n"] == 1200
