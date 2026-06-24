"""Testy Źródła 5 settlementu — fallback aggregator.consensus_result.

_find_leg_result próbuje kolejno: AF /fixtures + football-data.org (1-2),
FlashScore cache (3), tabela predictions w DB (4), a na końcu konsensus
multi-source (5: football-data.co.uk CSV + cross-walidowany FlashScore).
"""
from unittest.mock import MagicMock

from footstats.core import coupon_settlement


def _puste_zrodla_1_4(monkeypatch):
    """Zeruje źródła 1-4: FlashScore None + DB pusty. Caller pre-seeduje cache AF/fdb."""
    monkeypatch.setattr(
        "footstats.scrapers.flashscore_results.get_match_result",
        lambda *a, **k: None,
    )
    fake_conn = MagicMock()
    fake_conn.__enter__.return_value.execute.return_value.fetchone.return_value = None
    monkeypatch.setattr("footstats.core.backtest._connect", lambda: fake_conn)


def test_consensus_fallback_dostarcza_wynik(monkeypatch):
    """Gdy źródła 1-4 puste, a konsensus ma wynik → _find_leg_result go zwraca."""
    _puste_zrodla_1_4(monkeypatch)
    monkeypatch.setattr(
        "footstats.scrapers.sources.aggregator.consensus_result",
        lambda home, away, date: "2-1;HT:1-0",
    )

    # cache AF/fdb pre-seedowane na [] dla obu kandydujących dat → brak realnych fetchy
    fixtures_cache = {"2026-01-01": [], "2026-01-02": []}
    fdb_cache = {"2026-01-01": [], "2026-01-02": []}

    wynik = coupon_settlement._find_leg_result(
        "Barcelona", "Real Madrid", "2026-01-01",
        fixtures_cache, fdb_cache, api_key="", fdb_key="",
    )
    assert wynik == "2-1;HT:1-0"


def test_consensus_brak_wyniku_zwraca_none(monkeypatch):
    """Gdy źródła 1-4 puste i konsensus nic nie ma → None (nie wybucha)."""
    _puste_zrodla_1_4(monkeypatch)
    monkeypatch.setattr(
        "footstats.scrapers.sources.aggregator.consensus_result",
        lambda home, away, date: None,
    )

    fixtures_cache = {"2026-01-01": [], "2026-01-02": []}
    fdb_cache = {"2026-01-01": [], "2026-01-02": []}

    wynik = coupon_settlement._find_leg_result(
        "Nieznany", "Klub", "2026-01-01",
        fixtures_cache, fdb_cache, api_key="", fdb_key="",
    )
    assert wynik is None


def test_consensus_blad_jest_polykany(monkeypatch):
    """Wyjątek w konsensusie nie wywala settlementu — zwraca None."""
    _puste_zrodla_1_4(monkeypatch)

    def _wybuch(*a, **k):
        raise RuntimeError("źródło padło")

    monkeypatch.setattr(
        "footstats.scrapers.sources.aggregator.consensus_result", _wybuch
    )

    fixtures_cache = {"2026-01-01": [], "2026-01-02": []}
    fdb_cache = {"2026-01-01": [], "2026-01-02": []}

    wynik = coupon_settlement._find_leg_result(
        "Team A", "Team B", "2026-01-01",
        fixtures_cache, fdb_cache, api_key="", fdb_key="",
    )
    assert wynik is None
