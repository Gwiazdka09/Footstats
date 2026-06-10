"""Tests for core.risk_proposals — daily low/medium/high risk coupon proposals."""
from footstats.core.risk_proposals import build_daily_proposals, RISK_TIERS


def _match(mid, prob_home, odds_home, prob_over=55.0, odds_over=1.8):
    return {
        "id": mid,
        "gosp": f"Dom{mid}",
        "gosc": f"Gosc{mid}",
        "liga": "Test League",
        "data": "2026-06-15",
        "godzina": "18:00",
        "pred_ml": {
            "prob_home_win": prob_home,
            "prob_draw": (1 - prob_home) * 0.4,
            "prob_away_win": (1 - prob_home) * 0.6,
            "prob_over_25": prob_over / 100.0,
            "prob_btts_yes": 0.5,
        },
        "odds": {"home": odds_home, "over_2_5": odds_over},
    }


class TestBuildDailyProposals:
    def test_returns_all_three_tiers(self):
        result = build_daily_proposals([_match("m1", 0.65, 1.4)])
        assert set(result.keys()) == set(RISK_TIERS)
        for tier in RISK_TIERS:
            assert "legs" in result[tier]
            assert "total_odds" in result[tier]

    def test_strong_favorite_goes_to_low_risk(self):
        result = build_daily_proposals([_match("m1", 0.70, 1.3)])
        low_legs = result["low"]["legs"]
        assert len(low_legs) == 1
        assert low_legs[0]["match_id"] == "m1"
        assert low_legs[0]["odds"] <= 1.6

    def test_high_odds_goes_to_high_risk(self):
        result = build_daily_proposals([_match("m1", 0.30, 3.5)])
        high_legs = result["high"]["legs"]
        assert any(leg["match_id"] == "m1" for leg in high_legs)

    def test_total_odds_is_product_of_legs(self):
        result = build_daily_proposals([
            _match("m1", 0.70, 1.3),
            _match("m2", 0.65, 1.4),
        ])
        legs = result["low"]["legs"]
        expected = round(legs[0]["odds"] * legs[1]["odds"], 2) if len(legs) == 2 else legs[0]["odds"]
        assert result["low"]["total_odds"] == expected

    def test_max_legs_per_tier_respected(self):
        matches = [_match(f"m{i}", 0.70, 1.3) for i in range(10)]
        result = build_daily_proposals(matches, max_legs=3)
        assert len(result["low"]["legs"]) == 3

    def test_empty_predictions_returns_empty_tiers(self):
        result = build_daily_proposals([])
        for tier in RISK_TIERS:
            assert result[tier]["legs"] == []
            assert result[tier]["total_odds"] == 0.0
