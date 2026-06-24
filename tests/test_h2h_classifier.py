"""Unit tests for h2h.py and classifier.py."""
import pandas as pd
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════
# classifier.py — _czy_knockout + KlasyfikatorMeczu
# ═══════════════════════════════════════════════════════════════

from footstats.core.classifier import _czy_knockout, KlasyfikatorMeczu


class TestCzyKnockout:
    def test_final_is_knockout(self):
        assert _czy_knockout("FINAL") is True

    def test_semi_finals_is_knockout(self):
        assert _czy_knockout("SEMI_FINALS") is True

    def test_last16_is_knockout(self):
        assert _czy_knockout("LAST_16") is True

    def test_regular_season_not_knockout(self):
        assert _czy_knockout("REGULAR_SEASON") is False

    def test_case_insensitive(self):
        assert _czy_knockout("final") is True

    def test_unknown_stage_not_knockout(self):
        assert _czy_knockout("GROUP_STAGE") is False


class TestKlasyfikatorMeczu:
    def _klasyfikator(self, records=None, kod=""):
        df = pd.DataFrame(records) if records else pd.DataFrame()
        return KlasyfikatorMeczu(df, kod_ligi=kod)

    def test_liga_regular_season(self):
        k = self._klasyfikator()
        result = k.klasyfikuj("PSG", "Lyon", "REGULAR_SEASON", "2026-04-01")
        assert result["typ"] == "LIGA"
        assert result["rewanz"] is False

    def test_final_stage(self):
        k = self._klasyfikator()
        result = k.klasyfikuj("PSG", "Lyon", "FINAL", "2026-04-01")
        assert result["typ"] == "FINAL"
        assert result["single"] is True

    def test_knockout_without_history_is_puchar1(self):
        k = self._klasyfikator()
        result = k.klasyfikuj("PSG", "Lyon", "QUARTER_FINALS", "2026-04-01")
        assert result["typ"] == "PUCHAR_1"

    def test_rewanz_detected_from_history(self):
        # First leg 7 days ago
        first_leg_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        records = [{
            "gospodarz": "Lyon",
            "goscie": "PSG",
            "gole_g": 1,
            "gole_a": 2,
            "data": first_leg_date,
            "stage": "QUARTER_FINALS",
        }]
        k = self._klasyfikator(records)
        result = k.klasyfikuj("PSG", "Lyon", "QUARTER_FINALS", datetime.now().strftime("%Y-%m-%d"))
        assert result["rewanz"] is True
        assert result["typ"] == "REWANZ"

    def test_returns_dict_keys(self):
        k = self._klasyfikator()
        result = k.klasyfikuj("A", "B", "REGULAR_SEASON", "2026-01-01")
        for key in ("typ", "etykieta", "rewanz", "single", "agg_g", "agg_a", "opis"):
            assert key in result

    def test_none_df(self):
        k = KlasyfikatorMeczu(None)
        result = k.klasyfikuj("A", "B", "REGULAR_SEASON", "2026-01-01")
        assert result["typ"] == "LIGA"


# ═══════════════════════════════════════════════════════════════
# h2h.py — AnalizaH2H
# ═══════════════════════════════════════════════════════════════

from footstats.core.h2h import AnalizaH2H


class TestAnalizaH2H:
    def _make_df(self, records):
        return pd.DataFrame(records)

    def _recent_date(self, days_ago=30):
        return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def test_empty_df_returns_base_pewnosc(self):
        h = AnalizaH2H(pd.DataFrame())
        result = h.analiza("PSG", "Lyon")
        assert result["pewnosc"] == 20
        assert result["patent"] is False
        assert result["zemsta"] is False

    def test_none_df(self):
        h = AnalizaH2H(None)
        result = h.analiza("PSG", "Lyon")
        assert result["patent"] is False

    def test_one_h2h_match_increases_confidence(self):
        records = [{
            "gospodarz": "PSG", "goscie": "Lyon",
            "gole_g": 2, "gole_a": 1, "data": self._recent_date(30),
        }]
        h = AnalizaH2H(self._make_df(records))
        result = h.analiza("PSG", "Lyon")
        assert result["pewnosc"] >= 40

    def test_patent_detected_on_all_wins(self):
        records = [
            {"gospodarz": "PSG", "goscie": "Lyon", "gole_g": 3, "gole_a": 0, "data": self._recent_date(60)},
            {"gospodarz": "PSG", "goscie": "Lyon", "gole_g": 2, "gole_a": 1, "data": self._recent_date(30)},
        ]
        h = AnalizaH2H(self._make_df(records))
        result = h.analiza("PSG", "Lyon")
        assert result["patent"] is True
        assert result["mnoznik_szans"] > 1.0

    def test_zemsta_detected_after_heavy_loss(self):
        records = [{
            "gospodarz": "PSG", "goscie": "Lyon",
            "gole_g": 0, "gole_a": 4,  # Lyon won 4-0
            "data": self._recent_date(20),
        }]
        h = AnalizaH2H(self._make_df(records))
        result = h.analiza("PSG", "Lyon")  # PSG was home team → PSG lost 0-4
        assert result["zemsta"] is True
        assert result["mnoznik_atak"] > 1.0

    def test_no_zemsta_on_close_match(self):
        records = [{
            "gospodarz": "PSG", "goscie": "Lyon",
            "gole_g": 1, "gole_a": 2,  # Only 1 goal difference
            "data": self._recent_date(20),
        }]
        h = AnalizaH2H(self._make_df(records))
        result = h.analiza("PSG", "Lyon")
        assert result["zemsta"] is False

    def test_old_matches_filtered_out(self):
        records = [{
            "gospodarz": "PSG", "goscie": "Lyon",
            "gole_g": 2, "gole_a": 0,
            "data": "2020-01-01",  # > 24 months ago
        }]
        h = AnalizaH2H(self._make_df(records))
        result = h.analiza("PSG", "Lyon")
        assert result["n_h2h"] == 0

    def test_n_h2h_counts_both_directions(self):
        records = [
            {"gospodarz": "PSG", "goscie": "Lyon", "gole_g": 2, "gole_a": 1, "data": self._recent_date(30)},
            {"gospodarz": "Lyon", "goscie": "PSG", "gole_g": 1, "gole_a": 1, "data": self._recent_date(60)},
        ]
        h = AnalizaH2H(self._make_df(records))
        result = h.analiza("PSG", "Lyon")
        assert result["n_h2h"] == 2

    def test_returns_required_keys(self):
        h = AnalizaH2H(pd.DataFrame())
        result = h.analiza("A", "B")
        for key in ("patent", "zemsta", "mnoznik_atak", "mnoznik_szans", "pewnosc", "n_h2h"):
            assert key in result
