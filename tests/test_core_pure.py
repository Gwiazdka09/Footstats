"""Unit tests for pure-logic core modules (no DB/network required)."""
import pytest
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# kelly.py
# ═══════════════════════════════════════════════════════════════

from footstats.core.kelly import kelly_stake, kelly_kupon, dynamic_stake, ev_netto, format_kelly_info


class TestKellyStake:
    def test_positive_edge_returns_stake(self):
        stake = kelly_stake(p=0.60, odds=2.10, bankroll=200, fraction=3)
        assert stake > 0

    def test_stake_bounded_by_min(self):
        # p=0.70, odds=2.10 has edge but tiny bankroll → raw stake < 2.0 → clamped to min
        stake = kelly_stake(p=0.70, odds=2.10, bankroll=5, fraction=10)
        assert stake >= 2.0

    def test_stake_bounded_by_max(self):
        stake = kelly_stake(p=0.99, odds=5.0, bankroll=10000, fraction=1)
        assert stake <= 50.0

    def test_no_edge_returns_zero(self):
        # p=0.30, odds=2.00 → EV negative
        assert kelly_stake(p=0.30, odds=2.00) == 0.0

    def test_odds_at_one_returns_zero(self):
        assert kelly_stake(p=0.70, odds=1.00) == 0.0

    def test_p_zero_returns_zero(self):
        assert kelly_stake(p=0.0, odds=2.0) == 0.0

    def test_p_one_returns_zero(self):
        assert kelly_stake(p=1.0, odds=2.0) == 0.0

    def test_returns_float(self):
        assert isinstance(kelly_stake(p=0.65, odds=2.10), float)


class TestKellyKupon:
    def test_empty_returns_zero(self):
        assert kelly_kupon([]) == 0.0

    def test_single_event(self):
        result = kelly_kupon([{"pewnosc_pct": 65, "kurs": 1.90}])
        assert result >= 0.0

    def test_multi_event_lower_than_single(self):
        single = kelly_kupon([{"pewnosc_pct": 70, "kurs": 1.80}])
        multi = kelly_kupon([
            {"pewnosc_pct": 70, "kurs": 1.80},
            {"pewnosc_pct": 60, "kurs": 1.60},
        ])
        assert multi <= single

    def test_default_pewnosc(self):
        result = kelly_kupon([{"kurs": 2.0}])
        assert result >= 0.0


class TestDynamicStake:
    def test_high_confidence_multiplier(self):
        stake = dynamic_stake(85, 1.80, 10.0)
        assert stake == pytest.approx(15.0)

    def test_mid_confidence_multiplier(self):
        stake = dynamic_stake(70, 1.80, 10.0)
        assert stake == pytest.approx(10.0)

    def test_low_confidence_multiplier(self):
        stake = dynamic_stake(60, 1.80, 10.0)
        assert stake == pytest.approx(5.0)

    def test_high_odds_cap(self):
        stake = dynamic_stake(85, 3.00, 10.0)
        assert stake <= 8.1  # capped at 0.8x

    def test_returns_float(self):
        assert isinstance(dynamic_stake(70, 2.0, 10.0), float)


class TestEvNetto:
    def test_positive_ev(self):
        # p=0.70, odds=2.0 → EV = 0.70*2.0*0.88 - 1 = 0.232
        assert ev_netto(0.70, 2.0) > 0

    def test_negative_ev(self):
        assert ev_netto(0.30, 2.0) < 0

    def test_respects_tax(self):
        ev_12 = ev_netto(0.60, 2.0, podatek=0.12)
        ev_0 = ev_netto(0.60, 2.0, podatek=0.0)
        assert ev_0 > ev_12

    def test_returns_float(self):
        assert isinstance(ev_netto(0.5, 2.0), float)


class TestFormatKellyInfo:
    def test_returns_string(self):
        result = format_kelly_info(0.65, 2.10)
        assert isinstance(result, str)

    def test_contains_kelly_prefix(self):
        result = format_kelly_info(0.65, 2.10)
        assert "Kelly=" in result

    def test_contains_ev_prefix(self):
        result = format_kelly_info(0.65, 2.10)
        assert "EV=" in result


# ═══════════════════════════════════════════════════════════════
# ensemble.py
# ═══════════════════════════════════════════════════════════════

from footstats.core.ensemble import ensemble_probs, get_roznica


class TestEnsembleProbs:
    def test_both_empty_returns_empty(self):
        assert ensemble_probs({}, {}) == {}

    def test_only_poisson(self):
        result = ensemble_probs({"win": 0.60}, {})
        assert result["win"] == pytest.approx(0.60)

    def test_only_bzzoiro(self):
        result = ensemble_probs({}, {"win": 0.55})
        assert result["win"] == pytest.approx(0.55)

    def test_weighted_average(self):
        result = ensemble_probs({"win": 0.40}, {"win": 0.60})
        # default weights: poisson=0.45, bzzoiro=0.55
        expected = (0.40 * 0.45 + 0.60 * 0.55) / 1.0
        assert result["win"] == pytest.approx(expected, abs=1e-4)

    def test_custom_weights(self):
        result = ensemble_probs({"win": 0.40}, {"win": 0.60}, wagi={"poisson": 0.5, "bzzoiro": 0.5})
        assert result["win"] == pytest.approx(0.50)

    def test_all_keys_merged(self):
        result = ensemble_probs({"win": 0.5, "draw": 0.3}, {"win": 0.6, "loss": 0.1})
        assert "win" in result
        assert "draw" in result
        assert "loss" in result


class TestGetRoznica:
    def test_no_diff_returns_zero(self):
        assert get_roznica({"win": 0.5}, {"win": 0.5}, {"win": 0.5}) == 0.0

    def test_returns_max_diff(self):
        diff = get_roznica({}, {"win": 0.70, "draw": 0.20}, {"win": 0.40, "draw": 0.30})
        assert diff == pytest.approx(0.30, abs=1e-4)

    def test_missing_keys_ignored(self):
        diff = get_roznica({}, {"win": 0.70}, {"loss": 0.30})
        assert diff == 0.0


# ═══════════════════════════════════════════════════════════════
# decision_score.py
# ═══════════════════════════════════════════════════════════════

from footstats.core.decision_score import score_kandydat, is_go, PROG_DRAFT, PROG_FINAL


class TestScoreKandydat:
    def _base(self, **overrides):
        data = {
            "ev_netto": 0.05,
            "pewnosc": 75,
            "czynniki": [],
            "roznica_modeli": 10,
            "accuracy": 0.70,
        }
        data.update(overrides)
        return data

    def test_perfect_score_draft(self):
        w = self._base()
        score, _ = score_kandydat(w, phase="draft")
        assert score >= 70

    def test_ev_negative_reduces_score(self):
        w_pos = self._base(ev_netto=0.05)
        w_neg = self._base(ev_netto=-0.05)
        s_pos, _ = score_kandydat(w_pos)
        s_neg, _ = score_kandydat(w_neg)
        assert s_pos > s_neg

    def test_rotacja_reduces_score(self):
        w_clean = self._base(czynniki=[])
        w_rotacja = self._base(czynniki=["ROTACJA"])
        s_clean, _ = score_kandydat(w_clean)
        s_rot, _ = score_kandydat(w_rotacja)
        assert s_clean > s_rot

    def test_patent_adds_points(self):
        w_no = self._base(czynniki=[])
        w_patent = self._base(czynniki=["PATENT"])
        s_no, _ = score_kandydat(w_no)
        s_pat, _ = score_kandydat(w_patent)
        assert s_pat > s_no

    def test_final_phase_lineup_adds_points(self):
        w = self._base()
        s_without, _ = score_kandydat(w, {}, phase="final")
        s_with, _ = score_kandydat(w, {"lineup_ok": True, "referee_neutral": True}, phase="final")
        assert s_with > s_without

    def test_pewnosc_100_scale(self):
        w = self._base(pewnosc=75)  # % form → auto-normalize to 0.75
        score, reasons = score_kandydat(w)
        assert any("Pewność" in r for r in reasons)

    def test_returns_tuple(self):
        result = score_kandydat(self._base())
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_rozbieznosc_large_reduces_score(self):
        w_low = self._base(roznica_modeli=5)
        w_high = self._base(roznica_modeli=25)
        s_low, _ = score_kandydat(w_low)
        s_high, _ = score_kandydat(w_high)
        assert s_low > s_high


class TestIsGo:
    def test_draft_threshold(self):
        assert is_go(PROG_DRAFT, "draft") is True
        assert is_go(PROG_DRAFT - 1, "draft") is False

    def test_final_threshold(self):
        assert is_go(PROG_FINAL, "final") is True
        assert is_go(PROG_FINAL - 1, "final") is False

    def test_returns_bool(self):
        assert isinstance(is_go(50), bool)


# ═══════════════════════════════════════════════════════════════
# value_bet.py (typy_zaklady)
# ═══════════════════════════════════════════════════════════════

from footstats.core.value_bet import typy_zaklady


class TestTypyZaklady:
    def _w(self, pw=60, pr=25, pp=15, bt=50, o25=55, u25=45):
        return {
            "p_wygrana": pw, "p_remis": pr, "p_przegrana": pp,
            "btts": bt, "over25": o25, "under25": u25,
        }

    def test_high_home_win_included(self):
        wyniki = typy_zaklady(self._w(pw=75))
        typy = [t[0] for t in wyniki]
        assert any("Gospodarz" in t for t in typy)

    def test_draw_included_above_32(self):
        wyniki = typy_zaklady(self._w(pr=35))
        typy = [t[0] for t in wyniki]
        assert any("Remis" in t for t in typy)

    def test_draw_not_included_below_32(self):
        wyniki = typy_zaklady(self._w(pr=30))
        typy = [t[0] for t in wyniki]
        assert not any("Remis" in t for t in typy)

    def test_btts_included_above_65(self):
        wyniki = typy_zaklady(self._w(bt=70))
        assert any("BTTS TAK" in t[0] for t in wyniki)

    def test_over25_included_above_70(self):
        wyniki = typy_zaklady(self._w(o25=75))
        assert any("Over 2.5" in t[0] for t in wyniki)

    def test_returns_list(self):
        assert isinstance(typy_zaklady(self._w()), list)

    def test_pewny_vs_dobry_labels(self):
        wyniki = typy_zaklady(self._w(pw=75))
        pewne = [t for t in wyniki if t[2] == "PEWNY"]
        assert pewne


# ═══════════════════════════════════════════════════════════════
# fortress.py
# ═══════════════════════════════════════════════════════════════

from footstats.core.fortress import HomeFortress


class TestHomeFortress:
    def _df(self, records):
        return pd.DataFrame(records)

    def test_empty_df_no_fortress(self):
        hf = HomeFortress(pd.DataFrame())
        result = hf.analiza("PSG")
        assert result["fortress"] is False

    def test_fortress_after_enough_unbeaten(self):
        records = [
            {"gospodarz": "PSG", "goscie": "Lyon", "gole_g": 2, "gole_a": 0, "data": "2026-01-01"},
            {"gospodarz": "PSG", "goscie": "Monaco", "gole_g": 1, "gole_a": 1, "data": "2026-01-15"},
            {"gospodarz": "PSG", "goscie": "Marseille", "gole_g": 3, "gole_a": 0, "data": "2026-02-01"},
            {"gospodarz": "PSG", "goscie": "Lens", "gole_g": 2, "gole_a": 1, "data": "2026-02-15"},
            {"gospodarz": "PSG", "goscie": "Nice", "gole_g": 1, "gole_a": 0, "data": "2026-03-01"},
        ]
        hf = HomeFortress(self._df(records))
        result = hf.analiza("PSG")
        assert result["fortress"] is True
        assert result["bonus_obrona"] > 1.0

    def test_no_fortress_after_loss(self):
        records = [
            {"gospodarz": "PSG", "goscie": "Lyon", "gole_g": 0, "gole_a": 1, "data": "2026-01-01"},
            {"gospodarz": "PSG", "goscie": "Monaco", "gole_g": 2, "gole_a": 0, "data": "2026-01-15"},
            {"gospodarz": "PSG", "goscie": "Marseille", "gole_g": 3, "gole_a": 0, "data": "2026-02-01"},
        ]
        hf = HomeFortress(self._df(records))
        result = hf.analiza("PSG")
        assert result["fortress"] is False

    def test_unknown_team_no_fortress(self):
        records = [{"gospodarz": "PSG", "goscie": "Lyon", "gole_g": 2, "gole_a": 0, "data": "2026-01-01"}]
        hf = HomeFortress(self._df(records))
        result = hf.analiza("Bayern")
        assert result["fortress"] is False

    def test_none_df_no_fortress(self):
        hf = HomeFortress(None)
        result = hf.analiza("PSG")
        assert result["fortress"] is False


# ═══════════════════════════════════════════════════════════════
# fatigue.py
# ═══════════════════════════════════════════════════════════════

from footstats.core.fatigue import HeurystaZmeczeniaRotacji


class TestFatigue:
    def _df(self, records):
        return pd.DataFrame(records)

    def test_empty_df_no_modifiers(self):
        h = HeurystaZmeczeniaRotacji(pd.DataFrame())
        result = h.analiza("Bayern", "2026-04-01")
        assert result["rotacja"] is False
        assert result["zmeczenie"] is False
        assert result["mnoznik_atak"] == 1.0

    def test_fatigue_detected_when_recent_match(self):
        records = [{
            "gospodarz": "Bayern",
            "goscie": "Dortmund",
            "data_full": "2026-04-01 18:00",
            "competition": "BL",
        }]
        h = HeurystaZmeczeniaRotacji(self._df(records))
        # match 40h after last game — below threshold
        result = h.analiza("Bayern", "2026-04-03 10:00")
        assert result["zmeczenie"] is True
        assert result["mnoznik_obr"] < 1.0

    def test_no_fatigue_when_match_old(self):
        records = [{
            "gospodarz": "Bayern",
            "goscie": "Dortmund",
            "data_full": "2026-03-01 18:00",
            "competition": "BL",
        }]
        h = HeurystaZmeczeniaRotacji(self._df(records))
        result = h.analiza("Bayern", "2026-04-01 15:00")
        assert result["zmeczenie"] is False

    def test_none_df(self):
        h = HeurystaZmeczeniaRotacji(None)
        result = h.analiza("Bayern", "2026-04-01")
        assert result["rotacja"] is False

    def test_invalid_date_returns_no_modifiers(self):
        h = HeurystaZmeczeniaRotacji(pd.DataFrame())
        result = h.analiza("Bayern", "not-a-date")
        assert result["mnoznik_atak"] == 1.0


# ═══════════════════════════════════════════════════════════════
# importance.py
# ═══════════════════════════════════════════════════════════════

from footstats.core.importance import ImportanceIndex


class TestImportanceIndex:
    def _df(self, druzyna, poz, rozegrane):
        return pd.DataFrame([{"Druzyna": druzyna, "Poz.": poz, "M": rozegrane}])

    def test_empty_df_returns_normal(self):
        ii = ImportanceIndex(pd.DataFrame())
        result = ii.analiza("Bayern")
        assert result["status"] == "NORMAL"

    def test_final_top_status(self):
        df = self._df("PSG", 2, 33)  # 33/34 → 1 kolejka left → TRYB FINALNY
        ii = ImportanceIndex(df, n_druzyn=20)
        result = ii.analiza("PSG")
        assert result["status"] == "FINAL_TOP"
        assert result["bonus_atak"] > 1.0

    def test_final_relegation_status(self):
        df = self._df("Metz", 19, 33)  # position 19/20 → spadek
        ii = ImportanceIndex(df, n_druzyn=20)
        result = ii.analiza("Metz")
        assert result["status"] == "FINAL_RELEGATION"

    def test_vacation_status_mid_table(self):
        df = self._df("Lyon", 10, 33)  # mid-table, final mode
        ii = ImportanceIndex(df, n_druzyn=20)
        result = ii.analiza("Lyon")
        assert result["status"] == "VACATION"
        assert result["bonus_atak"] < 1.0

    def test_unknown_team_returns_normal(self):
        df = self._df("PSG", 1, 20)
        ii = ImportanceIndex(df)
        result = ii.analiza("Bayern")
        assert result["status"] == "NORMAL"

    def test_comfort_mid_season(self):
        df = self._df("Lyon", 10, 20)  # mid-table, 14 kolejek left
        ii = ImportanceIndex(df, n_druzyn=20)
        result = ii.analiza("Lyon")
        assert result["status"] == "COMFORT"
        assert result["bonus_atak"] < 1.0


# ═══════════════════════════════════════════════════════════════
# xg_lambda.py
# ═══════════════════════════════════════════════════════════════

from footstats.core.xg_lambda import xg_lambda, xg_lambda_pair


class TestXgLambda:
    def _df(self, home, away, hg, ag, xg_home=None, xg_away=None):
        records = []
        for h, a, hg_, ag_ in zip(home, away, hg, ag):
            r = {"home": h, "away": a, "hg": hg_, "ag": ag_}
            if xg_home is not None:
                r["xg_home"] = xg_home
                r["xg_away"] = xg_away
            records.append(r)
        return pd.DataFrame(records)

    def test_empty_df_returns_min_lambda(self):
        result = xg_lambda("PSG", pd.DataFrame())
        assert result > 0

    def test_none_df_returns_min_lambda(self):
        result = xg_lambda("PSG", None)
        assert result > 0

    def test_home_lambda_from_goals(self):
        df = self._df(["PSG"] * 5, ["Lyon"] * 5, [2, 3, 1, 2, 2], [0, 1, 0, 1, 0])
        result = xg_lambda("PSG", df, strona="home")
        assert result == pytest.approx(2.0, abs=0.5)

    def test_unknown_team_returns_min_lambda(self):
        df = self._df(["PSG"], ["Lyon"], [2], [1])
        result = xg_lambda("Bayern", df, strona="home")
        from footstats.core.xg_lambda import _MIN_LAMBDA
        assert result == _MIN_LAMBDA

    def test_xg_used_when_available(self):
        df = self._df(["PSG"], ["Lyon"], [3], [1], xg_home=1.5, xg_away=0.8)
        result = xg_lambda("PSG", df, strona="home")
        # xg_home=1.5 used instead of hg=3
        assert result == pytest.approx(1.5, abs=0.1)


class TestXgLambdaPair:
    def test_returns_tuple_of_floats(self):
        df = pd.DataFrame([
            {"home": "PSG", "away": "Lyon", "hg": 2, "ag": 1},
        ])
        lh, la = xg_lambda_pair("PSG", "Lyon", df)
        assert isinstance(lh, float)
        assert isinstance(la, float)

    def test_both_positive(self):
        df = pd.DataFrame([{"home": "A", "away": "B", "hg": 2, "ag": 1}])
        lh, la = xg_lambda_pair("A", "B", df)
        assert lh > 0
        assert la > 0
