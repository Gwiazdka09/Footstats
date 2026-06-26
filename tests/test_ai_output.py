"""test_ai_output.py — formatowanie wyświetlania analizy AI (było 6% pokryte)."""
from footstats.ai.output import wyswietl_analiza_ai


def test_wyswietl_pelny_wynik_wszystkie_galezie(capsys):
    wyswietl_analiza_ai({
        "gospodarz": "A", "goscie": "B", "typ": "1", "pewnosc": 72,
        "uzasadnienie": "Faworyt u siebie.",
        "value_bet": True, "value_bet_opis": "EV +8%",
        "alternatywny_typ": "Over 2.5", "ostrzezenia": "Rotacja składu",
        "k1": 1.8, "kX": 3.5, "k2": 4.2,
        "p_wygrana": 55.0, "p_remis": 25.0, "p_przegrana": 20.0,
    })
    out = capsys.readouterr().out
    assert "AI ANALIZA: A vs B" in out
    assert "TYP:      1" in out and "PEWNOSC:  72%" in out
    assert "VALUE BET: EV +8%" in out
    assert "Alternatywny typ: Over 2.5" in out
    assert "Ostrzezenia: Rotacja składu" in out
    assert "Kursy: 1=1.8" in out
    assert "1=55.0%" in out


def test_wyswietl_minimalny_pomija_opcjonalne(capsys):
    wyswietl_analiza_ai({"gospodarz": "A", "goscie": "B"})
    out = capsys.readouterr().out
    assert "AI ANALIZA: A vs B" in out
    assert "VALUE BET" not in out          # brak vb
    assert "Alternatywny typ" not in out   # brak alt
    assert "Kursy:" not in out             # brak k1
