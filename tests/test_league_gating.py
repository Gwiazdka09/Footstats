"""M1 lever #2 — gating słabych lig (env LEAGUE_GATING, default OFF).

Ligi <50% offline (POL/ESP/FRA) odrzucane TYLKO gdy LEAGUE_GATING=1; domyślnie
zero zmiany (faworyzuje NED/SCO/ITA/ENG). Flip po walidacji ~88 settled.
"""
import pytest

from footstats.core.daily_filters import _pre_filtruj_ligi


def _m(liga):
    return {"gospodarz": "A", "goscie": "B", "liga": liga, "data": "2026-06-26"}


def test_default_off_slaba_liga_przechodzi(monkeypatch):
    """Bez LEAGUE_GATING — POL/ESP/FRA przechodzą (zero zmiany prod)."""
    monkeypatch.delenv("LEAGUE_GATING", raising=False)
    przeszly = {m["liga"] for m in _pre_filtruj_ligi([
        _m("Ekstraklasa"), _m("La Liga"), _m("Ligue 1"),
    ])}
    assert przeszly == {"Ekstraklasa", "La Liga", "Ligue 1"}


def test_gating_on_odrzuca_slabe_ligi(monkeypatch):
    """LEAGUE_GATING=1 — POL/ESP/FRA odrzucone."""
    monkeypatch.setenv("LEAGUE_GATING", "1")
    assert _pre_filtruj_ligi([_m("Ekstraklasa")]) == []
    assert _pre_filtruj_ligi([_m("La Liga")]) == []
    assert _pre_filtruj_ligi([_m("Ligue 1")]) == []


def test_gating_on_mocna_liga_przechodzi(monkeypatch):
    """LEAGUE_GATING=1 — mocne ligi (NED/ITA/ENG) NIE są gatowane."""
    monkeypatch.setenv("LEAGUE_GATING", "1")
    przeszly = {m["liga"] for m in _pre_filtruj_ligi([
        _m("Eredivisie"), _m("Serie A"), _m("Premier League"),
    ])}
    assert przeszly == {"Eredivisie", "Serie A", "Premier League"}


def test_gating_on_normalizacja_prefiks_akcenty(monkeypatch):
    """Gating porównuje znormalizowane (prefiks kraju, akcenty, case)."""
    monkeypatch.setenv("LEAGUE_GATING", "1")
    assert _pre_filtruj_ligi([_m("ESP-La Liga")]) == []        # prefiks
    assert _pre_filtruj_ligi([_m("Segunda División")]) == []   # akcent (ESP 2. liga)


@pytest.mark.parametrize("val", ["0", "", "false"])
def test_gating_off_warianty(monkeypatch, val):
    """LEAGUE_GATING w {0,'',false} → OFF (słaba liga przechodzi)."""
    monkeypatch.setenv("LEAGUE_GATING", val)
    assert _pre_filtruj_ligi([_m("Ekstraklasa")]) == [_m("Ekstraklasa")]
