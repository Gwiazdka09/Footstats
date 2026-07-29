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


def _parse_players_json(html: str) -> list[dict] | None:
    """Wyciąga playersData JSON (pełen skład ligi) z HTML Understat."""
    match = re.search(r"var\s+playersData\s*=\s*JSON\.parse\('(.+?)'\)", html)
    if not match:
        return None
    try:
        raw = match.group(1).encode("utf-8").decode("unicode_escape")
        return json.loads(raw)
    except (ValueError, KeyError) as e:
        _log.debug("Błąd parsowania playersData: %s", e)
        return None


def parse_understat_players(html: str) -> list[dict]:
    """
    Parsuje playersData → [{name, team, goals, assists, minutes, xg}].
    Pomija wpisy bez nazwiska/drużyny. Gole/asysty/minuty None → 0.
    """
    data = _parse_players_json(html)
    if not data:
        return []
    return _mapuj_graczy(data)


def _mapuj_graczy(data: list[dict]) -> list[dict]:
    """Surowe playersData → schemat projektu. Wspólne dla HTML i odczytu z `window`."""
    out: list[dict] = []
    for p in data:
        name = (p.get("player_name") or "").strip()
        team = (p.get("team_title") or "").strip()
        if not name or not team:
            continue

        def _i(v: object) -> int:
            try:
                return int(float(v)) if v not in (None, "") else 0
            except (ValueError, TypeError):
                return 0

        def _f(v: object) -> float | None:
            try:
                return round(float(v), 2) if v not in (None, "") else None
            except (ValueError, TypeError):
                return None

        out.append({
            "name": name,
            "team": team,
            "goals": _i(p.get("goals")),
            "assists": _i(p.get("assists")),
            "minutes": _i(p.get("time")),
            "xg": _f(p.get("xG")),
        })
    return out


def _parsuj_liczbe(txt: str) -> float | None:
    """
    Pierwsza liczba z komórki tabeli Understat. None gdy jej nie ma.

    Kolumny xG/xGA niosą deltę wobec goli sklejoną z wartością ("77.49+6.49"),
    więc `float()` na całości by poległo, a naiwny split po '+' zgubiłby '-'.
    """
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(txt or ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def fetch_league_team_xg(league_key: str, season: int) -> dict[str, dict]:
    """
    xG/xGA wszystkich drużyn ligi — JEDNO pobranie przeglądarką.

    Understat porzucił zmienne JS (`matchesData`/`playersData` nie ma ani w HTML,
    ani w `window`); dane są w tabelach DOM budowanych po stronie klienta. Tabela
    ligi ma komplet (Team / M / xG / xGA), więc jeden fetch obsługuje ~20 drużyn
    zamiast 20 osobnych uruchomień chromium.

    Zapisuje wynik do tego samego cache, z którego czyta `poisson.predict_match`
    (`_cache_get(_to_slug(team), season)`), więc blend 20% xG rusza bez zmian w modelu.

    UWAGA na semantykę: to średnia **sezonowa** (xG/M), a nie z ostatnich N meczów
    jak w `fetch_team_xg`. Jest gładsza i mniej czuła na formę — świadomy kompromis
    za to, że w ogóle mamy xG (wcześniej cache był pusty, blend był cichym no-opem).

    Zwraca {nazwa_druzyny: payload}. Brak przeglądarki/danych → {}.
    """
    from footstats.scrapers.browser_fetch import pobierz_html

    url = f"https://understat.com/league/{league_key}/{season}"
    _log.info("[Understat] tabela ligi %s/%d", league_key, season)
    html = pobierz_html(url, czekaj_na="table")
    if not html:
        return {}

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
    except ImportError:
        _log.warning("[Understat] brak bs4 — pomijam tabelę ligi")
        return {}

    wynik: dict[str, dict] = {}
    for tabela in soup.find_all("table"):
        naglowki = [th.get_text(strip=True) for th in tabela.find_all("th")]
        if not {"Team", "xG", "xGA"}.issubset(set(naglowki)):
            continue  # kalendarze i inne tabele na stronie
        try:
            i_team, i_m = naglowki.index("Team"), naglowki.index("M")
            i_xg, i_xga = naglowki.index("xG"), naglowki.index("xGA")
        except ValueError:
            continue

        for wiersz in tabela.find_all("tr")[1:]:
            komorki = [c.get_text(strip=True) for c in wiersz.find_all(["td", "th"])]
            if len(komorki) <= max(i_team, i_m, i_xg, i_xga):
                continue
            team = komorki[i_team].strip()
            mecze = _parsuj_liczbe(komorki[i_m])
            xg = _parsuj_liczbe(komorki[i_xg])
            xga = _parsuj_liczbe(komorki[i_xga])
            # Niepełny wiersz jest bezużyteczny — pomijamy zamiast zgadywać.
            if not team or not mecze or mecze <= 0 or xg is None or xga is None:
                continue

            payload = {
                "team": team,
                "season": season,
                "mecze": int(mecze),
                "xg_for_avg": round(xg / mecze, 2),
                "xga_avg": round(xga / mecze, 2),
                "historia": [],  # tabela ligi nie ma rozbicia na mecze
                "zrodlo": "understat-liga",
            }
            _cache_set(_to_slug(team), season, payload)
            wynik[team] = payload
        break  # pierwsza tabela z kompletem kolumn wystarczy

    _log.info("[Understat] tabela ligi %s: %d drużyn", league_key, len(wynik))
    return wynik


# Klucze lig Understat (URL) — pokrywa TOP5 + rosyjska. MLS/Saudi/LigaMX poza zasięgiem.
UNDERSTAT_LIGI: dict[str, str] = {
    "PL": "EPL",
    "PD": "La_liga",
    "SA": "Serie_A",
    "BL1": "Bundesliga",
    "FL1": "Ligue_1",
}


def fetch_league_players_understat(league_key: str, season: int) -> list[dict]:
    """
    Parsuje pełen skład ligi z Understat (per-gracz gole/asysty/xG).
    league_key: URL Understat (np. 'EPL','La_liga'). Zwraca [] gdy brak/HTTP błąd.

    Od ~2026 Understat NIE osadza już `playersData` w HTML dla prostych klientów
    (zwraca ~18KB shell) — dane wstrzykuje JS. Gdy plain-HTTP nic nie znajdzie,
    schodzimy na przeglądarkę (`browser_fetch`, chromium jest w obrazie jobs).
    """
    url = f"https://understat.com/league/{league_key}/{season}"
    _log.info("[Understat] GET %s", url)
    try:
        time.sleep(1.0)  # grzeczny scraper
        resp = _SESSION.get(url, timeout=20)
        if resp.status_code == 200:
            gracze = parse_understat_players(resp.text)
            if gracze:
                return gracze
        else:
            _log.warning("[Understat] HTTP %d dla %s", resp.status_code, url)
    except (requests.RequestException, ValueError, KeyError) as e:
        _log.error("[Understat] Błąd HTTP: %s", e)

    return _gracze_przez_przegladarke(url)


def _gracze_przez_przegladarke(url: str) -> list[dict]:
    """Fallback: odczyt `window.playersData` z wyrenderowanej strony. [] gdy brak."""
    from footstats.scrapers.browser_fetch import pobierz_zmienne_js

    _log.info("[Understat] plain-HTTP bez playersData → przeglądarka: %s", url)
    zmienne = pobierz_zmienne_js(url, ["playersData"])
    surowe = zmienne.get("playersData")
    if not surowe:
        return []
    return _mapuj_graczy(surowe)


def _matches_przez_przegladarke(url: str) -> list[dict] | None:
    """Fallback: odczyt `window.matchesData` z wyrenderowanej strony. None gdy brak."""
    from footstats.scrapers.browser_fetch import pobierz_zmienne_js

    _log.info("[Understat] plain-HTTP bez matchesData → przeglądarka: %s", url)
    zmienne = pobierz_zmienne_js(url, ["matchesData"])
    surowe = zmienne.get("matchesData")
    return surowe if surowe else None


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

    matches: list[dict] | None = None
    try:
        time.sleep(1.0)  # grzeczny scraper
        resp = _SESSION.get(url, timeout=15)
        if resp.status_code == 200:
            matches = _parse_matches_json(resp.text)
        else:
            _log.warning("[Understat] HTTP %d dla %s", resp.status_code, url)
    except (requests.RequestException, ValueError, KeyError) as e:
        _log.error("[Understat] Błąd HTTP: %s", e)

    # Od ~2026 strona nie embeduje `matchesData` w HTML (JS wstrzykuje je w window).
    # Bez tego fallbacku cały xG był martwy, a blend 20% w predict_match nigdy nie grał.
    if matches is None:
        matches = _matches_przez_przegladarke(url)

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
