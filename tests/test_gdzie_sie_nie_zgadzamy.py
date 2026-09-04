"""Gdzie sie nie zgadzamy — czy podzial i test McNemara sa poprawne."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from gdzie_sie_nie_zgadzamy import mcnemar  # noqa: E402


def test_mcnemar_zeruje_sie_przy_remisie():
    m = mcnemar(np.array([True] * 50 + [False] * 50),
                np.array([False] * 50 + [True] * 50))
    assert m["a"] == m["b"] == 50
    assert m["z"] == pytest.approx(0.0)


def test_mcnemar_ujemny_gdy_rynek_trafia_czesciej():
    m = mcnemar(np.array([True] * 20 + [False] * 180),
                np.array([False] * 20 + [True] * 80 + [False] * 100))
    assert m["a"] == 20 and m["b"] == 80
    assert m["z"] == pytest.approx((20 - 80) / np.sqrt(100))
    assert m["z"] < -2


def test_mcnemar_dodatni_gdy_model_trafia_czesciej():
    m = mcnemar(np.array([True] * 80), np.array([False] * 80))
    assert m["z"] > 2


def test_mcnemar_bez_trafien_nie_wywala_sie():
    """Podzbior, w ktorym ZAWSZE wygral trzeci wynik — obaj chybili.
    Bez tego guardu byloby dzielenie przez zero."""
    m = mcnemar(np.zeros(30, dtype=bool), np.zeros(30, dtype=bool))
    assert m["z"] is None


def test_mcnemar_liczy_tylko_podane_mecze():
    """Test dziala na PODZBIORZE niezgody — dlugosc wejscia ma byc n podzbioru,
    a nie calej proby. Pomylka tutaj rozcienczylaby wynik czterokrotnie."""
    model_ok = np.array([True, False, False])
    rynek_ok = np.array([False, True, False])
    m = mcnemar(model_ok, rynek_ok)
    assert m["a"] + m["b"] == 2
