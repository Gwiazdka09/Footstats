"""Decyzja 2026-11-07: kupon final domyslnie NIE jest zapisywany do bazy."""
import footstats.daily_agent as da


def test_zapis_kuponu_final_domyslnie_wylaczony(monkeypatch):
    monkeypatch.delenv("FINAL_ZAPIS_KUPONU", raising=False)
    assert da._zapis_kuponu_final_wlaczony() is False


def test_zapis_kuponu_final_wlaczany_flaga(monkeypatch):
    monkeypatch.setenv("FINAL_ZAPIS_KUPONU", "1")
    assert da._zapis_kuponu_final_wlaczony() is True
