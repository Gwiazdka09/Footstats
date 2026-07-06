"""
match_analysis.py — rdzeń zakładki "Analizy meczowe" (Sofascore-style).

Agreguje kartę meczu z danych które już mamy: gole/mecz + rating (team_stats),
kontuzje z wpływem (goal_share z player_db), model 1X2/O-U/BTTS, gospodarz/venue.
Buduje prompt dla LLM (gpt-oss, rola: ANALIZA nie pick) + data-hash do cache
(regen analizy tylko gdy dane się zmienią — nie na każdy request użytkownika).

Pure/testowalne — źródła (Bzzoiro/form_scraper/lineup) podpina endpoint.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from footstats.config import DB_PATH

_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS analysis_cache (
    data_hash  TEXT PRIMARY KEY,
    analysis   TEXT,
    updated_at TEXT
)
"""


def _top_scorers(gs: dict | None, n: int = 3) -> list[dict]:
    """Top strzelcy drużyny wg goal_share ({name, goal_share})."""
    if not gs:
        return []
    top = sorted(gs.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [{"name": nm, "goal_share": round(s, 3)} for nm, s in top]


def _team_block(ts: dict | None, name: str) -> dict:
    if not ts:
        return {"team": name, "matches": None, "gf_pg": None, "ga_pg": None,
                "rating": None, "clean_sheets": None}
    m = int(ts.get("matches") or 0)
    return {
        "team": name,
        "matches": m,
        "gf_pg": round(ts.get("goals_for", 0) / m, 2) if m else None,
        "ga_pg": round(ts.get("goals_against", 0) / m, 2) if m else None,
        "rating": ts.get("avg_rating"),
        "clean_sheets": ts.get("clean_sheets"),
    }


def _inj_block(injs: list | None, gs: dict | None) -> list[dict]:
    out = []
    for i in injs or []:
        name = (i.get("name") or i.get("nazwa") or "").strip()
        if not name:
            continue
        share = (gs or {}).get(name)
        out.append({
            "name": name,
            "position": i.get("position") or i.get("pozycja"),
            "goal_share": round(share, 3) if share else None,
            "reason": i.get("reason") or i.get("powod"),
        })
    return out


def build_match_card(
    match: dict,
    ts_home: dict | None = None,
    ts_away: dict | None = None,
    gs_home: dict | None = None,
    gs_away: dict | None = None,
    inj_home: list | None = None,
    inj_away: list | None = None,
    lineups: dict | None = None,
) -> dict:
    """
    Składa kartę analizy meczu. match: {gospodarz, goscie, liga, data, pw,pr,pp,o25,bt}.
    ts_*: wiersz team_stats. gs_*: goal_shares. inj_*: lista kontuzji. lineups: startXI.
    """
    return {
        "home": match.get("gospodarz"),
        "away": match.get("goscie"),
        "liga": match.get("liga"),
        "data": match.get("data"),
        "host": match.get("gospodarz"),          # gospodarz = venue/host
        "model": {k: match.get(k) for k in ("pw", "pr", "pp", "o25", "bt")},
        "home_stats": _team_block(ts_home, match.get("gospodarz")),
        "away_stats": _team_block(ts_away, match.get("goscie")),
        "injuries_home": _inj_block(inj_home, gs_home),
        "injuries_away": _inj_block(inj_away, gs_away),
        "top_scorers_home": _top_scorers(gs_home),
        "top_scorers_away": _top_scorers(gs_away),
        "lineups": lineups or None,
    }


def analysis_prompt(card: dict) -> str:
    """Prompt dla LLM (rola: ZWIĘZŁA analiza, NIE wybór typu — model już wybrał)."""
    hs, as_ = card["home_stats"], card["away_stats"]
    m = card["model"]

    def inj_txt(injs):
        if not injs:
            return "brak istotnych"
        return ", ".join(
            f"{i['name']}" + (f" ({i['goal_share']*100:.0f}% goli)" if i.get("goal_share") else "")
            for i in injs
        )

    def scorers_txt(ts):
        if not ts:
            return "brak danych"
        return ", ".join(f"{s['name']} ({s['goal_share']*100:.0f}%)" for s in ts)

    return (
        f"Przeanalizuj mecz. Model statystyczny już podał typy — Twoja rola to ZWIĘZŁA "
        f"analiza (kluczowe czynniki + ryzyko), NIE wybierasz typu.\n\n"
        f"MECZ: {card['home']} vs {card['away']} ({card['liga']}, {card['data']})\n"
        f"Gospodarz: {card['host']}\n"
        f"Gole/mecz — {card['home']}: {hs['gf_pg']} strzelone / {hs['ga_pg']} stracone "
        f"(rating {hs['rating']}); {card['away']}: {as_['gf_pg']} / {as_['ga_pg']} "
        f"(rating {as_['rating']})\n"
        f"Top strzelcy {card['home']}: {scorers_txt(card.get('top_scorers_home'))}; "
        f"{card['away']}: {scorers_txt(card.get('top_scorers_away'))}\n"
        f"Model: 1={m['pw']}% X={m['pr']}% 2={m['pp']}% | Over2.5={m['o25']}% | BTTS={m['bt']}%\n"
        f"Kontuzje {card['home']}: {inj_txt(card['injuries_home'])}\n"
        f"Kontuzje {card['away']}: {inj_txt(card['injuries_away'])}\n\n"
        f"Max 100 słów: 3 kluczowe czynniki + główne ryzyko + krótki werdykt na gole."
    )


def card_data_hash(card: dict) -> str:
    """
    Hash danych karty (bez pól ulotnych) → klucz cache. Ten sam stan danych = ten sam
    hash (zwróć cache); zmiana (nowe kontuzje/składy/model) = inny hash (regeneruj).
    """
    payload = {
        "home": card["home"], "away": card["away"], "data": card["data"],
        "model": card["model"], "home_stats": card["home_stats"],
        "away_stats": card["away_stats"],
        "injuries_home": card["injuries_home"], "injuries_away": card["injuries_away"],
        "lineups": card.get("lineups"),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── Cache analiz LLM (persistent SQLite) — raz generujesz, regen tylko na nowy hash ──

def get_cached_analysis(data_hash: str, db_path: Path | str = DB_PATH) -> str | None:
    """Zwraca zapisaną analizę dla data-hash lub None."""
    try:
        con = sqlite3.connect(str(db_path))
        con.execute(_CACHE_DDL)
        row = con.execute(
            "SELECT analysis FROM analysis_cache WHERE data_hash = ?", (data_hash,)
        ).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def set_cached_analysis(data_hash: str, text: str, db_path: Path | str = DB_PATH) -> None:
    """Zapisuje analizę pod data-hash (upsert)."""
    try:
        con = sqlite3.connect(str(db_path))
        con.execute(_CACHE_DDL)
        con.execute(
            "INSERT INTO analysis_cache (data_hash, analysis, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(data_hash) DO UPDATE SET analysis=excluded.analysis, updated_at=excluded.updated_at",
            (data_hash, text, datetime.now().isoformat()),
        )
        con.commit()
        con.close()
    except sqlite3.Error:
        pass
