"""understat_xg.py — xG scraper z Understat.com (bezpłatny, bez klucza API).

Understat osadza dane meczowe jako JSON.parse(...) w tagu <script>.
Pobieramy ostatnie N meczów drużyny i liczymy średnie xG/xGA.

Użycie:
    from footstats.scrapers.understat_xg import fetch_team_xg
    dane = fetch_team_xg("Arsenal", season=2025)

    python -m footstats.scrapers.understat_xg Arsenal 2025
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import requests

_log = logging.getLogger(__name__)

_CACHE_DIR = Path("cache/understat_xg")
_CACHE_TTL_H = 6
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})
import atexit
atexit.register(_SESSION.close)

# Mapowanie polskich/angielskich nazw → slug Understat (spacje → podkreślnik)
_TEAM_SLUGS: dict[str, str] = {
    "Arsenal": "Arsenal",
    "Chelsea": "Chelsea",
    "Liverpool": "Liverpool",
    "Manchester City": "Manchester_City",
    "Manchester United": "Manchester_United",
    "Tottenham": "Tottenham",
    "Newcastle": "Newcastle_United",
    "Aston Villa": "Aston_Villa",
    "West Ham": "West_Ham",
    "Brighton": "Brighton",
    "Bayern": "Bayern_Munich",
    "Bayern Munich": "Bayern_Munich",
    "Dortmund": "Borussia_Dortmund",
    "Borussia Dortmund": "Borussia_Dortmund",
    "Leverkusen": "Bayer_Leverkusen",
    "RB Leipzig": "RasenBallsport_Leipzig",
    "Real Madrid": "Real_Madrid",
    "Barcelona": "FC_Barcelona",
    "Atletico": "Atletico_Madrid",
    "Atletico Madrid": "Atletico_Madrid",
    "Juventus": "Juventus",
    "Inter": "Internazionale",
    "Milan": "AC_Milan",
    "Napoli": "Napoli",
    "Roma": "AS_Roma",
    "PSG": "Paris_Saint_Germain",
    "Paris Saint-Germain": "Paris_Saint_Germain",
}


def _to_slug(team_name: str) -> str:
    """Normalizuje nazwę drużyny do formatu URL Understat."""
    if team_name in _TEAM_SLUGS:
        return _TEAM_SLUGS[team_name]
    # fallback: zamień spacje na podkreślniki
    return team_name.replace(" ", "_")


def _cache_path(team_slug: str, season: int) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{team_slug}_{season}.json"


def _cache_get(team_slug: str, season: int) -> dict | None:
    path = _cache_path(team_slug, season)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        saved_at = datetime.fromisoformat(data.get("_ts", "2000-01-01"))
        if (datetime.now() - saved_at).total_seconds() < _CACHE_TTL_H * 3600:
            return data.get("payload")
    except (OSError, ValueError) as e:
        _log.debug("Błąd odczytu cache Understat: %s", e)
    return None


def _cache_set(team_slug: str, season: int, payload: dict) -> None:
    try:
        _cache_path(team_slug, season).write_text(
            json.dumps({"_ts": datetime.now().isoformat(), "payload": payload},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        _log.debug("Błąd zapisu cache Understat: %s", e)


def _parse_matches_json(html: str) -> list[dict] | None:
    """Wyciąga matchesData JSON z HTML Understat."""
    # Understat: var matchesData = JSON.parse('...')
    match = re.search(r"var\s+matchesData\s*=\s*JSON\.parse\('(.+?)'\)", html)
    if not match:
        return None
    try:
        raw = match.group(1)
        # Understat używa unicode escapes i odwróconych ukośników
        raw = raw.encode("utf-8").decode("unicode_escape")
        return json.loads(raw)
    except (requests.RequestException, ValueError, KeyError) as e:
        _log.debug("Błąd parsowania matchesData: %s", e)
        return None


def fetch_team_xg(
    team_name: str,
    season: int | None = None,
    ostatnie_n: int = 10,
) -> dict | None:
    """
    Pobiera xG i xGA z ostatnich N meczów drużyny z Understat.com.

    Zwraca:
        {
            "team": str,
            "season": int,
            "mecze": int,
            "xg_for_avg": float,    # średnie xG strzelone
            "xga_avg": float,        # średnie xG stracone
            "historia": [{"date", "opponent", "xg_for", "xga", "wynik"}, ...]
        }
    """
    if season is None:
        now = datetime.now()
        season = now.year if now.month >= 7 else now.year - 1

    slug = _to_slug(team_name)
    cached = _cache_get(slug, season)
    if cached is not None:
        return cached

    url = f"https://understat.com/team/{slug}/{season}"
    _log.info("[Understat] GET %s", url)

    try:
        time.sleep(1.0)  # grzeczny scraper
        resp = _SESSION.get(url, timeout=15)
        if resp.status_code != 200:
            _log.warning("[Understat] HTTP %d dla %s", resp.status_code, url)
            return None
        html = resp.text
    except (requests.RequestException, ValueError, KeyError) as e:
        _log.error("[Understat] Błąd HTTP: %s", e)
        return None

    matches = _parse_matches_json(html)
    if matches is None:
        _log.warning("[Understat] Nie znaleziono matchesData dla %s/%d", slug, season)
        return None

    # Filtr: tylko zakończone mecze
    finished = [m for m in matches if m.get("isResult")]
    finished = sorted(finished, key=lambda m: m.get("datetime", ""), reverse=True)
    recent = finished[:ostatnie_n]

    if not recent:
        return None

    historia: list[dict] = []
    xg_for_vals: list[float] = []
    xga_vals: list[float] = []

    for m in recent:
        h_id = str(m.get("h", {}).get("id", ""))
        a_id = str(m.get("a", {}).get("id", ""))

        # Znajdź ID naszej drużyny
        # (Understat nie zwraca wprost ID szukanej drużyny w tym kontekście,
        #  więc sprawdzamy tytuły)
        h_title = m.get("h", {}).get("title", "")
        a_title = m.get("a", {}).get("title", "")

        is_home = slug.replace("_", " ").lower() in h_title.lower() or h_title.lower() in team_name.lower()

        xg_data = m.get("xG", {})
        goals_data = m.get("goals", {})

        if is_home:
            xgf = xg_data.get("h")
            xga = xg_data.get("a")
            gh  = goals_data.get("h", "?")
            ga  = goals_data.get("a", "?")
            opp = a_title
        else:
            xgf = xg_data.get("a")
            xga = xg_data.get("h")
            gh  = goals_data.get("a", "?")
            ga  = goals_data.get("h", "?")
            opp = h_title

        try:
            xgf_f = float(xgf) if xgf is not None else None
            xga_f = float(xga) if xga is not None else None
        except (ValueError, TypeError):
            xgf_f = xga_f = None

        wpis = {
            "date":     str(m.get("datetime", ""))[:10],
            "opponent": opp,
            "xg_for":   round(xgf_f, 2) if xgf_f is not None else None,
            "xga":      round(xga_f, 2) if xga_f is not None else None,
            "wynik":    f"{gh}-{ga}",
        }
        historia.append(wpis)

        if xgf_f is not None:
            xg_for_vals.append(xgf_f)
        if xga_f is not None:
            xga_vals.append(xga_f)

    wynik = {
        "team":        team_name,
        "season":      season,
        "mecze":       len(historia),
        "xg_for_avg":  round(sum(xg_for_vals) / len(xg_for_vals), 2) if xg_for_vals else None,
        "xga_avg":     round(sum(xga_vals) / len(xga_vals), 2) if xga_vals else None,
        "historia":    historia,
    }
    _cache_set(slug, season, wynik)
    return wynik


if __name__ == "__main__":
    import sys
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    team = sys.argv[1] if len(sys.argv) > 1 else "Arsenal"
    year = int(sys.argv[2]) if len(sys.argv) > 2 else None
    n    = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    dane = fetch_team_xg(team, year, n)
    if dane:
        print(f"\n{dane['team']} {dane['season']} — {dane['mecze']} meczów")
        print(f"  xG for avg : {dane['xg_for_avg']}")
        print(f"  xGA avg    : {dane['xga_avg']}")
        for m in dane["historia"]:
            print(f"  {m['date']} vs {m['opponent']:20s} | xG: {m['xg_for']} | xGA: {m['xga']} | {m['wynik']}")
    else:
        print("Brak danych.")
