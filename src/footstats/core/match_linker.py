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

Read-only: wyłącznie SELECT z predictions, zero zapisów, zero zewnętrznych API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from datetime import timedelta

from footstats.utils.db import connect
from footstats.utils.normalize import _norm_ascii


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
        rows = conn.execute(
            f"""SELECT id, team_home, team_away, match_date, ai_tip,
                       ai_confidence, prob_home, prob_draw, prob_away, actual_result
                FROM predictions
                WHERE substr(match_date, 1, 10) IN ({placeholders})""",
            tuple(window),
        ).fetchall()

    candidates = [
        row for row in rows
        if _norm_ascii(row["team_home"]) == norm_home
        and _norm_ascii(row["team_away"]) == norm_away
    ]

    if not candidates:
        return LinkResult(False, "none", None, "Brak dopasowania w oknie dat")

    # Redukcja do unikalnych meczów po (norm_home, norm_away, date10) — wiele
    # wierszy tego samego meczu (różne tipy) trafia do jednej grupy.
    unique_matches: dict[str, list] = {}
    for row in candidates:
        date10 = str(row["match_date"])[:10]
        unique_matches.setdefault(date10, []).append(row)

    if len(unique_matches) > 1:
        return LinkResult(False, "ambiguous", None, "Więcej niż jeden mecz pasuje w oknie dat")

    rows_for_match = next(iter(unique_matches.values()))
    best_row = max(rows_for_match, key=lambda r: r["ai_confidence"])

    return LinkResult(True, "exact", _row_to_prediction(best_row), "Dopasowano jednoznacznie")
