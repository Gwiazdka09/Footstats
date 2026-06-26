"""test_confidence_komentarz.py — komentarz_analityka (string builder, był 74% pokryty).

Pokrywa gałęzie kontekstu meczu (REWANZ/FINAL/PUCHAR_1), faworyta, statusy
Importance Index, heurystykę/H2H/fortress/formę i rynki BTTS/Over/Under.
"""
from footstats.core.confidence import komentarz_analityka


def _base(**over):
    w = {
        "gospodarz": "A", "gosc": "B",
        "p_wygrana": 40, "p_remis": 25, "p_przegrana": 35,
        "btts": 50, "over25": 50, "under25": 50, "pewnosc": 60,
    }
    w.update(over)
    return w


def test_faworyt_gospodarz_i_pewnosc():
    txt = komentarz_analityka(_base(p_wygrana=70))
    assert "faworyzuje A" in txt
    assert "Pewnosc modelu: 60%" in txt


def test_faworyt_gosc():
    assert "faworyzuje B" in komentarz_analityka(_base(p_przegrana=70))


def test_mecz_wyrownany_remis():
    assert "wysoka szansa na remis" in komentarz_analityka(
        _base(p_wygrana=36, p_remis=30, p_przegrana=34))


def test_kontekst_rewanz():
    txt = komentarz_analityka(_base(
        klasyfikacja={"typ": "REWANZ", "agg_g": 2, "agg_a": 1, "opis": "x"}))
    assert "[REWANZ]" in txt and "2:1" in txt


def test_kontekst_final():
    txt = komentarz_analityka(_base(klasyfikacja={"typ": "FINAL"}))
    assert "[FINAL/TURNIEJ]" in txt


def test_kontekst_puchar_1():
    txt = komentarz_analityka(_base(klasyfikacja={"typ": "PUCHAR_1"}))
    assert "[PUCHAR 1/2]" in txt


def test_importance_statusy():
    txt = komentarz_analityka(_base(
        imp_g={"status": "FINAL_TOP"}, imp_a={"status": "VACATION"}))
    assert "TRYB FINALNY" in txt and "Efekt wakacji" in txt


def test_heur_h2h_fortress_forma():
    txt = komentarz_analityka(_base(
        heur_g={"opis": "Zmeczenie B2B"},
        h2h_g={"opis": "Patent nad B", "patent": True},
        fortress_g={"fortress": True, "opis": "Twierdza A"},
        forma_g=2.5, forma_a=1.0))
    assert "Zmeczenie B2B" in txt
    assert "Patent nad B" in txt
    assert "Twierdza A" in txt
    assert "Forma A" in txt


def test_rynki_btts_over():
    txt = komentarz_analityka(_base(btts=70, over25=75))
    assert "BTTS" in txt and "Over 2.5" in txt


def test_rynek_under_i_knockout():
    txt = komentarz_analityka(_base(
        over25=30, under25=70, knockout=True, korekta_opis="Korekta knockout"))
    assert "Under 2.5" in txt and "Korekta knockout" in txt
