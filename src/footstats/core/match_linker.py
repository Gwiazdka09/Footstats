"""
match_linker.py — Dopasowanie wolnego wpisu (home, away, date) do rekordu w
tabeli predictions (dziennik kuponów, Etap A planu J6/J4c).

Algorytm KONSERWATYWNY (precyzja > recall — false-negative bezpieczniejszy niż
false-positive, user oznaczy ręcznie brak dopasowania):
  - Ścisła normalizacja nazw drużyn przez `_norm_ascii` (NFKD → ascii, lowercase,
    alfanumeryczne — BEZ zdejmowania prefiksów/sufiksów i BEZ mappingów).
    `normalize_team_name` NIE jest tu używane — jego mappingi (team_mappings.json)
    kolidują pod recall (np. "Manchester City" i "Manchester United" mogą
    wylądować na tym samym skrócie), co dałoby false-positive w rozliczeniu.
  - Ta sama orientacja: home==home, away==away — swap traktowany jako brak
    dopasowania (odwróciłby znaczenie tipu 1/2).
  - Okno dat [date-tol, date+tol] (domyślnie ±1 dzień), porównanie po
    substr(match_date, 1, 10).
  - Redukcja do unikalnych meczów: 0 → "none", ≥2 różne mecze → "ambiguous",
    dokładnie 1 (możliwe wiele wierszy-tipów) → "exact" (bierzemy wiersz
    z max ai_confidence).

Read-only: wyłącznie SELECT z `predictions` i `model_log`, zero zapisów, zero
zewnętrznych API.

Dwie tabele, bo `predictions` jest z nich WĘŻSZA: zapisuje tylko ścieżkę
`top3`/`kupon_d`, podczas gdy `model_log` (dziennik kalibracyjny) dostaje każdy
oceniony mecz. Na produkcji 2026-08-28: 161 wierszy vs 424. Kupon dziennika
z meczem spoza `predictions` wisiał ACTIVE mimo że wynik leżał w naszej bazie.
Sygnał dla użytkownika (`preview_signal`) dalej idzie WYŁĄCZNIE z `predictions`
— `model_log` nie ma `ai_tip` ani `ai_confidence`, więc `wynik_z_model_log`
zwraca sam wynik meczu i służy tylko rozliczaniu.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date as _date
from datetime import timedelta

import psycopg2

from footstats.utils.betting import powod_nierozliczalny
from footstats.utils.db import connect
from footstats.utils.normalize import _norm_ascii

log = logging.getLogger(__name__)

# `model_log` to źródło POMOCNICZE — jego awaria nie może wywrócić rozliczania,
# bo nierozliczony kupon zostaje ACTIVE i człowiek go domknie. Stare bazy
# (i świeże SQLite w testach) tej tabeli po prostu nie mają.
#
# `RuntimeError` jest w tuplu celowo, ta sama lista co `kalibracja_log._AWARIE_BAZY`:
# pula połączeń (`utils/db._get_pool`) zgłasza brak `DATABASE_URL` właśnie nim,
# a nie wyjątkiem sterownika. Bez tego samo pytanie o źródło pomocnicze
# wywracałoby rozliczanie w każdym środowisku bez skonfigurowanej bazy.
_AWARIE_BAZY = (sqlite3.Error, psycopg2.Error, RuntimeError, OSError)


@dataclass(frozen=True)
class LinkResult:
    """Wynik próby dopasowania jednej nogi kuponu do predykcji w DB."""

    matched: bool
    match_confidence: str  # "exact" | "none" | "ambiguous"
    prediction: dict | None
    reason: str


def _date_window(center: str, day_tolerance: int) -> list[str]:
    """Buduje listę dat (YYYY-MM-DD) w oknie [center-tol, center+tol]."""
    center_date = _date.fromisoformat(center[:10])
    return [
        (center_date + timedelta(days=offset)).isoformat()
        for offset in range(-day_tolerance, day_tolerance + 1)
    ]


def _row_to_prediction(row) -> dict:
    """Mapuje wiersz DB na dict zgodny z kontraktem `prediction`."""
    return {
        "id": row["id"],
        "team_home": row["team_home"],
        "team_away": row["team_away"],
        "match_date": row["match_date"],
        "ai_tip": row["ai_tip"],
        "ai_confidence": row["ai_confidence"],
        "prob_home": row["prob_home"],
        "prob_draw": row["prob_draw"],
        "prob_away": row["prob_away"],
        "actual_result": row["actual_result"],
    }


def link_leg(
    home: str, away: str, date: str | None, day_tolerance: int = 1
) -> LinkResult:
    """
    Próbuje dopasować wolny wpis (home, away, date) do meczu w predictions.

    Args:
        home: Nazwa gospodarza (free-form, wpisana ręcznie przez użytkownika).
        away: Nazwa gościa (free-form).
        date: Data meczu (YYYY-MM-DD) lub None.
        day_tolerance: Tolerancja okna dat w dniach (domyślnie ±1).

    Returns:
        LinkResult z flagą `matched`, poziomem pewności i (opcjonalnie) predykcją.

    Uwaga (v1, świadome ograniczenie): STRICT `_norm_ascii` nie dekomponuje
    polskiego „ł” (np. „Łódź” → „odz”, litera znika zamiast zamienić się na
    „l”), co może dać false-negative dla nazw z tą literą — bezpieczniejsze niż
    false-positive, user oznaczy dopasowanie ręcznie.
    """
    if not home or not away or not date:
        return LinkResult(False, "none", None, "Brak nazw drużyn lub daty meczu")

    norm_home = _norm_ascii(home)
    norm_away = _norm_ascii(away)
    if not norm_home or not norm_away:
        return LinkResult(False, "none", None, "Nazwa drużyny pusta po normalizacji")

    try:
        window = _date_window(date, day_tolerance)
    except ValueError:
        return LinkResult(False, "none", None, f"Niepoprawny format daty: {date!r}")

    placeholders = ",".join("?" for _ in window)
    with connect() as conn:
        # Bezpieczne: f-string wstawia WYŁĄCZNIE `placeholders`, czyli ciąg znaków "?"
        # wygenerowany z długości `window`. Żadna wartość od użytkownika nie trafia do
        # SQL-a: daty idą osobno przez sparametryzowane `tuple(window)`.
        rows = conn.execute(
            f"""SELECT id, team_home, team_away, match_date, ai_tip,
                       ai_confidence, prob_home, prob_draw, prob_away, actual_result
                FROM predictions
                WHERE substr(match_date, 1, 10) IN ({placeholders})""",  # nosec B608
            tuple(window),
        ).fetchall()

    rows_for_match, pewnosc = _unikalny_mecz(rows, norm_home, norm_away)
    if pewnosc == "none":
        return LinkResult(False, "none", None, "Brak dopasowania w oknie dat")
    if pewnosc == "ambiguous":
        return LinkResult(False, "ambiguous", None, "Więcej niż jeden mecz pasuje w oknie dat")

    best_row = max(rows_for_match, key=lambda r: r["ai_confidence"])
    return LinkResult(True, "exact", _row_to_prediction(best_row), "Dopasowano jednoznacznie")


def _unikalny_mecz(rows: list, norm_home: str, norm_away: str) -> tuple[list, str]:
    """Redukuje wiersze z okna dat do JEDNEGO meczu.

    Ta sama orientacja (home==home, away==away) i ta sama redukcja po dacie, co
    w `link_leg` — wiele wierszy tego samego meczu (różne tipy, kolejne przebiegi
    potoku) trafia do jednej grupy, dwa różne mecze dają "ambiguous".

    Returns:
        (wiersze_jednego_meczu, "exact") albo ([], "none"/"ambiguous").
    """
    candidates = [
        row for row in rows
        if _norm_ascii(row["team_home"]) == norm_home
        and _norm_ascii(row["team_away"]) == norm_away
    ]
    if not candidates:
        return [], "none"

    unique_matches: dict[str, list] = {}
    for row in candidates:
        unique_matches.setdefault(str(row["match_date"])[:10], []).append(row)

    if len(unique_matches) > 1:
        return [], "ambiguous"
    return next(iter(unique_matches.values())), "exact"


def wynik_z_model_log(
    home: str, away: str, date: str | None, day_tolerance: int = 1
) -> str | None:
    """Zwraca `actual_result` meczu z `model_log` albo None.

    Źródło DARMOWE i NASZE — pytane po `predictions`, ale PRZED zewnętrznymi
    API z D5 (`MANUAL_SETTLE_EXTERNAL`). Ta sama konserwatywna zasada co
    w `link_leg`: brak dopasowania, dwa różne mecze w oknie dat albo dwa
    sprzeczne wyniki tego samego meczu → None. Rozliczenie z niewłaściwego
    meczu jest gorsze niż kupon czekający dzień dłużej.

    Args:
        home: Nazwa gospodarza (free-form, wpisana ręcznie przez użytkownika).
        away: Nazwa gościa (free-form).
        date: Data meczu (YYYY-MM-DD) lub None.
        day_tolerance: Tolerancja okna dat w dniach (domyślnie ±1).
    """
    if not home or not away or not date:
        return None

    norm_home = _norm_ascii(home)
    norm_away = _norm_ascii(away)
    if not norm_home or not norm_away:
        return None

    try:
        window = _date_window(date, day_tolerance)
    except ValueError as e:
        # Data z kuponu jest nieparsowalna — kupon nie rozliczy się NIGDY z żadnego
        # źródła, więc cisza tutaj chowałaby jedyny ślad prawdziwej przyczyny.
        log.warning("Niepoprawna data meczu %r w dzienniku (%s)", date, e)
        return None

    placeholders = ",".join("?" for _ in window)
    try:
        with connect() as conn:
            # Bezpieczne: f-string wstawia WYŁĄCZNIE `placeholders` (ciąg "?"),
            # daty idą sparametryzowane przez `tuple(window)`.
            rows = conn.execute(
                f"""SELECT team_home, team_away, match_date, actual_result
                    FROM model_log
                    WHERE substr(match_date, 1, 10) IN ({placeholders})""",  # nosec B608
                tuple(window),
            ).fetchall()
    except _AWARIE_BAZY as e:
        log.warning("model_log niedostępny (%s) — pomijam to źródło wyników", e)
        return None

    rows_for_match, pewnosc = _unikalny_mecz(rows, norm_home, norm_away)
    if pewnosc != "exact":
        return None

    # Pusty `actual_result` to BRAK danych (mecz zapisany przed rozegraniem),
    # nie sprzeczność — przebieg `final` zapisuje mecz, `evening` uzupełnia wynik.
    wyniki = {str(r["actual_result"]).strip() for r in rows_for_match
              if r["actual_result"] and str(r["actual_result"]).strip()}
    if len(wyniki) != 1:
        return None

    wynik = wyniki.pop()
    # Kontrakt tej funkcji brzmi „daj wynik, KTÓRYM DA SIĘ ROZLICZYĆ". Od 28.08
    # `model_log` trzyma także wyniki po dogrywce i karnych (wcześniej takie
    # wiersze nie dostawały `actual_result` w ogóle i kręciły się w kolejce).
    # Oddanie ich tutaj przerwałoby łańcuch źródeł w `settle_manual_coupons`:
    # `elif` uznałby, że wynik jest, i nie zapytałby źródła zewnętrznego, które
    # ma wynik regulaminowy. Kupon utknąłby przez dane, które właśnie dodaliśmy.
    powod = powod_nierozliczalny(wynik)
    if powod:
        log.debug("model_log ma dla %s vs %s wynik '%s' (%s) — nierozliczalny"
                  " dla rynkow 90-minutowych, oddaje pole kolejnemu zrodlu",
                  home, away, wynik, powod)
        return None
    return wynik
