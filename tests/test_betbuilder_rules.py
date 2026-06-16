"""
test_betbuilder_rules.py — FAZA 18.1: reguły korelacji manualnego BetBuilder.
Weryfikuje zabezpieczenia: sprzeczne (1+2), trywialne (1⇒Over 0.5), dozwolone (1+Over 1.5).
"""
from footstats.core.betbuilder_rules import (
    czy_dozwolony, dozwolone_dodatki, powod_blokady, szansa_combo, WSZYSTKIE_RYNKI,
)


# ── Sprzeczności (brak wspólnego wyniku) ──────────────────────────────────

def test_1_i_2_sprzeczne():
    assert czy_dozwolony("2", ["1"]) is False
    assert "sprzeczny" in powod_blokady("2", ["1"])


def test_1x2_wzajemnie_wykluczajace():
    assert czy_dozwolony("X", ["1"]) is False
    assert czy_dozwolony("1", ["X"]) is False
    assert czy_dozwolony("2", ["X"]) is False


def test_over25_under25_sprzeczne():
    assert czy_dozwolony("Under 2.5", ["Over 2.5"]) is False


def test_btts_kontra_under15():
    # BTTS wymaga >=2 goli, Under 1.5 to <=1 → sprzeczne
    assert czy_dozwolony("Under 1.5", ["BTTS"]) is False


# ── Trywialne / implikowane (blokada) ─────────────────────────────────────

def test_1_blokuje_over05():
    # Kluczowy wymóg: "1" ⇒ co najmniej 1 gol ⇒ Over 0.5 trywialne
    assert czy_dozwolony("Over 0.5", ["1"]) is False
    assert "trywialny" in powod_blokady("Over 0.5", ["1"])


def test_1_blokuje_gospodarz_over05():
    # "1" (gospodarz wygrywa) ⇒ gospodarz strzelił ≥1
    assert czy_dozwolony("Gospodarz Over 0.5", ["1"]) is False


def test_2_blokuje_gosc_over05():
    assert czy_dozwolony("Gość Over 0.5", ["2"]) is False


def test_over25_blokuje_slabsze_over():
    # Over 2.5 ⇒ Over 1.5 i Over 0.5 trywialne
    assert czy_dozwolony("Over 1.5", ["Over 2.5"]) is False
    assert czy_dozwolony("Over 0.5", ["Over 2.5"]) is False


def test_btts_blokuje_over15():
    # BTTS ⇒ oba strzeliły ⇒ >=2 gole ⇒ Over 1.5 trywialne
    assert czy_dozwolony("Over 1.5", ["BTTS"]) is False


# ── Dozwolone realne combo ────────────────────────────────────────────────

def test_1_plus_over15_dozwolone():
    assert czy_dozwolony("Over 1.5", ["1"]) is True
    assert powod_blokady("Over 1.5", ["1"]) is None


def test_1_plus_btts_dozwolone():
    assert czy_dozwolony("BTTS", ["1"]) is True


def test_1_plus_over25_dozwolone():
    assert czy_dozwolony("Over 2.5", ["1"]) is True


def test_over25_plus_under35_band():
    # Over 2.5 + Under 3.5 = dokładnie 3 gole → dozwolone (wąski band)
    assert czy_dozwolony("Under 3.5", ["Over 2.5"]) is True


def test_handicap_minus1_plus_btts():
    # Gospodarz wygrywa 2+ różnicą + oba strzelą (np. 3:1) → osiągalne, zawęża
    assert czy_dozwolony("BTTS", ["Handicap -1 Gospodarz"]) is True


# ── dozwolone_dodatki ─────────────────────────────────────────────────────

def test_dozwolone_dodatki_pusta_lista():
    # Bez wyborów wszystkie rynki dozwolone (każdy zawęża pełną siatkę)
    out = dozwolone_dodatki([])
    assert set(out) == set(WSZYSTKIE_RYNKI)


def test_dozwolone_dodatki_po_wyborze_1():
    out = dozwolone_dodatki(["1"])
    # Zablokowane: X, 2, Over 0.5, Gospodarz Over 0.5
    assert "X" not in out
    assert "2" not in out
    assert "Over 0.5" not in out
    assert "Gospodarz Over 0.5" not in out
    # Dozwolone realne
    assert "Over 1.5" in out
    assert "BTTS" in out


def test_dozwolone_dodatki_nie_zawiera_juz_wybranych():
    out = dozwolone_dodatki(["1", "Over 1.5"])
    assert "1" not in out
    assert "Over 1.5" not in out


# ── szansa_combo ──────────────────────────────────────────────────────────

def test_szansa_combo_pusta_zero():
    assert szansa_combo([], [[1.0]]) == 0.0


def test_szansa_combo_zaweza_sie():
    from footstats.core.bet_builder import probability_matrix
    mat = probability_matrix(1.8, 1.2)
    p_1 = szansa_combo(["1"], mat)
    p_1_o15 = szansa_combo(["1", "Over 1.5"], mat)
    # Dodanie warunku może tylko zmniejszyć lub utrzymać szansę
    assert 0.0 < p_1_o15 <= p_1 <= 1.0


def test_szansa_combo_sprzeczne_zero():
    from footstats.core.bet_builder import probability_matrix
    mat = probability_matrix(1.5, 1.5)
    assert szansa_combo(["1", "2"], mat) == 0.0
