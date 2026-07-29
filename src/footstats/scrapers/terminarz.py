"""
terminarz.py — terminarze lig z darmowych źródeł (openfootball + OpenLigaDB).

Po co: pipeline widział dotąd wyłącznie mecze z horyzontu draftu (48h). Terminarz
całego sezonu daje trzy rzeczy, których wcześniej nie było:
  1. przygotowanie pod ważne kolejki / końcówkę sezonu / finały,
  2. odliczanie do startu ligi ("za ile Premier League"),
  3. zakładkę „Terminarz" w GUI.

Źródła (oba darmowe, bez klucza, bez anti-bota):
  - **openfootball** (GitHub raw JSON) — 20 lig na sezon, pełne terminarze z kolejkami.
  - **OpenLigaDB** — ligi niemieckie, redundancja i świeższe statusy meczów.

ZNANE OGRANICZENIE: openfootball **nie ma polskiej ligi** (sprawdzone 2026-07-29 —
20 plików w `2025-26/`, zero `pl.*`). Ekstraklasę trzeba brać z API-Football, które
projekt już ma wpięte. Pilnuje tego test `test_brak_ekstraklasy_jest_jawny`.
"""
from __future__ import annotations

import logging
from datetime import date

import requests

log = logging.getLogger(__name__)

_OPENFOOTBALL = "https://raw.githubusercontent.com/openfootball/football.json/master"
_OPENLIGADB = "https://api.openligadb.de"
_TIMEOUT = 20
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Ligi realnie dostępne w openfootball (zweryfikowane na repo, nie zgadywane).
LIGI: dict[str, dict[str, str]] = {
    "en.1": {"nazwa": "Premier League", "kraj": "Anglia"},
    "en.2": {"nazwa": "Championship", "kraj": "Anglia"},
    "es.1": {"nazwa": "La Liga", "kraj": "Hiszpania"},
    "es.2": {"nazwa": "La Liga 2", "kraj": "Hiszpania"},
    "de.1": {"nazwa": "Bundesliga", "kraj": "Niemcy"},
    "de.2": {"nazwa": "2. Bundesliga", "kraj": "Niemcy"},
    "it.1": {"nazwa": "Serie A", "kraj": "Włochy"},
    "it.2": {"nazwa": "Serie B", "kraj": "Włochy"},
    "fr.1": {"nazwa": "Ligue 1", "kraj": "Francja"},
    "fr.2": {"nazwa": "Ligue 2", "kraj": "Francja"},
    "nl.1": {"nazwa": "Eredivisie", "kraj": "Holandia"},
    "pt.1": {"nazwa": "Primeira Liga", "kraj": "Portugalia"},
    "be.1": {"nazwa": "Jupiler Pro League", "kraj": "Belgia"},
    "at.1": {"nazwa": "Bundesliga (AUT)", "kraj": "Austria"},
    "sco.1": {"nazwa": "Premiership", "kraj": "Szkocja"},
    "tr.1": {"nazwa": "Süper Lig", "kraj": "Turcja"},
    "gr.1": {"nazwa": "Super League", "kraj": "Grecja"},
}


def biezacy_sezon(dzis: str | None = None) -> str:
    """Kod sezonu openfootball ('2025-26'). Sezon europejski startuje w lipcu."""
    d = date.fromisoformat(dzis) if dzis else date.today()
    start = d.year if d.month >= 7 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def poprzedni_sezon(sezon: str) -> str:
    """'2026-27' → '2025-26'."""
    start = int(sezon[:4]) - 1
    return f"{start}-{(start + 1) % 100:02d}"


def _sezony_do_proby(sezon: str | None) -> list[str]:
    """
    Sezony do sprawdzenia, w kolejności.

    openfootball publikuje terminarz z opóźnieniem — w lipcu 2026 katalog
    `2026-27/` jeszcze nie istniał (same 404), choć sezon formalnie już trwał.
    Dlatego po bieżącym próbujemy poprzedni: lepiej pokazać terminarz o sezon
    starszy niż pustą zakładkę. Gdy user poda sezon jawnie — respektujemy wybór.
    """
    if sezon:
        return [sezon]
    biezacy = biezacy_sezon()
    return [biezacy, poprzedni_sezon(biezacy)]


def _pobierz_json(url: str):
    """JSON spod URL. None przy dowolnym błędzie — źródło jest opcjonalne."""
    try:
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    except (OSError, ValueError) as e:
        log.warning("terminarz: %s nieosiągalne: %s", url, e)
        return None
    if r.status_code != 200:
        log.warning("terminarz: %s → HTTP %s", url, r.status_code)
        return None
    try:
        return r.json()
    except ValueError:
        return None


def _wynik_ft(mecz: dict) -> list:
    """
    Wynik końcowy [gole_gosp, gole_gosc] albo [] gdy meczu nie rozegrano.

    openfootball nie trzyma jednego kształtu: bywa `score: {"ft": [1, 0]}`,
    bywa samo `score: [1, 0]`, bywa para `score1`/`score2`. Prawdziwe pliki
    mieszają te warianty w obrębie jednego repo — stąd tolerancyjny odczyt.
    """
    surowy = mecz.get("score")
    kandydat = None
    if isinstance(surowy, dict):
        kandydat = surowy.get("ft")
    elif isinstance(surowy, list):
        kandydat = surowy
    if kandydat is None and mecz.get("score1") is not None:
        kandydat = [mecz.get("score1"), mecz.get("score2")]

    if not isinstance(kandydat, list) or len(kandydat) != 2:
        return []
    try:
        return [int(kandydat[0]), int(kandydat[1])]
    except (TypeError, ValueError):
        return []


def _poprawna_data(tekst: str) -> bool:
    try:
        date.fromisoformat(tekst)
        return True
    except (ValueError, TypeError):
        return False


def pobierz_terminarz(kod_ligi: str, sezon: str | None = None) -> list[dict]:
    """
    Terminarz ligi z openfootball → lista znormalizowanych meczów.

    Każdy mecz: {data, godzina, kolejka, gospodarz, goscie, rozegrany, wynik, liga}.
    Mecz z niepoprawną datą lub bez nazwy drużyny jest pomijany — w terminarzu
    pokazywanym userowi nie ma miejsca na wpisy-śmieci.
    """
    if kod_ligi not in LIGI:
        log.debug("terminarz: nieznana liga %s", kod_ligi)
        return []

    dane = None
    for kandydat in _sezony_do_proby(sezon):
        dane = _pobierz_json(f"{_OPENFOOTBALL}/{kandydat}/{kod_ligi}.json")
        if isinstance(dane, dict):
            sezon = kandydat
            break
    if not isinstance(dane, dict):
        return []

    mecze: list[dict] = []
    for m in (dane.get("matches") or []):
        if not isinstance(m, dict):
            continue
        gosp = str(m.get("team1") or "").strip()
        gosc = str(m.get("team2") or "").strip()
        data = str(m.get("date") or "").strip()
        if not gosp or not gosc or not _poprawna_data(data):
            continue

        wynik_ft = _wynik_ft(m)
        rozegrany = len(wynik_ft) == 2
        mecze.append({
            "data": data,
            "godzina": str(m.get("time") or "").strip() or None,
            "kolejka": str(m.get("round") or "").strip() or None,
            "gospodarz": gosp,
            "goscie": gosc,
            "rozegrany": rozegrany,
            "wynik": f"{wynik_ft[0]}-{wynik_ft[1]}" if rozegrany else None,
            "liga": LIGI[kod_ligi]["nazwa"],
            # Sezon REALNIE użyty — może być starszy niż bieżący, gdy openfootball
            # jeszcze nie opublikował nowego. GUI musi pokazać prawdę, nie życzenie.
            "sezon": sezon,
            "zrodlo": "openfootball",
        })
    return mecze


def pobierz_terminarz_openligadb(skrot: str = "bl1", sezon: int | None = None) -> list[dict]:
    """
    Terminarz z OpenLigaDB (ligi niemieckie) w tym samym schemacie co openfootball.

    Redundancja + świeższy status meczu (`matchIsFinished`).
    """
    sezon = sezon or int(biezacy_sezon()[:4])
    dane = _pobierz_json(f"{_OPENLIGADB}/getmatchdata/{skrot}/{sezon}")
    if not isinstance(dane, list):
        return []

    mecze: list[dict] = []
    for m in dane:
        if not isinstance(m, dict):
            continue
        gosp = str((m.get("team1") or {}).get("teamName") or "").strip()
        gosc = str((m.get("team2") or {}).get("teamName") or "").strip()
        stempel = str(m.get("matchDateTime") or "")
        if not gosp or not gosc or "T" not in stempel:
            continue
        data, reszta = stempel.split("T", 1)
        if not _poprawna_data(data):
            continue

        mecze.append({
            "data": data,
            "godzina": reszta[:5] or None,
            "kolejka": str((m.get("group") or {}).get("groupName") or "").strip() or None,
            "gospodarz": gosp,
            "goscie": gosc,
            "rozegrany": bool(m.get("matchIsFinished")),
            "wynik": None,  # OpenLigaDB trzyma wynik w matchResults — nie potrzebujemy go w terminarzu
            "liga": str(m.get("leagueName") or skrot).strip(),
            "zrodlo": "openligadb",
        })
    return mecze


def _klucz_czasu(m: dict) -> str:
    """Data + godzina jako sortowalny string. Brak godziny ląduje na początku dnia."""
    return f"{m.get('data', '')} {m.get('godzina') or '00:00'}"


def nadchodzace(mecze: list[dict], od: str | None = None, limit: int | None = None) -> list[dict]:
    """
    Mecze jeszcze nierozegrane od danego dnia włącznie, posortowane chronologicznie.

    `od` w formacie YYYY-MM-DD (domyślnie dziś).
    """
    od = od or date.today().isoformat()
    przyszle = [
        m for m in mecze
        if not m.get("rozegrany") and str(m.get("data") or "") >= od
    ]
    przyszle.sort(key=_klucz_czasu)
    return przyszle[:limit] if limit else przyszle


def start_sezonu(mecze: list[dict]) -> str | None:
    """Data pierwszego meczu w terminarzu. None gdy terminarz pusty."""
    daty = [str(m.get("data")) for m in mecze if m.get("data")]
    return min(daty) if daty else None


def dni_do(data_docelowa: str, dzis: str | None = None) -> int | None:
    """
    Ile dni do podanej daty (ujemne = już minęła). None gdy data nieparsowalna.

    Zasila „za ile startuje liga" w GUI.
    """
    try:
        cel = date.fromisoformat(data_docelowa)
    except (ValueError, TypeError):
        return None
    baza = date.fromisoformat(dzis) if dzis else date.today()
    return (cel - baza).days


def przeglad_lig(sezon: str | None = None, limit_na_lige: int = 3) -> list[dict]:
    """
    Podsumowanie wszystkich lig na potrzeby zakładki „Terminarz".

    Dla każdej ligi: nazwa, kraj, start sezonu, ile dni do startu, licznik meczów
    i kilka najbliższych spotkań. Liga, której nie udało się pobrać, jest pomijana
    (nie blokuje pozostałych).
    """
    # UWAGA: `sezon` przekazujemy dalej jako None gdy user go nie podał — inaczej
    # `pobierz_terminarz` uzna go za wybór jawny i straci fallback na poprzedni
    # sezon (openfootball publikuje z opóźnieniem, patrz `_sezony_do_proby`).
    dzis = date.today().isoformat()
    przeglad: list[dict] = []

    for kod, meta in LIGI.items():
        mecze = pobierz_terminarz(kod, sezon)
        if not mecze:
            continue
        start = start_sezonu(mecze)
        kolejne = nadchodzace(mecze, od=dzis, limit=limit_na_lige)
        przeglad.append({
            "kod": kod,
            "nazwa": meta["nazwa"],
            "kraj": meta["kraj"],
            # Sezon z danych, nie z kalendarza — fallback mógł cofnąć o rok.
            "sezon": mecze[0].get("sezon") or biezacy_sezon(),
            "start_sezonu": start,
            "dni_do_startu": dni_do(start, dzis) if start else None,
            "meczow_total": len(mecze),
            "meczow_rozegranych": sum(1 for m in mecze if m.get("rozegrany")),
            "nastepne": kolejne,
        })

    # Ligi, które startują najwcześniej (albo już trwają), na górze.
    przeglad.sort(key=lambda x: (x["nastepne"][0]["data"] if x["nastepne"] else "9999"))
    return przeglad
