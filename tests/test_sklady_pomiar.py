"""Sklady — czy pomiar bedzie liczyl to, co trzeba, ZANIM pojawia sie dane."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from sklady_pomiar import _over, brier_dwuwyjsciowy, mde  # noqa: E402


def test_over25_correct_to_WYNIK_a_nie_nasza_trafnosc():
    """Settlement liczy `over25_correct` jako ocene STALEGO typu 'Over 2.5'
    wobec wyniku, wiec 1 znaczy 'padlo Over'. Odwrotna interpretacja odwrocilaby
    znak calego pomiaru, a liczby dalej wygladalyby sensownie."""
    assert _over({"over25_correct": 1}) is True
    assert _over({"over25_correct": 0}) is False
    assert _over({}) is False


def test_brier_ta_sama_konwencja_co_rynek_golowy():
    """Suma po obu wyjsciach, czyli 2*(p-y)^2. Wersja jednostronna dalaby liczby
    o polowe mniejsze i nie dalyby sie zestawic z -0.01752."""
    assert brier_dwuwyjsciowy(np.array([0.7]), np.array([1.0]))[0] == pytest.approx(
        2 * 0.09)
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from rynek_golowy import brier_dwuwyjsciowy as ref
    p, y = np.array([0.31, 0.62]), np.array([1.0, 0.0])
    assert brier_dwuwyjsciowy(p, y).tolist() == pytest.approx(ref(p, y).tolist())


def test_minimalny_wykrywalny_efekt_maleje_z_pierwiastkiem_n():
    assert mde(500) == pytest.approx(2 * 0.186 / np.sqrt(500))
    assert mde(2000) == pytest.approx(mde(500) / 2, rel=1e-6)
    assert mde(0) == float("inf")


def test_prog_500_wykrywa_efekt_wielkosci_naszego_deficytu():
    """Sanity na deklaracji z pre-rejestracji: przy n=500 wykryjemy tylko efekt
    rzedu calego deficytu wobec ceny golowej (0.01752), nie mniejszy."""
    assert mde(500) > 0.01
    assert mde(500) < 0.02
    assert mde(5000) < 0.006
