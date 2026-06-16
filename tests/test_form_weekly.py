"""
test_form_weekly.py — testy czystych funkcji form.py + weekly_picks._typy_pewne (TD-31).
"""
import pandas as pd

from footstats.core.form import (
    _wagi_mecze, _oblicz_sile_wazona, pobierz_forme, AnalizaDomWyjazd,
)
from footstats.core.weekly_picks import _typy_pewne


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _mecz(g, a, gg, ga, data="2026-01-01"):
    return {"gospodarz": g, "goscie": a, "gole_g": gg, "gole_a": ga, "data": data}


# ── form._wagi_mecze ──────────────────────────────────────────────────────

def test_wagi_najnowsze_mecze_wyzsza_waga():
    df = _df([_mecz("A", "B", 1, 0, f"2026-01-{i:02d}") for i in range(1, 11)])
    wagi = _wagi_mecze(df)
    # 3 najnowsze (ostatnie indeksy) = 1.5
    assert list(wagi)[-3:] == [1.5, 1.5, 1.5]
    # najstarsze (poz 7+ od końca) = 0.5
    assert list(wagi)[0] == 0.5


def test_wagi_krotka_historia():
    df = _df([_mecz("A", "B", 1, 0), _mecz("A", "C", 2, 1)])
    wagi = _wagi_mecze(df)
    assert all(w == 1.5 for w in wagi)  # oba w top-3


# ── form._oblicz_sile_wazona ──────────────────────────────────────────────

def test_sila_wazona_struktura():
    df = _df([
        _mecz("A", "B", 2, 0, "2026-01-01"),
        _mecz("C", "A", 1, 1, "2026-01-02"),
        _mecz("A", "C", 3, 1, "2026-01-03"),
    ])
    sily, srednia = _oblicz_sile_wazona(df)
    assert "A" in sily
    assert srednia > 0
    for klucz in ("atak", "obrona", "mecze", "forma_pkt"):
        assert klucz in sily["A"]


def test_sila_mocny_atak_wyzszy():
    # A strzela dużo, B mało
    df = _df([
        _mecz("A", "X", 4, 0, "2026-01-01"),
        _mecz("A", "Y", 3, 0, "2026-01-02"),
        _mecz("B", "X", 0, 1, "2026-01-03"),
        _mecz("B", "Y", 0, 2, "2026-01-04"),
    ])
    sily, _ = _oblicz_sile_wazona(df)
    assert sily["A"]["atak"] > sily["B"]["atak"]


# ── form.pobierz_forme ────────────────────────────────────────────────────

def test_pobierz_forme_wynik_wrp():
    df = _df([
        _mecz("A", "B", 2, 0, "2026-01-01"),  # A dom W
        _mecz("C", "A", 1, 1, "2026-01-02"),  # A wyjazd R
        _mecz("D", "A", 2, 0, "2026-01-03"),  # A wyjazd P
    ])
    forma = pobierz_forme("A", df, n=8)
    wyniki = list(forma["wynik"])
    assert "W" in wyniki and "R" in wyniki and "P" in wyniki


def test_pobierz_forme_pusta_dla_nieznanej():
    df = _df([_mecz("A", "B", 1, 0)])
    forma = pobierz_forme("NieMa", df, n=8)
    assert forma.empty


# ── form.AnalizaDomWyjazd ─────────────────────────────────────────────────

def test_domwyjazd_pusta_baza():
    out = AnalizaDomWyjazd(pd.DataFrame()).analiza("A")
    assert out["podroznik"] is False
    assert out["dom_m"] == 0


def test_domwyjazd_podroznik():
    # A: słaby u siebie (same remisy=1pkt), mocny na wyjeździe (same wygrane=3pkt), 5+ meczów
    rows = []
    for i in range(6):
        rows.append(_mecz("A", "H", 1, 1, f"2026-02-{i+1:02d}"))   # dom remis
    for i in range(6):
        rows.append(_mecz("W", "A", 0, 2, f"2026-03-{i+1:02d}"))   # wyjazd A wygrywa
    out = AnalizaDomWyjazd(_df(rows)).analiza("A")
    assert out["podroznik"] is True
    assert out["bonus_wyjazd"] > 1.0
    assert out["wyjazd_pkt"] > out["dom_pkt"]


# ── weekly_picks._typy_pewne ──────────────────────────────────────────────

def test_typy_pewne_zwraca_powyzej_progu():
    # pw=70 (1), pp=10, pr=20 → 1X=90, 12=80; prog 60
    typy = _typy_pewne(pw=70, pr=20, pp=10, bt=55, o25=65, u25=35, g="Arsenal", a="Chelsea", prog=60)
    opisy = [t[0] for t in typy]
    assert any("1 –" in o for o in opisy)        # pw=70 >= 60
    assert any("1X" in o for o in opisy)         # 90 >= 60
    assert any("Over 2.5" in o for o in opisy)   # 65 >= 60
    # poniżej progu nie ma
    assert not any("Under 2.5" in o for o in opisy)  # u25=35 < 60


def test_typy_pewne_pusty_gdy_wszystko_ponizej():
    typy = _typy_pewne(pw=30, pr=30, pp=30, bt=40, o25=45, u25=55, g="A", a="B", prog=90)
    assert typy == []


def test_typy_pewne_szansa_zaokraglona():
    typy = _typy_pewne(pw=72.345, pr=10, pp=10, bt=10, o25=10, u25=10, g="A", a="B", prog=70)
    # pierwszy typ "1" z szansą 72.3
    assert typy[0][1] == 72.3
