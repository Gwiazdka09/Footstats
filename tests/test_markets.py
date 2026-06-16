"""
test_markets.py — FAZA 20: katalog rynków bramkowych z Poissona.
Krytyczny wymóg: KAŻDY tip w katalogu musi być rozliczalny (oblicz_tip_correct).
"""
import pytest

from footstats.core.markets import build_market_catalog
from footstats.utils.betting import oblicz_tip_correct


def test_katalog_ma_grupy_i_rynki():
    cat = build_market_catalog(1.6, 1.2)
    assert len(cat) >= 7
    assert sum(len(g["rynki"]) for g in cat) >= 30
    for g in cat:
        assert "grupa" in g and "rynki" in g


def test_wszystkie_tipy_rozliczalne():
    """Każdy tip z katalogu daje 0/1 (nie None) dla realnego wyniku."""
    cat = build_market_catalog(2.0, 1.0)
    for g in cat:
        for r in g["rynki"]:
            for score in ("3-1", "0-0", "1-1", "2-2"):
                wynik = oblicz_tip_correct(r["tip"], score)
                assert wynik in (0, 1), f"{r['rynek']} ({r['tip']}) @ {score} = {wynik}"


def test_1x2_sumuje_do_100():
    cat = build_market_catalog(1.5, 1.5)
    wynik = next(g for g in cat if g["grupa"] == "Wynik meczu")
    suma = sum(r["szansa"] for r in wynik["rynki"])
    assert abs(suma - 100.0) < 0.5


def test_bzzoiro_kurs_uzyty_gdy_dostepny():
    cat = build_market_catalog(1.8, 1.1, bzz_odds={"home": 1.65, "btts": 2.1})
    wynik = next(g for g in cat if g["grupa"] == "Wynik meczu")
    dom = next(r for r in wynik["rynki"] if r["tip"] == "1")
    assert dom["kurs"] == 1.65
    assert dom["zrodlo"] == "bzzoiro"


def test_fair_kurs_gdy_brak_bzzoiro():
    cat = build_market_catalog(1.8, 1.1)
    wynik = next(g for g in cat if g["grupa"] == "Wynik meczu")
    dom = next(r for r in wynik["rynki"] if r["tip"] == "1")
    assert dom["zrodlo"] == "fair"
    # fair ≈ 1/prob
    assert dom["kurs"] == pytest.approx(round(100.0 / dom["szansa"], 2), abs=0.05)


def test_handicap_w_katalogu():
    cat = build_market_catalog(2.2, 0.8)
    hcp = next(g for g in cat if g["grupa"] == "Handicap")
    tipy = {r["tip"] for r in hcp["rynki"]}
    assert "1 (-1.5)" in tipy
    assert "2 (+1.5)" in tipy


def test_silny_faworyt_wyzsza_szansa_1():
    cat = build_market_catalog(2.5, 0.6)
    wynik = next(g for g in cat if g["grupa"] == "Wynik meczu")
    p1 = next(r["szansa"] for r in wynik["rynki"] if r["tip"] == "1")
    p2 = next(r["szansa"] for r in wynik["rynki"] if r["tip"] == "2")
    assert p1 > p2
