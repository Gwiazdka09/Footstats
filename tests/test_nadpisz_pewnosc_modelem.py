"""Cel B: _nadpisz_pewnosc_modelem — bramki kuponu na prob MODELU, nie Groq."""
from footstats.ai.analyzer_helpers import _nadpisz_pewnosc_modelem


def test_nadpisuje_pewnosc_prob_modelu():
    # Groq zawyżył pewność (90%), model daje 55% → po nadpisaniu 55.
    wyniki = [{"gospodarz": "PSG", "goscie": "Lyon",
               "pred": {"p_wygrana": 55.0, "p_remis": 25.0, "p_przegrana": 20.0}}]
    dane = {"kupon_a": {"zdarzenia": [
        {"mecz": "PSG vs Lyon", "typ": "1", "kurs": 1.7, "pewnosc_pct": 90},
    ]}}
    _nadpisz_pewnosc_modelem(dane, wyniki)
    assert dane["kupon_a"]["zdarzenia"][0]["pewnosc_pct"] == 55


def test_fallback_groq_gdy_brak_pred():
    # Brak pred modelu → zostaje Groq pewnosc_pct.
    wyniki = [{"gospodarz": "X", "goscie": "Y", "pred": {}}]
    dane = {"top3": [{"mecz": "X vs Y", "typ": "1", "pewnosc_pct": 70}]}
    _nadpisz_pewnosc_modelem(dane, wyniki)
    assert dane["top3"][0]["pewnosc_pct"] == 70


def test_brak_dopasowania_meczu_fallback():
    # Mecz nieznaleziony w wyniki → fallback na Groq.
    wyniki = [{"gospodarz": "A", "goscie": "B", "pred": {"p_wygrana": 60.0}}]
    dane = {"kupon_a": {"zdarzenia": [
        {"mecz": "C vs D", "typ": "1", "pewnosc_pct": 80},
    ]}}
    _nadpisz_pewnosc_modelem(dane, wyniki)
    assert dane["kupon_a"]["zdarzenia"][0]["pewnosc_pct"] == 80


def test_over_uzywa_over25_modelu():
    wyniki = [{"gospodarz": "A", "goscie": "B",
               "pred": {"over25": 48.0, "p_wygrana": 50.0}}]
    dane = {"kupon_a": {"zdarzenia": [
        {"mecz": "A vs B", "typ": "Over 2.5", "pewnosc_pct": 75},
    ]}}
    _nadpisz_pewnosc_modelem(dane, wyniki)
    assert dane["kupon_a"]["zdarzenia"][0]["pewnosc_pct"] == 48
