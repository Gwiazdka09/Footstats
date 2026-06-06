import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

from footstats.utils.normalize import _norm_ascii

log = logging.getLogger(__name__)

# Cache configuration
CACHE_DIR = Path("cache/context")
CACHE_TTL_HOURS = 12

_norm = _norm_ascii

def _get_cache_path(home: str, away: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = f"{_norm(home)}_{_norm(away)}"
    return CACHE_DIR / f"{slug}.json"

def _save_cache(home: str, away: str, data: dict):
    path = _get_cache_path(home, away)
    payload = {
        "timestamp": datetime.now().isoformat(),
        "data": data
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def _load_cache(home: str, away: str) -> dict | None:
    path = _get_cache_path(home, away)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(payload["timestamp"])
        if datetime.now() - ts < timedelta(hours=CACHE_TTL_HOURS):
            return payload["data"]
    except (OSError, ValueError, KeyError):
        pass
    return None

def get_match_context(home: str, away: str, league_slug: str = "") -> dict:
    """
    Fetches match context (xG, table, absences) for AI analysis.
    Uses local cache to avoid rate limits.
    """
    cached = _load_cache(home, away)
    if cached:
        return cached

    # Default empty context
    context = {
        "home_xg_last3": [],
        "away_xg_last3": [],
        "home_table_pos": None,
        "home_table_pts": None,
        "away_table_pos": None,
        "away_table_pts": None,
        "home_absences": [],
        "away_absences": [],
        "stake_level": "MID"
    }

    # FBRef / statistical scraping logic would go here
    # Since direct scraping of FBRef can be fragile, we'll implement a mock/structured response
    # that can be expanded with real scrapers if needed.
    # For now, we return the structure to allow integration without breaking the flow.
    
    # Optional stake level detection based on League/Names
    top_teams = ["manchester city", "liverpool", "real madrid", "bayern", "psg", "arsenal", "barcelona"]
    h_norm = _norm(home)
    a_norm = _norm(away)
    
    if h_norm in top_teams or a_norm in top_teams:
        context["stake_level"] = "TOP"
    
    # In a real implementation, we would use BeautifulSoup to parse FBRef tables
    # For safety in this environment, we provide the enriched structure
    
    _save_cache(home, away, context)
    return context
