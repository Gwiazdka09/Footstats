"""Analizy meczowe — statystyki drużyn dla wszystkich użytkowników.

GET /api/analyses/matches → karty ważnych meczów (top-5+WC+Euro+EKS): gole/mecz
                            (team_stats), strzelcy (goal_share), kontuzje.

Od 10.09.2026 BEZ predykcji: karta nie niesie prawdopodobieństw 1X2/Over/BTTS
ani kursów, a analiza LLM (`POST /analyses/llm`) jest usunięta. Decyzja usera:
nasze typy nie pokazują się w GUI poza kreatorem „Stwórz Kupon” — ta zakładka
to dane o drużynach, nie prognoza.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from footstats.api.auth import require_auth
from footstats.core import opis_meczu
from footstats.core.czas_meczu import juz_sie_zaczal, moment_meczu
from footstats.core.match_analysis import build_match_card
from footstats.core.player_db import team_goal_shares_recent, get_team_stats
from footstats.utils.normalize import _norm_ascii

router = APIRouter(prefix="/api", tags=["analyses"])
log = logging.getLogger(__name__)

# Ważne ligi (substring nazwy): top-5 + Mistrzostwa Świata + Euro + Ekstraklasa
_WAZNE = (
    "premier league", "la liga", "primera division", "serie a", "bundesliga",
    "ligue 1", "world cup", "mistrzostwa", "euro 20", "euro 2028", "european championship",
    "ekstraklasa", "pko bp",
)
_SEASON = 2026
# Maks. liczba wyników wyszukiwania: każda karta = 4 zapytania do DB,
# a middleware ma timeout, więc szeroki `q` nie może budować setek kart.
_MAX_WYNIKOW_SZUKANIA = 20
_MIN_DLUGOSC_ZAPYTANIA = 2


def _wazna(liga: str | None) -> bool:
    return any(w in (liga or "").lower() for w in _WAZNE)


def _na_dzis_i_jutro(events: list[dict], dzis: date) -> list[dict]:
    """Pure: zostawia mecze z dziś i jutra, posortowane po dacie i godzinie.

    Od 2026-10-25 `predykcje_tygodnia()` pobiera wszystkie strony (609 zamiast 50),
    czyli ~100 meczów ważnych lig na 7 dni. Każda karta to 4 zapytania do DB,
    a middleware ma timeout 10 s — dlatego endpoint pokazuje tylko dziś i jutro.
    """
    dozwolone = {dzis.isoformat(), (dzis + timedelta(days=1)).isoformat()}
    wybrane = [m for m in events if m.get("data") in dozwolone]
    return sorted(wybrane, key=lambda m: (m.get("data") or "", m.get("godzina") or ""))


def _bez_rozpoczetych(events: list[dict], teraz: datetime) -> list[dict]:
    """Pure: odrzuca mecze trwające, zakończone, odwołane lub już rozpoczęte."""
    return [m for m in events if not juz_sie_zaczal(m, teraz)]


def _szukaj(events: list[dict], q: str, limit: int = _MAX_WYNIKOW_SZUKANIA) -> list[dict]:
    """Pure: mecze z `q` w gospodarzu, gościu lub lidze (bez wielkości liter i diakrytyków).

    Szuka w całym tygodniu i we wszystkich ligach; wynik posortowany po
    momencie meczu i obcięty do `limit`.
    """
    szukane = _norm_ascii(q)
    if not szukane:
        return []
    trafione = [
        m for m in events
        if any(szukane in _norm_ascii(m.get(k) or "") for k in ("gosp", "gosc", "liga"))
    ]
    koniec = datetime.max.replace(tzinfo=timezone.utc)
    trafione.sort(key=lambda m: moment_meczu(m) or koniec)
    return trafione[:limit]


def _zbior():
    """Zbiór historyczny z `admin_opisy` (jeden leniwy cache). Import lokalny:
    admin_opisy importuje `_SEASON` stąd, więc na górze byłby cykl."""
    from footstats.api.routes.admin_opisy import _zbior as zbior_admina
    return zbior_admina()


_STREFA_PL = ZoneInfo("Europe/Warsaw")


def _start_warszawa(m: dict) -> tuple[str | None, str | None]:
    """Pure: (data, godzina) startu w Europe/Warsaw albo (None, None).

    Bzzoiro `godzina` to wycinek UTC; `moment_meczu` daje moment ze strefą, tu
    tylko konwersja (uwzględnia CET/CEST). Bez godziny nie zgadujemy.
    """
    if not (m.get("godzina") or m.get("data_full")):
        return None, None
    moment = moment_meczu(m)
    if moment is None:
        return None, None
    lokalny = moment.astimezone(_STREFA_PL)
    return lokalny.strftime("%Y-%m-%d"), lokalny.strftime("%H:%M")


def _blok_z_historii(blok: dict, druzyna: str) -> dict:
    """Nowy blok statystyk z gf/ga policzonymi z ostatnich meczów zbioru historycznego.

    `team_stats` zawiera tylko 48 reprezentacji (WC 2026) — dla klubów jest puste,
    więc średnie goli liczymy z `data/hist_cache/full_dataset.parquet` (ostatnie 10
    meczów, jak w opisie meczu). Brak drużyny w zbiorze = blok bez zmian (bez zmyślania).
    """
    if blok.get("gf_pg") is not None:
        return blok
    f = opis_meczu.forma(_zbior(), druzyna)
    if not f:
        return blok
    return {**blok, "matches": f["mecze_w_sredniej"],
            "gf_pg": f["gole_strzelone_sr10"], "ga_pg": f["gole_stracone_sr10"]}


def _build_cards(events: list[dict], tylko_wazne: bool = True) -> list[dict]:
    """Pure: z eventów Bzzoiro buduje karty ważnych meczów + team_stats/goal_share.

    `pred_ml` i `odds` z eventu są celowo POMIJANE — karta to statystyki drużyn.
    """
    cards = []
    for m in events:
        if tylko_wazne and not _wazna(m.get("liga")):
            continue
        home, away = m.get("gosp"), m.get("gosc")
        if not home or not away:
            # Zdarzenie bez nazw druzyn szlo do `get_team_stats(None, ...)`.
            # Karta meczu bez nazw i tak jest bezuzyteczna — pomijamy, ale
            # GLOSNO: cisza tutaj chowalaby uszkodzone zrodlo zdarzen.
            log.warning("Zdarzenie bez nazw druzyn (gosp=%r, gosc=%r, liga=%r)"
                        " — pomijam karte meczu", home, away, m.get("liga"))
            continue
        match = {"gospodarz": home, "goscie": away, "liga": m.get("liga"), "data": m.get("data")}
        card = build_match_card(
            match,
            ts_home=get_team_stats(home, _SEASON), ts_away=get_team_stats(away, _SEASON),
            gs_home=team_goal_shares_recent(home, _SEASON), gs_away=team_goal_shares_recent(away, _SEASON),
            inj_home=m.get("injuries_home"), inj_away=m.get("injuries_away"),
        )
        # `build_match_card` zawsze dokłada blok `model` (używał go prompt LLM) —
        # tu go wycinamy, żeby w odpowiedzi nie jechały nawet puste pola predykcji.
        data_pl, godzina = _start_warszawa(m)
        card = {
            **{k: v for k, v in card.items() if k != "model"},
            "home_stats": _blok_z_historii(card["home_stats"], home),
            "away_stats": _blok_z_historii(card["away_stats"], away),
            "data_pl": data_pl, "godzina": godzina,
        }
        cards.append(card)
    return cards


@router.get("/analyses/matches")
def analyses_matches(
    user_id: int = Depends(require_auth),
    q: str | None = Query(None, max_length=50),
):
    """Karty meczów (dane, bez LLM). Źródło: Bzzoiro predykcje_tygodnia.

    Bez `q`: dziś i jutro, ważne ligi. Z `q` (≥2 znaki): cały tydzień, wszystkie
    ligi. Mecze rozpoczęte i zakończone są ukrywane zawsze.
    """
    try:
        from footstats.scrapers.bzzoiro import BzzoiroClient
        klucz = os.getenv("BZZOIRO_KEY", "").strip()
        if not klucz:
            return {"matches": [], "error": "brak BZZOIRO_KEY"}
        events = BzzoiroClient(klucz).predykcje_tygodnia() or []
    except (OSError, ValueError, KeyError) as e:
        log.warning("analyses_matches: %s", e)
        return {"matches": [], "error": str(e)}
    events = _bez_rozpoczetych(events, datetime.now(timezone.utc))
    zapytanie = (q or "").strip()
    if len(zapytanie) >= _MIN_DLUGOSC_ZAPYTANIA:
        return {"matches": _build_cards(_szukaj(events, zapytanie), tylko_wazne=False)}
    dzis = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    return {"matches": _build_cards(_na_dzis_i_jutro(events, dzis))}
