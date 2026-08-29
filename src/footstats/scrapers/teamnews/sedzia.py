"""
sedzia.py — statystyki sędziego z FotMoba na kolumny tabeli `referees`.

Osobny moduł, bo to jedyne miejsce, gdzie jednostki źródła i bazy się nie zgadzają:

    FotMob                              referees
    yellowCards  valueType=perMatch  →  avg_yellow    bierzemy wprost
    redCards     valueType=total     →  avg_red       DZIELIMY przez liczbę meczów
    matches      valueType=total     →  n_matches     wprost
    (nie podaje)                     →  avg_goals     klucza NIE MA
    (nie podaje)                     →  home_win_pct  klucza NIE MA

Dwa ostatnie wiersze są sednem. Zero w kolumnie "średnia goli" nie znaczy
"nie wiem", tylko "zmierzyłem zero" — a to nieprawda i nikt tego nie odróżni
po fakcie.

`valueType` jest sprawdzany, nie zakładany: gdyby źródło zmieniło jednostkę
żółtych z `perMatch` na `total`, milczące przyjęcie `value` wpisałoby do bazy
205 kartek na mecz. Brak `perMatch` → brak klucza.
"""
from __future__ import annotations


def _wartosci(surowy: dict) -> dict[str, dict]:
    """Tablica `stats` → {typ: wpis}. Śmieci i wpisy bez `type` odpadają."""
    out: dict[str, dict] = {}
    for wpis in surowy.get("stats") or []:
        if isinstance(wpis, dict) and wpis.get("type"):
            out[str(wpis["type"])] = wpis
    return out


def statystyki_sedziego(surowy: dict | None) -> dict[str, float | None]:
    """
    Mapuje `matchFacts.infoBox.Referee` FotMoba na kolumny tabeli `referees`.

    Klucz trafia do wyniku WYŁĄCZNIE wtedy, gdy źródło realnie go podało
    w oczekiwanej jednostce. Brak klucza znaczy "nie wiadomo" i tak ma zostać
    zapisany w bazie (NULL), nie zerem.
    """
    if not isinstance(surowy, dict) or not surowy:
        return {}

    stat = _wartosci(surowy)
    wynik: dict[str, float | None] = {}

    surowe_mecze = stat.get("matches", {}).get("value")
    liczba_meczow = (int(surowe_mecze)
                     if isinstance(surowe_mecze, (int, float)) and surowe_mecze > 0
                     else None)
    if liczba_meczow:
        wynik["n_matches"] = liczba_meczow

    zolte = stat.get("yellowCards") or {}
    if (zolte.get("valueType") == "perMatch"
            and isinstance(zolte.get("value"), (int, float))):
        wynik["avg_yellow"] = float(zolte["value"])

    czerwone = stat.get("redCards") or {}
    suma_czerwonych = czerwone.get("value")
    if isinstance(suma_czerwonych, (int, float)) and liczba_meczow:
        # `value` to SUMA sezonu — bez tego dzielenia Oliver dostałby avg_red=2.0,
        # czyli dwie czerwone w każdym meczu zamiast 0.037.
        wynik["avg_red"] = round(float(suma_czerwonych) / liczba_meczow, 4)

    return wynik
