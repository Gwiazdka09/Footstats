"""Testy edge case'ów rozliczania kuponów — oblicz_tip_correct."""
from footstats.utils.betting import oblicz_tip_correct


# ── 1X2 — wynik bramkowy ──────────────────────────────────────────────────

def test_tip_1_home_win():
    assert oblicz_tip_correct("1", "2-1") == 1


def test_tip_1_draw():
    assert oblicz_tip_correct("1", "1-1") == 0


def test_tip_x_draw():
    assert oblicz_tip_correct("X", "0-0") == 1


def test_tip_2_away_win():
    assert oblicz_tip_correct("2", "1-3") == 1


def test_tip_2_home_win():
    assert oblicz_tip_correct("2", "2-0") == 0


# ── 1X2 — wynik symboliczny ───────────────────────────────────────────────

def test_symbolic_result_1():
    assert oblicz_tip_correct("1", "1") == 1
    assert oblicz_tip_correct("2", "1") == 0


def test_symbolic_result_x():
    assert oblicz_tip_correct("X", "X") == 1
    assert oblicz_tip_correct("1", "X") == 0


# ── Double chance ─────────────────────────────────────────────────────────

def test_double_chance_1x_home():
    assert oblicz_tip_correct("1X", "3-0") == 1


def test_double_chance_1x_draw():
    assert oblicz_tip_correct("1X", "1-1") == 1


def test_double_chance_1x_away():
    assert oblicz_tip_correct("1X", "0-2") == 0


def test_double_chance_x2_away():
    assert oblicz_tip_correct("X2", "0-1") == 1


def test_double_chance_12_no_draw():
    assert oblicz_tip_correct("12", "1-1") == 0
    assert oblicz_tip_correct("12", "2-0") == 1
    assert oblicz_tip_correct("12", "0-1") == 1


# ── Over/Under ────────────────────────────────────────────────────────────

def test_over25_hit():
    assert oblicz_tip_correct("OVER2.5", "2-1") == 1  # 3 gole


def test_over25_miss():
    assert oblicz_tip_correct("OVER2.5", "1-1") == 0  # 2 gole


def test_under25_hit():
    assert oblicz_tip_correct("UNDER2.5", "1-0") == 1  # 1 gol


def test_under25_miss():
    assert oblicz_tip_correct("UNDER2.5", "2-1") == 0  # 3 gole


# ── BTTS ──────────────────────────────────────────────────────────────────

def test_btts_yes():
    assert oblicz_tip_correct("BTTS", "1-1") == 1


def test_btts_no_one_team_zero():
    assert oblicz_tip_correct("BTTS", "2-0") == 0


# ── Edge cases ────────────────────────────────────────────────────────────

def test_none_result_returns_none():
    assert oblicz_tip_correct("1", None) is None


def test_empty_result_returns_none():
    assert oblicz_tip_correct("1", "") is None


def test_tuple_result():
    assert oblicz_tip_correct("1", (2, 1)) == 1
    assert oblicz_tip_correct("2", (2, 1)) == 0


def test_list_result():
    assert oblicz_tip_correct("X", [1, 1]) == 1


def test_result_with_aet():
    # "2-1 (AET)" — extra time annotation should be stripped
    assert oblicz_tip_correct("1", "2-1 (AET)") == 1


def test_lowercase_result():
    # ensure robust to lowercase
    assert oblicz_tip_correct("1", "1") == 1
