"""
test_daily_phases.py — testy czystych helperów wydzielonych z daily_agent.py
do core/daily_phases.py (dług techniczny #3, behavior-preserving refactor).
"""
from footstats.core.daily_phases import _dodaj_kelly


def _no_calibration(monkeypatch):
    """Mock kalibracji — neutralny multiplier, brak zapytań do DB (zero touch prod)."""
    import footstats.core.calibration as cal
    monkeypatch.setattr(cal, "get_stake_multiplier", lambda *a, **k: 1.0)
    monkeypatch.setattr(cal, "calibration_summary", lambda *a, **k: {"n": 0})


def test_dodaj_kelly_dodaje_stawke_do_kuponu(monkeypatch):
    _no_calibration(monkeypatch)
    dane = {"kupon_a": {"zdarzenia": [{"pewnosc_pct": 65, "kurs": 2.10}]}}
    _dodaj_kelly(dane, bankroll=200.0)
    z = dane["kupon_a"]["zdarzenia"][0]
    assert "kelly_stake" in z
    assert z["kelly_stake"] >= 0.0


def test_dodaj_kelly_dodaje_stawke_do_top3(monkeypatch):
    _no_calibration(monkeypatch)
    dane = {"top3": [{"pewnosc_pct": 70, "kurs": 1.85}]}
    _dodaj_kelly(dane, bankroll=200.0)
    assert "kelly_stake" in dane["top3"][0]


def test_dodaj_kelly_brak_edge_zwraca_zero(monkeypatch):
    _no_calibration(monkeypatch)
    # Niska pewność vs wysoki kurs wymagany — brak edge
    dane = {"kupon_a": {"zdarzenia": [{"pewnosc_pct": 20, "kurs": 1.3}]}}
    _dodaj_kelly(dane, bankroll=200.0)
    assert dane["kupon_a"]["zdarzenia"][0]["kelly_stake"] == 0.0


def test_dodaj_kelly_nieprawidlowy_bankroll_uzywa_fallback(monkeypatch):
    """Bankroll None/ujemny (np. z DB) nie crashuje — fallback do AGENT_BANKROLL."""
    _no_calibration(monkeypatch)
    dane = {"kupon_a": {"zdarzenia": [{"pewnosc_pct": 65, "kurs": 2.0}]}}
    _dodaj_kelly(dane, bankroll=None)
    assert "kelly_stake" in dane["kupon_a"]["zdarzenia"][0]


def test_dodaj_kelly_brak_kuponow_nie_crashuje(monkeypatch):
    _no_calibration(monkeypatch)
    dane = {}
    _dodaj_kelly(dane, bankroll=200.0)  # nie powinno rzucić
    assert dane == {}
