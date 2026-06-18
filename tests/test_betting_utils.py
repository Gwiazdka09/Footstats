"""Unit tests for utils/betting.py — oblicz_tip_correct and typy_zaklady."""
import pytest
from footstats.utils.betting import oblicz_tip_correct


class TestObliczTipCorrect:
    # ── 1/X/2 from score strings ──────────────────────────────────────────────

    def test_home_win_tip1_correct(self):
        assert oblicz_tip_correct("1", "2-1") == 1

    def test_home_win_tip1_wrong(self):
        assert oblicz_tip_correct("2", "2-1") == 0

    def test_draw_tipX_correct(self):
        assert oblicz_tip_correct("X", "1-1") == 1

    def test_draw_tipX_wrong(self):
        assert oblicz_tip_correct("1", "1-1") == 0

    def test_away_win_tip2_correct(self):
        assert oblicz_tip_correct("2", "0-1") == 1

    # ── Double chance ─────────────────────────────────────────────────────────

    def test_1x_home_win(self):
        assert oblicz_tip_correct("1X", "2-0") == 1

    def test_1x_draw(self):
        assert oblicz_tip_correct("1X", "0-0") == 1

    def test_1x_away_loss(self):
        assert oblicz_tip_correct("1X", "0-2") == 0

    def test_x2_draw(self):
        assert oblicz_tip_correct("X2", "0-0") == 1

    def test_x2_away_win(self):
        assert oblicz_tip_correct("X2", "1-2") == 1

    def test_x2_home_win(self):
        assert oblicz_tip_correct("X2", "2-0") == 0

    def test_12_home_win(self):
        assert oblicz_tip_correct("12", "2-1") == 1

    def test_12_draw(self):
        assert oblicz_tip_correct("12", "0-0") == 0

    # ── Over / Under ──────────────────────────────────────────────────────────

    def test_over25_correct(self):
        assert oblicz_tip_correct("OVER 2.5", "2-1") == 1  # 3 goals

    def test_over25_wrong(self):
        assert oblicz_tip_correct("OVER 2.5", "1-1") == 0  # 2 goals

    def test_under25_correct(self):
        assert oblicz_tip_correct("UNDER 2.5", "1-0") == 1  # 1 goal

    def test_under25_wrong(self):
        assert oblicz_tip_correct("UNDER 2.5", "2-1") == 0  # 3 goals

    # ── BTTS ──────────────────────────────────────────────────────────────────

    def test_btts_both_score(self):
        assert oblicz_tip_correct("BTTS", "1-1") == 1

    def test_btts_one_nil(self):
        assert oblicz_tip_correct("BTTS", "2-0") == 0

    def test_btts_no(self):
        assert oblicz_tip_correct("BTTS NO", "2-0") == 1

    def test_no_btts_both_score(self):
        assert oblicz_tip_correct("NO BTTS", "1-1") == 0

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_no_result_returns_none(self):
        assert oblicz_tip_correct("1", None) is None

    def test_empty_result_returns_none(self):
        assert oblicz_tip_correct("1", "") is None

    def test_tuple_result(self):
        assert oblicz_tip_correct("1", (2, 1)) == 1

    def test_list_result(self):
        assert oblicz_tip_correct("2", [0, 1]) == 1

    def test_aet_suffix_stripped(self):
        assert oblicz_tip_correct("1", "2-1 (AET)") == 1

    def test_unknown_tip_returns_none(self):
        assert oblicz_tip_correct("UNKNOWN", "2-1") is None

    def test_invalid_score_returns_none(self):
        assert oblicz_tip_correct("1", "bad-score") is None

    def test_raw_result_1(self):
        assert oblicz_tip_correct("1", "1") == 1

    def test_raw_result_X(self):
        assert oblicz_tip_correct("X", "X") == 1

    def test_case_insensitive_tip(self):
        assert oblicz_tip_correct("over 2.5", "2-1") == 1

    # ── Handicap europejski (FAZA 20) ─────────────────────────────────────────

    def test_handicap_home_minus15_hit(self):
        assert oblicz_tip_correct("1 (-1.5)", "3-1") == 1   # margin 2

    def test_handicap_home_minus15_miss(self):
        assert oblicz_tip_correct("1 (-1.5)", "2-1") == 0   # margin 1

    def test_handicap_away_plus15_hit(self):
        assert oblicz_tip_correct("2 (+1.5)", "2-1") == 1   # przegrał o 1, +1.5 ratuje

    def test_handicap_away_plus15_miss(self):
        assert oblicz_tip_correct("2 (+1.5)", "3-1") == 0

    def test_handicap_home_minus05_equiv_win(self):
        assert oblicz_tip_correct("1 (-0.5)", "1-0") == 1
        assert oblicz_tip_correct("1 (-0.5)", "1-1") == 0

    def test_handicap_brak_wyniku_none(self):
        assert oblicz_tip_correct("1 (-1.5)", "1") is None  # brak bramek

    # ── Parzyste / nieparzyste (FAZA 20) ──────────────────────────────────────

    def test_parzyste_hit(self):
        assert oblicz_tip_correct("PARZYSTE", "1-1") == 1   # 2 gole

    def test_parzyste_zero_to_parzyste(self):
        assert oblicz_tip_correct("PARZYSTE", "0-0") == 1   # 0 = parzyste

    def test_nieparzyste_hit(self):
        assert oblicz_tip_correct("NIEPARZYSTE", "2-1") == 1  # 3 gole

    def test_parzyste_miss(self):
        assert oblicz_tip_correct("PARZYSTE", "2-1") == 0

    # ── BetBuilder combo = koniunkcja członów (krytyczny fix) ─────────────────

    def test_bb_combo_oba_trafione(self):
        assert oblicz_tip_correct("BB: 1 + Over 1.5", "3-1") == 1

    def test_bb_combo_pierwszy_czlon_przegral(self):
        # gospodarz PRZEGRAL (1-3) → combo przegrane mimo Over
        assert oblicz_tip_correct("BB: 1 + Over 1.5", "1-3") == 0

    def test_bb_combo_drugi_czlon_przegral(self):
        # 1 wygral (3-0) ale Under 3.5 też trafione (total 3) → wygrane
        assert oblicz_tip_correct("BB: 1 + Under 3.5", "3-0") == 1
        # 1 wygral ale total 4 > 3.5 → Under nietrafione → przegrane
        assert oblicz_tip_correct("BB: 1 + Under 3.5", "3-1") == 0

    def test_bb_combo_btts(self):
        assert oblicz_tip_correct("BB: 2 + BTTS", "1-2") == 1   # gość wygrał + oba strzeliły
        assert oblicz_tip_correct("BB: 2 + BTTS", "2-1") == 0   # gość przegrał

    def test_bb_combo_czlon_nierozliczalny_none(self):
        # nieznany człon → całość None (nie zgaduj)
        assert oblicz_tip_correct("BB: 1 + Zawodnik gola", "2-1") is None
