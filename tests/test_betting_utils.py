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
