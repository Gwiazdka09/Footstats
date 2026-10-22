"""Ligi z danymi Poissona pod nazwą sponsora / rundy przechodzą filtr lig.

Logi footstats-final 23.09–22.10: „Trendyol Super Lig”, „Liga MX Apertura”
i „Stoiximan Super League” odrzucone (≥17 meczów), choć Turcja, Meksyk i Grecja
są w zbiorze historycznym. `_norm_liga` zdejmuje tylko akcenty i prefiks kraju,
więc nazwa sponsora musi być aliasem w `config._ALIASY_ZRODLA`.
"""
import pytest

from footstats.core.daily_filters import _pre_filtruj_ligi


def _m(liga):
    return {"gospodarz": "A", "goscie": "B", "liga": liga, "data": "2026-10-22"}


@pytest.mark.parametrize("liga", [
    "Trendyol Super Lig", "Trendyol Süper Lig",
    "Liga MX Apertura", "Liga MX Clausura",
    "Stoiximan Super League",
])
def test_nazwa_sponsorska_ligi_z_danymi_przechodzi(liga):
    assert _pre_filtruj_ligi([_m(liga)]) == [_m(liga)]


def test_puchary_nadal_odrzucane():
    # Aliasy nie mogą otworzyć pucharów (23ae6181c) — Poisson nie liczy par z dwóch lig.
    assert _pre_filtruj_ligi([_m("Europa League"), _m("Conference League")]) == []
