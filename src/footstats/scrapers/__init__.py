"""Footstats scrapers package."""
from footstats.scrapers.football_data import APIClient
from footstats.scrapers.api_football import APIFootball
from footstats.scrapers.bzzoiro import BzzoiroClient
from footstats.scrapers.source_manager import SourceManager
from footstats.scrapers.enriched import enrich_match_data
from footstats.scrapers.form_scraper import pobierz_forme, pobierz_forme_meczu
try:
    from footstats.scrapers.superbet_bb import pobierz_bb_dla_meczow
except ImportError:
    pobierz_bb_dla_meczow = None  # type: ignore[assignment]

__all__ = [
    "APIClient",
    "APIFootball",
    "BzzoiroClient",
    "SourceManager",
    "enrich_match_data",
    "pobierz_forme",
    "pobierz_forme_meczu",
    "pobierz_bb_dla_meczow",
]
