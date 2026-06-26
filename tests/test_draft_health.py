"""test_draft_health.py — sygnał świeżości danych walidacyjnych cloud-draft."""
from datetime import date, datetime

import pytest

from footstats.core.draft_health import ocena_swiezosci, _to_date, PROG_STALE_DNI


def test_brak_kuponu_to_stale():
    r = ocena_swiezosci(None, dzis="2026-06-26")
    assert r["stale"] is True and r["stale_days"] is None


def test_dzisiejszy_kupon_fresh():
    r = ocena_swiezosci("2026-06-26 07:30:00", dzis="2026-06-26")
    assert r["stale_days"] == 0 and r["stale"] is False


def test_dwa_dni_jeszcze_fresh():
    r = ocena_swiezosci("2026-06-24", dzis="2026-06-26")
    assert r["stale_days"] == 2 and r["stale"] is False


def test_prog_dni_stale():
    # dokładnie prog_dni → stale (>=)
    r = ocena_swiezosci("2026-06-23", dzis="2026-06-26", prog_dni=3)
    assert r["stale_days"] == 3 and r["stale"] is True


def test_stary_kupon_stale():
    r = ocena_swiezosci("2026-06-20", dzis="2026-06-26")
    assert r["stale_days"] == 6 and r["stale"] is True


def test_parse_error_to_stale():
    assert ocena_swiezosci("nie-data", dzis="2026-06-26")["stale"] is True


@pytest.mark.parametrize("val,oczek", [
    ("2026-06-26", date(2026, 6, 26)),
    ("2026-06-26 07:30:00", date(2026, 6, 26)),
    (datetime(2026, 6, 26, 7, 30), date(2026, 6, 26)),
    (date(2026, 6, 26), date(2026, 6, 26)),
])
def test_to_date_warianty(val, oczek):
    assert _to_date(val) == oczek


def test_prog_domyslny_eksportowany():
    assert PROG_STALE_DNI == 3
