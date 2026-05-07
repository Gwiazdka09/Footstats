
import pytest
from footstats.betbuilder import _para_sprzeczna, Typ

def test_same_market_conflicts():
    # Mecz 1X2
    assert _para_sprzeczna("Mecz: 1", "Mecz: 2") is True
    assert _para_sprzeczna("Mecz: 1", "Mecz: X") is True
    assert _para_sprzeczna("Mecz: 2", "Mecz: X") is True
    assert _para_sprzeczna("Mecz: 1", "Mecz: 1") is False  # Identical is not conflict
    
    # Tak/Nie
    assert _para_sprzeczna("BTTS: Tak", "BTTS: Nie") is True
    
    # Over/Under same market
    assert _para_sprzeczna("Liczba goli: powyżej 2.5", "Liczba goli: poniżej 1.5") is True
    assert _para_sprzeczna("Liczba goli: powyżej 2.5", "Liczba goli: powyżej 3.5") is True # Redundant (Rule 6)

def test_cross_market_result_conflicts():
    # Draw No Bet vs Match Result
    # DNB 1 means (Win 1 = win, Draw = push). 
    # Mecz 2 means Away win. 
    # They are mutually exclusive.
    assert _para_sprzeczna("Draw No Bet: 1", "Mecz: 2") is True
    assert _para_sprzeczna("Draw No Bet: 1", "Mecz: X") is True
    assert _para_sprzeczna("Draw No Bet: 2", "Mecz: 1") is True
    assert _para_sprzeczna("Draw No Bet: 2", "Mecz: X") is True
    
    # Double Chance vs Match Result
    assert _para_sprzeczna("Podwójna szansa: 1X", "Mecz: 2") is True
    assert _para_sprzeczna("Podwójna szansa: X2", "Mecz: 1") is True
    assert _para_sprzeczna("Podwójna szansa: 12", "Mecz: X") is True

def test_compatible_cross_market():
    # DNB 1 and Mecz 1 are compatible
    assert _para_sprzeczna("Draw No Bet: 1", "Mecz: 1") is False
    
    # Double Chance 1X and Mecz 1 are compatible
    assert _para_sprzeczna("Podwójna szansa: 1X", "Mecz: 1") is False
    assert _para_sprzeczna("Podwójna szansa: 1X", "Mecz: X") is False

def test_case_sensitivity():
    # sa/sb are lowercased in the code, but legacy pairs might be sensitive
    assert _para_sprzeczna("Mecz: X", "Mecz: 1") is True
    assert _para_sprzeczna("mecz: x", "mecz: 1") is True

def test_compound_markets():
    assert _para_sprzeczna("1.Połowa/Mecz: 1/1", "1.Połowa/Mecz: X/X") is True
    assert _para_sprzeczna("1.Połowa/Mecz: 1/1", "1.Połowa/Mecz: 1/1") is False
