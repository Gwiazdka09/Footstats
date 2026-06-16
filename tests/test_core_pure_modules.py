"""
test_core_pure_modules.py — testy czystych modułów core bez DB/network (TD-31).
Pokrywa: classifier (knockout + korekta rewanżu), confidence (komentarz),
h2h (pewność łączna), fortress (twierdza domowa).
"""
import pandas as pd

from footstats.core.classifier import (
    _czy_knockout, _korekta_rewanz_v26, _korekta_dwumecz,
)
from footstats.core.confidence import komentarz_analityka
from footstats.core.h2h import AnalizaH2H
from footstats.core.fortress import HomeFortress


# ── classifier._czy_knockout ──────────────────────────────────────────────

def test_knockout_rozpoznaje_faze_pucharowa():
    assert _czy_knockout("FINAL") is True
    assert _czy_knockout("semi_finals") is True       # case-insensitive
    assert _czy_knockout("ROUND_OF_16") is True
    assert _czy_knockout("PLAYOFFS") is True


def test_knockout_odrzuca_liga():
    assert _czy_knockout("REGULAR_SEASON") is False
    assert _czy_knockout("") is False
    assert _czy_knockout("GROUP_STAGE") is False


# ── classifier._korekta_rewanz_v26 (4 gałęzie) ────────────────────────────

def test_rewanz_gospodarz_prowadzi_komfortowo():
    # roznica >= +2 → gospodarz gra na czas (atak w dół), goscie va-bank
    lg, la, opis = _korekta_rewanz_v26(1.5, 1.0, agg_g=3, agg_a=1)
    assert lg < 1.5, "atak gospodarza obniżony (parking bus)"
    assert la > 1.0, "atak gości podniesiony (va-bank)"
    assert "PROWADZI" in opis


def test_rewanz_gospodarz_przegrywa():
    # roznica <= -2 → gospodarz va-bank
    lg, la, opis = _korekta_rewanz_v26(1.2, 1.4, agg_g=0, agg_a=2)
    assert lg > 1.2, "atak gospodarza podniesiony (va-bank)"
    assert "PRZEGRYWA" in opis


def test_rewanz_remis_oba_atakuja():
    # roznica == 0 i agg równe → +10% obu
    lg, la, opis = _korekta_rewanz_v26(1.0, 1.0, agg_g=1, agg_a=1)
    assert lg == round(1.0 * 1.10, 3)
    assert la == round(1.0 * 1.10, 3)
    assert "Remis" in opis


def test_rewanz_minimalna_roznica():
    # roznica == 1 → lekkie wzmocnienie obu (+5%)
    lg, la, opis = _korekta_rewanz_v26(2.0, 2.0, agg_g=2, agg_a=1)
    assert lg == round(2.0 * 1.05, 3)
    assert "Minimalna" in opis


def test_korekta_dwumecz_brak_wyniku():
    lg, la, opis = _korekta_dwumecz(1.5, 1.2, None, None, jest_gospodarzem_1=True)
    assert (lg, la) == (1.5, 1.2)
    assert "Brak wyniku" in opis


def test_korekta_dwumecz_duza_przewaga():
    # gospodarz prowadzi 3:0 z 1. meczu (jako gospodarz wtedy) → parking bus
    lg, la, opis = _korekta_dwumecz(1.5, 1.2, 3, 0, jest_gospodarzem_1=True)
    assert lg < 1.5
    assert la > 1.2


# ── confidence.komentarz_analityka ────────────────────────────────────────

def _w_min(**over) -> dict:
    base = {
        "gospodarz": "Arsenal", "gosc": "Chelsea",
        "p_wygrana": 70, "p_remis": 18, "p_przegrana": 12,
        "btts": 50, "over25": 55, "under25": 45,
    }
    base.update(over)
    return base


def test_komentarz_faworyt_gospodarz():
    txt = komentarz_analityka(_w_min(p_wygrana=72))
    assert "Arsenal" in txt
    assert "faworyzuje" in txt.lower()


def test_komentarz_wyrownany_remis():
    txt = komentarz_analityka(_w_min(p_wygrana=33, p_remis=34, p_przegrana=33))
    assert "remis" in txt.lower()


def test_komentarz_zawiera_pewnosc():
    txt = komentarz_analityka(_w_min(pewnosc=64))
    assert "64%" in txt


# ── h2h.oblicz_pewnosc_laczna (staticmethod, pure) ────────────────────────

def test_pewnosc_laczna_rosnie_z_h2h():
    p0 = AnalizaH2H.oblicz_pewnosc_laczna(0, 0)
    p3 = AnalizaH2H.oblicz_pewnosc_laczna(3, 10)
    assert p3 > p0
    assert 20 <= p0 <= 100
    assert 20 <= p3 <= 100


def test_pewnosc_laczna_clamp_dolny():
    assert AnalizaH2H.oblicz_pewnosc_laczna(0, 0) >= 20


# ── fortress.HomeFortress.analiza ─────────────────────────────────────────

def _df_dom(team: str, wyniki: list[tuple[int, int]]) -> pd.DataFrame:
    """Buduje DataFrame meczów domowych: lista (gole_g, gole_a) od najstarszego."""
    rows = []
    for i, (gg, ga) in enumerate(wyniki):
        rows.append({"gospodarz": team, "gole_g": gg, "gole_a": ga, "data": f"2026-01-{i+1:02d}"})
    return pd.DataFrame(rows)


def test_fortress_wykrywa_twierdze():
    # 5 meczów bez porażki u siebie (FORTRESS_MECZE=5) → fortress=True
    df = _df_dom("Bayern", [(2, 0), (1, 1), (3, 1), (2, 2), (4, 0)])
    out = HomeFortress(df).analiza("Bayern")
    assert out["fortress"] is True
    assert out["seria"] >= 5
    assert out["bonus_obrona"] > 1.0


def test_fortress_przerwana_seria():
    # ostatni mecz przegrany → seria=0, brak twierdzy
    df = _df_dom("Bayern", [(2, 0), (1, 1), (3, 1), (2, 2), (0, 3)])
    out = HomeFortress(df).analiza("Bayern")
    assert out["fortress"] is False
    assert out["seria"] == 0


def test_fortress_pusta_baza():
    out = HomeFortress(pd.DataFrame()).analiza("Bayern")
    assert out["fortress"] is False
    assert out["seria"] == 0
