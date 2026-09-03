"""
historical_loader.py – pobiera i normalizuje dane historyczne z trzech źródeł:
  1. football-data.co.uk  (CSV per sezon: ENG/GER/ESP/ITA/FRA/NED/BEL/SCO)
  2. football-data.co.uk  (nowy format "new/": Ekstraklasa, AUT-Bundesliga)
  3. xgabora GitHub       (226k meczów 2000-2025) — NIE w domyślnym zakresie,
     bo nazywa ligi kodami ("E0") zamiast pełnych nazw jak reszta datasetu

Użycie:
    from footstats.data.historical_loader import download_all, load_cached

    df = download_all()          # pobiera i cache'uje (pełny zakres produkcyjny)
    df = load_cached()           # tylko z dysku (szybkie)

`download_all()` bez argumentów odtwarza dokładnie ten skład, który leży
w `data/hist_cache/full_dataset.parquet` i jedzie do obrazów Cloud Run
(patrz `Dockerfile.jobs` / `Dockerfile.api`) — dzięki temu odświeżenie danych
jest jednym wywołaniem i nie da się nim przypadkiem okroić zbioru.
"""

import io
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parents[3] / "data" / "hist_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BASE_FDCO = "https://www.football-data.co.uk"

# Ile sezonów trzymamy w datasecie: trwający + 10 rozegranych do końca.
# Nie 10 łącznie — wtedy start nowego sezonu (w którym jest kilkanaście meczów)
# wypychałby z okna cały sezon rozegrany, czyli refresh dokładałby 34 mecze
# kosztem 2566. Liczba pełnych sezonów ma być stała przez cały rok.
LICZBA_SEZONOW = 11

# Plik trwającego sezonu dopisuje kolejki co tydzień, więc cache musi wygasać.
# Sezony zamknięte są niezmienne — ich cache zostaje na zawsze (patrz
# `_cache_wazny`), inaczej każdy przebieg ciągnąłby ~80 plików CSV bez powodu.
TTL_BIEZACY_SEZON_H = 12


def kod_sezonu(dzien: date | None = None) -> str:
    """Kod sezonu football-data.co.uk dla danego dnia ("2627" = sezon 2026/27).

    Sezon leży na przełomie lat kalendarzowych. Za granicę bierzemy lipiec:
    football-data publikuje plik nowego sezonu jeszcze przed pierwszą kolejką,
    a rozgrywki startują w lipcu/sierpniu.
    """
    d = dzien or date.today()
    rok = d.year if d.month >= 7 else d.year - 1
    return f"{rok % 100:02d}{(rok + 1) % 100:02d}"


def ostatnie_sezony(ile: int = LICZBA_SEZONOW, dzien: date | None = None) -> list[str]:
    """Kody `ile` ostatnich sezonów, od bieżącego wstecz.

    Liczone z daty, nie z literału. Poprzednia wersja była listą wpisaną na
    sztywno i skończyła się na "2526" — 2026-08-07 dataset urywał się więc na
    maju, a model typował mecze sezonu, którego nie widział ani razu.
    """
    rok = 2000 + int(kod_sezonu(dzien)[:2])
    return [f"{(rok - i) % 100:02d}{(rok - i + 1) % 100:02d}" for i in range(ile)]


# Zachowane dla zgodności z kodem, który importuje stałą.
FDCO_SEASONS = ostatnie_sezony()

# Ligi z plików sezonowych (kod football-data.co.uk → nazwa w datasecie).
# Rozszerzone 2026-08-07: przez rok braliśmy 8 z 22 dostępnych, więc Poisson
# nie miał historii dla większości meczów, jakie w ogóle podaje źródło predykcji.
# Niższe klasy (E1-EC, SC1-SC3, D2, I2, SP2, F2) też mają wartość: drużyny
# spadają i awansują, a bez nich beniaminek startuje bez ani jednego meczu.
FDCO_LEAGUES = {
    "E0":  "ENG-Premier League",
    "E1":  "ENG-Championship",
    "E2":  "ENG-League One",
    "E3":  "ENG-League Two",
    "EC":  "ENG-National League",
    "SC0": "SCO-Premiership",
    "SC1": "SCO-Championship",
    "SC2": "SCO-League One",
    "SC3": "SCO-League Two",
    "D1":  "GER-Bundesliga",
    "D2":  "GER-2. Bundesliga",
    "I1":  "ITA-Serie A",
    "I2":  "ITA-Serie B",
    "SP1": "ESP-La Liga",
    "SP2": "ESP-Segunda Division",
    "F1":  "FRA-Ligue 1",
    "F2":  "FRA-Ligue 2",
    "N1":  "NED-Eredivisie",
    "B1":  "BEL-First Division A",
    "P1":  "POR-Primeira Liga",
    "T1":  "TUR-Super Lig",
    "G1":  "GRE-Super League",
}

# Kraje z nowego formatu (jeden plik zbiorczy z całą historią).
# Wartość to nazwa ZAPASOWA — używana tylko, gdy w pliku nie ma kolumny
# `League`. Normalnie nazwa ligi idzie z pliku, bo część krajów trzyma
# w jednym pliku kilka rozgrywek (ARG: Liga Profesional + Copa,
# SWZ: Super League + Challenge League).
FDCO_NEW_LEAGUES = {
    "POL": "POL-Ekstraklasa",
    "AUT": "AUT-Bundesliga",
    "ARG": "ARG-Liga Profesional",
    "BRA": "BRA-Serie A",
    "CHN": "CHN-Super League",
    "DNK": "DNK-Superliga",
    "FIN": "FIN-Veikkausliiga",
    "IRL": "IRL-Premier Division",
    "JPN": "JPN-J1 League",
    "MEX": "MEX-Liga MX",
    "NOR": "NOR-Eliteserien",
    "ROU": "ROU-Superliga",
    "RUS": "RUS-Premier League",
    "SWE": "SWE-Allsvenskan",
    "SWZ": "SWZ-Super League",
    "USA": "USA-MLS",
}


def _nazwa_ligi_new(country_code: str, liga_z_pliku: str | None) -> str:
    """Nazwa ligi dla wiersza z pliku `new/`: "SWZ-Super League".

    Źródło zostawia w nazwach końcowe spacje ('Superliga '), przez co ta sama
    liga potrafi wystąpić jako dwie różne — stąd `strip()`. Pusta nazwa cofa
    się do mapy krajów, żeby nigdy nie powstało samo "SWZ-".
    """
    # `pd.isna` osobno: pusta komórka wraca z pandas jako NaN, a NaN jest
    # prawdziwościowo PRAWDZIWY — `or ""` go nie złapie i powstałoby "POL-nan".
    if liga_z_pliku is None or pd.isna(liga_z_pliku):
        return FDCO_NEW_LEAGUES.get(country_code, country_code)
    nazwa = str(liga_z_pliku).strip()
    if not nazwa:
        return FDCO_NEW_LEAGUES.get(country_code, country_code)
    return f"{country_code}-{nazwa}"

XGABORA_MATCHES_URL = (
    "https://raw.githubusercontent.com/xgabora/"
    "Club-Football-Match-Data-2000-2025/main/data/Matches.csv"
)
XGABORA_ELO_URL = (
    "https://raw.githubusercontent.com/xgabora/"
    "Club-Football-Match-Data-2000-2025/main/data/EloRatings.csv"
)


# ─────────────────────────── helpers ──────────────────────────────────────

def _get(url: str, timeout: int = 30) -> bytes | None:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "FootStats/3.0"})
        r.raise_for_status()
        return r.content
    except (requests.RequestException, OSError) as e:
        log.warning("HTTP error %s → %s", url, e)
        return None


def _czytaj_csv(raw: bytes) -> pd.DataFrame:
    """CSV ze źródła → ramka, z UTF-8 przed latin-1.

    Kolejność jest tu całą treścią: `latin-1` dekoduje KAŻDY bajt bez wyjątku,
    więc plik w UTF-8 nie padał, tylko wchodził przekręcony ("PreuÃen MÃ¼nster"
    zamiast "Preußen Münster"). Przekręcona nazwa nie dopasuje się do niczego,
    czyli mecz przepada dla λ Poissona i dla formy — cicho, bez śladu w logach.
    Fallback zostaje, bo archiwalne sezony u źródła NAPRAWDĘ są w cp1252/latin-1.
    """
    try:
        return pd.read_csv(io.BytesIO(raw), encoding="utf-8", on_bad_lines="skip")
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(raw), encoding="latin-1", on_bad_lines="skip")


def _parse_date(s: str) -> pd.Timestamp | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return pd.to_datetime(s, format=fmt)
        except (ValueError, TypeError):
            pass
    return pd.NaT


# ─────────────────────────── FDCO sezonowy ────────────────────────────────

def _wpisz_kursy(
    out: pd.DataFrame,
    df: pd.DataFrame,
    docelowe: tuple[str, ...],
    warianty: list[tuple[str, ...]],
) -> None:
    """Przepisuje do `out[docelowe]` ten wariant kolumn, który MA najwięcej danych.

    O wyborze decyduje POKRYCIE, nie kolejność. Kolumna, która istnieje i jest
    pusta, spełniała dotąd warunek obecności tak samo dobrze jak wypełniona:
    źródło dołożyło w `new/JPN.csv` kolumny B365C* wypełnione dopiero od sezonu
    2025 (170 z 4563 wierszy), przy `AvgCH` pełnym w 100% — i odświeżenie
    datasetu 2026-09-03 skasowało kursy w 4353 japońskich meczach. Bez kursów
    mecz cicho wypada z ramienia RYNKOWEGO walk-forwardu (`wf_harness.predict_one`
    je devigauje), więc pomiar „model vs rynek" robi się węższy, zamiast krzyknąć.

    Liczy się wiersz z KOMPLETEM kolumn wariantu: devig potrzebuje wszystkich
    wyjść naraz, a dwa z trzech dają marżę, której nikt nie wystawił. Z tego
    samego powodu wariantów się nie miesza w obrębie jednego meczu.

    Remis rozstrzyga kolejność `warianty` — przy równym pokryciu zostaje ten
    sam dostawca co dotąd, żeby poprawka nie przestawiła kursów w ligach,
    w których nic się nie zepsuło. Zmiana preferencji dostawcy to osobna
    decyzja i osobny pomiar.

    Ta funkcja istnieje, bo ta sama reguła żyła w tym pliku w TRZECH kopiach
    (kursy 1X2 w `new`, 1X2 w `season`, Over/Under w `season`). Trzy kopie jednej
    reguły to trzy okazje, żeby rozjechały się po cichu.
    """
    najlepszy: tuple[int, tuple[str, ...]] | None = None
    for wariant in warianty:
        if not set(wariant) <= set(df.columns):
            continue
        kolumny = [pd.to_numeric(df[k], errors="coerce") for k in wariant]
        pokrycie = int(pd.concat(kolumny, axis=1).notna().all(axis=1).sum())
        if pokrycie and (najlepszy is None or pokrycie > najlepszy[0]):
            najlepszy = (pokrycie, wariant)

    if najlepszy is None:
        return
    for cel, zrodlo in zip(docelowe, najlepszy[1]):
        out[cel] = pd.to_numeric(df[zrodlo], errors="coerce")


def _download_fdco_season(league_code: str, season: str) -> pd.DataFrame | None:
    url = f"{BASE_FDCO}/mmz4281/{season}/{league_code}.csv"
    raw = _get(url)
    if raw is None:
        return None
    try:
        df = _czytaj_csv(raw)
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as e:
        log.warning("Błąd parsowania %s: %s", url, e)
        return None
    if df.empty or "HomeTeam" not in df.columns:
        return None

    # Normalizacja → wspólny schemat
    out = pd.DataFrame()
    out["date"]    = df["Date"].apply(_parse_date)
    out["league"]  = FDCO_LEAGUES.get(league_code, league_code)
    out["season"]  = f"20{season[:2]}/{season[2:]}"
    out["home"]    = df["HomeTeam"].str.strip()
    out["away"]    = df["AwayTeam"].str.strip()
    out["hg"]      = pd.to_numeric(df.get("FTHG", df.get("HG")), errors="coerce")
    out["ag"]      = pd.to_numeric(df.get("FTAG", df.get("AG")), errors="coerce")
    out["result"]  = df.get("FTR", df.get("Res", ""))
    out["ht_hg"]   = pd.to_numeric(df.get("HTHG", pd.Series(dtype=float)), errors="coerce")
    out["ht_ag"]   = pd.to_numeric(df.get("HTAG", pd.Series(dtype=float)), errors="coerce")
    out["hs"]      = pd.to_numeric(df.get("HS"),  errors="coerce")
    out["as_"]     = pd.to_numeric(df.get("AS"),  errors="coerce")
    out["hst"]     = pd.to_numeric(df.get("HST"), errors="coerce")
    out["ast"]     = pd.to_numeric(df.get("AST"), errors="coerce")
    out["hc"]      = pd.to_numeric(df.get("HC"),  errors="coerce")
    out["ac"]      = pd.to_numeric(df.get("AC"),  errors="coerce")
    out["hy"]      = pd.to_numeric(df.get("HY"),  errors="coerce")
    out["ay"]      = pd.to_numeric(df.get("AY"),  errors="coerce")

    # Kursy – przy równym pokryciu Bet365, dalej Average (patrz `_wpisz_kursy`)
    _wpisz_kursy(out, df, ("odds_h", "odds_d", "odds_a"), [
        ("B365H", "B365D", "B365A"),
        ("BbAvH", "BbAvD", "BbAvA"),
        ("AvgH",  "AvgD",  "AvgA"),
        ("WHH",   "WHD",   "WHA"),
    ])

    # Over 2.5
    _wpisz_kursy(out, df, ("odds_over25", "odds_under25"), [
        ("B365>2.5", "B365<2.5"),
        ("BbAv>2.5", "BbAv<2.5"),
        ("Avg>2.5",  "Avg<2.5"),
    ])

    out["source"] = "fdco_season"
    return out.dropna(subset=["home", "away", "hg", "ag"])


def _koniec_sezonu(sezon: str) -> pd.Timestamp:
    """Data, po której plik sezonu jest już kompletny.

    Rozgrywki kończą się do czerwca, więc lipiec roku zamykającego sezon
    ("2526" → lipiec 2026) to bezpieczny próg.
    """
    return pd.Timestamp(year=2000 + int(sezon[2:]), month=7, day=1)


def _cache_wazny(cache_f: Path, sezon: str) -> bool:
    """Czy plik cache można wziąć z dysku zamiast pobierać.

    Sezon trwający: tylko w granicach TTL — inaczej dataset zamarza na kolejce,
    na której akurat pierwszy raz go pobrano.

    Sezon zamknięty: tylko gdy plik powstał PO jego zakończeniu. Sam fakt, że
    sezon się skończył, nie znaczy, że mamy komplet — pliki pobrane w kwietniu
    2026 uznawaliśmy za niezmienne, przez co Premier League, Bundesliga
    i Eredivisie urwały się na 2026-03-22 i traciły ~2 miesiące, które u źródła
    były dostępne (znalezione 2026-08-08).
    """
    if not cache_f.exists():
        return False
    zapisany = pd.Timestamp(cache_f.stat().st_mtime, unit="s")
    if sezon != kod_sezonu():
        return zapisany >= _koniec_sezonu(sezon)
    wiek_h = (pd.Timestamp.now() - zapisany).total_seconds() / 3600
    return wiek_h < TTL_BIEZACY_SEZON_H


def download_fdco_seasons(
    leagues: list[str] | None = None,
    seasons: list[str] | None = None,
) -> pd.DataFrame:
    """Pobiera ligi sezonowe z football-data.co.uk."""
    leagues = leagues or list(FDCO_LEAGUES.keys())
    seasons = seasons or ostatnie_sezony()
    frames = []
    for lg in leagues:
        for s in seasons:
            cache_f = CACHE_DIR / f"fdco_{lg}_{s}.parquet"
            if _cache_wazny(cache_f, s):
                frames.append(pd.read_parquet(cache_f))
                continue
            df = _download_fdco_season(lg, s)
            if df is not None and not df.empty:
                df.to_parquet(cache_f, index=False)
                frames.append(df)
                log.info("Pobrano %s %s → %d meczów", lg, s, len(df))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ─────────────────────────── FDCO new format ──────────────────────────────

def _download_fdco_new(country_code: str) -> pd.DataFrame | None:
    url = f"{BASE_FDCO}/new/{country_code}.csv"
    raw = _get(url)
    if raw is None:
        return None
    try:
        df = _czytaj_csv(raw)
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as e:
        log.warning("Błąd parsowania %s: %s", url, e)
        return None
    if df.empty or "Home" not in df.columns:
        return None

    out = pd.DataFrame()
    out["date"]    = df["Date"].apply(_parse_date)
    # Nazwa ligi Z PLIKU: część krajów trzyma w jednym pliku kilka rozgrywek
    # (ARG, SWZ), więc etykieta per kod kraju wrzucałaby drugą klasę pod nazwę
    # pierwszej — cichy fałsz w kolumnie, po której filtrujemy i raportujemy.
    kolumna_ligi = df["League"] if "League" in df.columns else pd.Series([None] * len(df))
    out["league"]  = [_nazwa_ligi_new(country_code, x) for x in kolumna_ligi]
    out["season"]  = df["Season"].astype(str) if "Season" in df.columns else ""
    out["home"]    = df["Home"].str.strip()
    out["away"]    = df["Away"].str.strip()
    out["hg"]      = pd.to_numeric(df.get("HG"), errors="coerce")
    out["ag"]      = pd.to_numeric(df.get("AG"), errors="coerce")
    out["result"]  = df.get("Res", "")

    # Kursy (format "new" używa B365CH/B365CD/B365CA lub AvgCH itd.).
    # Komplet kolumn wariantu, nie tylko pierwszej: część plików `new/` ma kurs
    # gospodarza bez kursu gościa, a sprawdzanie samego `h_col` kończyło się
    # `KeyError: 'B365CA'`, które przerywało pobieranie całego kraju.
    # O wyborze wariantu decyduje pokrycie — patrz `_wpisz_kursy`.
    _wpisz_kursy(out, df, ("odds_h", "odds_d", "odds_a"), [
        ("B365CH", "B365CD", "B365CA"),
        ("AvgCH",  "AvgCD",  "AvgCA"),
        ("MaxCH",  "MaxCD",  "MaxCA"),
    ])

    out["source"] = "fdco_new"
    return out.dropna(subset=["home", "away", "hg", "ag"])


def download_fdco_new(countries: list[str] | None = None) -> pd.DataFrame:
    """Pobiera historię ligową z nowego formatu football-data.co.uk."""
    countries = countries or list(FDCO_NEW_LEAGUES.keys())
    frames = []
    for cc in countries:
        cache_f = CACHE_DIR / f"fdco_new_{cc}.parquet"
        # Plik new/ jest aktualizowany, trzymaj max 1 dzień cache
        if cache_f.exists():
            age_h = (pd.Timestamp.now() - pd.Timestamp(cache_f.stat().st_mtime, unit="s")).total_seconds() / 3600
            if age_h < 24:
                frames.append(pd.read_parquet(cache_f))
                continue
        df = _download_fdco_new(cc)
        if df is not None and not df.empty:
            df.to_parquet(cache_f, index=False)
            frames.append(df)
            log.info("Pobrano fdco_new %s → %d meczów", cc, len(df))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ─────────────────────────── xgabora ──────────────────────────────────────

def _download_xgabora_matches() -> pd.DataFrame | None:
    cache_f = CACHE_DIR / "xgabora_matches.parquet"
    if cache_f.exists():
        age_days = (pd.Timestamp.now() - pd.Timestamp(cache_f.stat().st_mtime, unit="s")).total_seconds() / 86400
        if age_days < 7:
            return pd.read_parquet(cache_f)

    raw = _get(XGABORA_MATCHES_URL, timeout=60)
    if raw is None:
        return None
    try:
        df = pd.read_csv(io.BytesIO(raw), encoding="utf-8", on_bad_lines="skip", low_memory=False)
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as e:
        log.warning("Błąd xgabora matches: %s", e)
        return None
    if df.empty:
        return None

    log.info("xgabora MATCHES raw kolumny: %s", df.columns.tolist())
    df.to_parquet(cache_f, index=False)
    return df


# _download_xgabora_elo() usunieta 2026-07-30 — nigdy nie wolana. Rankingi Elo
# bierzemy ze scrapers/clubelo.py (swiezy feed, aktualizowany codziennie),
# a nie z jednorazowego CSV w repo xgabora. Pobieranie MECZOW (_download_xgabora_matches)
# zostaje — to zrodlo historii jest uzywane.


def normalize_xgabora(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizuje xgabora Matches.csv do wspólnego schematu.
    Kolumny: Division, MatchDate, HomeTeam, AwayTeam, FTHome, FTAway,
             FTResult, HomeElo, AwayElo, Form3Home/5, OddHome/Draw/Away,
             Over25, Under25, HomeShots, AwayShots itd.
    """
    out = pd.DataFrame()
    out["date"]    = pd.to_datetime(df["MatchDate"], errors="coerce")
    out["league"]  = df["Division"].astype(str).str.strip()
    out["home"]    = df["HomeTeam"].astype(str).str.strip()
    out["away"]    = df["AwayTeam"].astype(str).str.strip()
    out["hg"]      = pd.to_numeric(df["FTHome"],  errors="coerce")
    out["ag"]      = pd.to_numeric(df["FTAway"],  errors="coerce")
    out["result"]  = df["FTResult"].astype(str).str.strip()
    out["ht_hg"]   = pd.to_numeric(df.get("HTHome"), errors="coerce")
    out["ht_ag"]   = pd.to_numeric(df.get("HTAway"), errors="coerce")
    out["hs"]      = pd.to_numeric(df.get("HomeShots"),  errors="coerce")
    out["as_"]     = pd.to_numeric(df.get("AwayShots"),  errors="coerce")
    out["hst"]     = pd.to_numeric(df.get("HomeTarget"), errors="coerce")
    out["ast"]     = pd.to_numeric(df.get("AwayTarget"), errors="coerce")
    out["hc"]      = pd.to_numeric(df.get("HomeCorners"), errors="coerce")
    out["ac"]      = pd.to_numeric(df.get("AwayCorners"), errors="coerce")
    out["hy"]      = pd.to_numeric(df.get("HomeYellow"), errors="coerce")
    out["ay"]      = pd.to_numeric(df.get("AwayYellow"), errors="coerce")
    out["odds_h"]  = pd.to_numeric(df.get("OddHome"),  errors="coerce")
    out["odds_d"]  = pd.to_numeric(df.get("OddDraw"),  errors="coerce")
    out["odds_a"]  = pd.to_numeric(df.get("OddAway"),  errors="coerce")
    out["odds_over25"]  = pd.to_numeric(df.get("Over25"),   errors="coerce")
    out["odds_under25"] = pd.to_numeric(df.get("Under25"),  errors="coerce")
    out["elo_home"] = pd.to_numeric(df.get("HomeElo"), errors="coerce")
    out["elo_away"] = pd.to_numeric(df.get("AwayElo"), errors="coerce")
    # Forma (punkty z ost. 3/5 meczów — gotowe z datasetu)
    out["form3_home"] = pd.to_numeric(df.get("Form3Home"), errors="coerce")
    out["form5_home"] = pd.to_numeric(df.get("Form5Home"), errors="coerce")
    out["form3_away"] = pd.to_numeric(df.get("Form3Away"), errors="coerce")
    out["form5_away"] = pd.to_numeric(df.get("Form5Away"), errors="coerce")
    out["source"] = "xgabora"
    return out.dropna(subset=["home", "away", "hg", "ag"])


def download_xgabora() -> pd.DataFrame:
    """Pobiera i normalizuje xgabora dataset."""
    raw = _download_xgabora_matches()
    if raw is None or raw.empty:
        return pd.DataFrame()
    return normalize_xgabora(raw)


# ─────────────────────────── soccerdata / FBref (xG) ─────────────────────

# Mapowanie naszych nazw lig na formaty soccerdata/FBref
_FBREF_LEAGUE_MAP: dict[str, str] = {
    "ENG-Premier League": "ENG-Premier League",
    "GER-Bundesliga":     "GER-Bundesliga",
    "ESP-La Liga":        "ESP-La Liga",
    "ITA-Serie A":        "ITA-Serie A",
    "FRA-Ligue 1":        "FRA-Ligue 1",
    "NED-Eredivisie":     "NED-Eredivisie",
    # Skróty alternatywne
    "Premier League":     "ENG-Premier League",
    "Bundesliga":         "GER-Bundesliga",
    "La Liga":            "ESP-La Liga",
    "Serie A":            "ITA-Serie A",
    "Ligue 1":            "FRA-Ligue 1",
    "Eredivisie":         "NED-Eredivisie",
}

FBREF_DEFAULT_LEAGUES = list(_FBREF_LEAGUE_MAP.values())[:6]
FBREF_DEFAULT_SEASONS = ["2024", "2023", "2022"]


def _download_fbref_one(league: str, season: str) -> pd.DataFrame | None:
    """
    Pobiera xG z FBref dla jednej ligi/sezonu przez soccerdata.
    Zwraca DataFrame z kolumnami: date, league, home, away, xg_home, xg_away.
    Zwraca None jeśli brak soccerdata lub błąd.
    """
    try:
        import soccerdata as sd  # type: ignore
    except ImportError:
        log.debug("soccerdata niedostępne (pip install soccerdata)")
        return None

    fbref_league = _FBREF_LEAGUE_MAP.get(league, league)
    cache_f = CACHE_DIR / f"fbref_{fbref_league.replace(' ', '_').replace('-', '_')}_{season}.parquet"
    if cache_f.exists():
        age_days = (
            pd.Timestamp.now() - pd.Timestamp(cache_f.stat().st_mtime, unit="s")
        ).total_seconds() / 86400
        if age_days < 30:  # FBref dane historyczne — cache 30 dni
            return pd.read_parquet(cache_f)

    try:
        fbref = sd.FBref(leagues=fbref_league, seasons=int(season))
        sched = fbref.read_schedule()
    except (ValueError, KeyError, AttributeError, OSError) as e:
        log.warning("FBref schedule error %s %s: %s", league, season, e)
        return None

    if sched is None or sched.empty:
        return None

    # Spłaszcz MultiIndex (soccerdata zwraca go w niektórych wersjach)
    if isinstance(sched.index, pd.MultiIndex):
        sched = sched.reset_index()
    else:
        sched = sched.reset_index()

    # Normalizuj nazwy kolumn (soccerdata zmienia je między wersjami)
    cols = {c.lower(): c for c in sched.columns}

    def _col(*candidates: str) -> str | None:
        for c in candidates:
            if c in cols:
                return cols[c]
        return None

    date_col  = _col("date")
    home_col  = _col("home_team", "home", "hometeam")
    away_col  = _col("away_team", "away", "awayteam")
    xgh_col   = _col("home_xg", "xg_home", "xgh", "home_xgoals")
    xga_col   = _col("away_xg", "xg_away", "xga", "away_xgoals")

    if not date_col or not home_col or not away_col:
        log.warning("FBref: brak kluczowych kolumn w %s %s. Dostępne: %s",
                    league, season, list(sched.columns))
        return None

    out = pd.DataFrame()
    out["date"]    = pd.to_datetime(sched[date_col], errors="coerce")
    out["league"]  = fbref_league
    out["home"]    = sched[home_col].astype(str).str.strip()
    out["away"]    = sched[away_col].astype(str).str.strip()
    out["xg_home"] = pd.to_numeric(sched[xgh_col], errors="coerce") if xgh_col else pd.NA
    out["xg_away"] = pd.to_numeric(sched[xga_col], errors="coerce") if xga_col else pd.NA
    out["source_xg"] = "fbref"

    out = out.dropna(subset=["date", "home", "away"])
    out = out[out["xg_home"].notna() | out["xg_away"].notna()]

    if out.empty:
        log.warning("FBref %s %s: brak danych xG (schedule nie zawiera home_xg/away_xg)", league, season)
        # Spróbuj pobrać ze statystyk strzeleckich
        out = _try_fbref_shooting(fbref, fbref_league, sched, date_col, home_col, away_col)

    if out is not None and not out.empty:
        out.to_parquet(cache_f, index=False)
        log.info("FBref xG %s %s -> %d meczów", league, season, len(out))
    return out if out is not None and not out.empty else None


def _try_fbref_shooting(fbref, league: str, sched, date_col, home_col, away_col) -> pd.DataFrame | None:
    """Fallback: pobierz xG ze statystyk drużynowych jeśli nie ma w schedule."""
    try:
        shots = fbref.read_team_match_stats(stat_type="shooting")
    except (ValueError, KeyError, AttributeError, OSError) as e:
        log.debug("FBref shooting fallback error: %s", e)
        return None

    if shots is None or shots.empty:
        return None

    # Statystyki shooting mają MultiIndex (team, game_id) lub (game_id, team)
    shots_flat = shots.reset_index()

    xg_col = next((shots_flat.columns[i] for i, c in enumerate(shots_flat.columns)
                   if c.lower() in ("xg", "expected_goals", "xgoals")), None)
    team_col = next((shots_flat.columns[i] for i, c in enumerate(shots_flat.columns)
                     if c.lower() in ("team", "squad")), None)

    if xg_col is None or team_col is None:
        return None

    # Połącz schedule ze strzałami per mecz/drużyna
    sched_flat = sched.reset_index()
    game_col = next((c for c in shots_flat.columns if c.lower() in ("game", "game_id", "match_id")), None)
    sched_game_col = next((c for c in sched_flat.columns if c.lower() in ("game", "game_id")), None)

    if game_col and sched_game_col:
        merged = sched_flat.merge(shots_flat[[game_col, team_col, xg_col]], on=game_col, how="left")
        # Pivot home/away xG
        home_xg = merged[merged[team_col] == merged[home_col]][[sched_game_col, xg_col]].rename(
            columns={xg_col: "xg_home"})
        away_xg = merged[merged[team_col] == merged[away_col]][[sched_game_col, xg_col]].rename(
            columns={xg_col: "xg_away"})
        out2 = sched_flat[[date_col, home_col, away_col]].copy()
        out2["league"] = league
        out2["xg_home"] = home_xg["xg_home"].values if len(home_xg) == len(out2) else pd.NA
        out2["xg_away"] = away_xg["xg_away"].values if len(away_xg) == len(out2) else pd.NA
        out2 = out2.rename(columns={date_col: "date", home_col: "home", away_col: "away"})
        out2["source_xg"] = "fbref_shooting"
        return out2.dropna(subset=["date", "home", "away"])
    return None


def download_fbref_xg(
    leagues: list[str] | None = None,
    seasons: list[str] | None = None,
) -> pd.DataFrame:
    """
    Pobiera xG z FBref dla wielu lig i sezonów.
    Wymaga: pip install soccerdata

    Zwraca DataFrame z kolumnami: date, league, home, away, xg_home, xg_away
    """
    leagues = leagues or FBREF_DEFAULT_LEAGUES
    seasons = seasons or FBREF_DEFAULT_SEASONS
    frames  = []

    for lg in leagues:
        for s in seasons:
            df = _download_fbref_one(lg, s)
            if df is not None and not df.empty:
                frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def merge_xg_into_dataset(df_main: pd.DataFrame, df_xg: pd.DataFrame) -> pd.DataFrame:
    """
    Wzbogaca główny DataFrame o kolumny xg_home i xg_away z FBref.

    Dopasowanie po: league + home + away + date (tolerancja ±1 dzień).
    Tylko mecze które już mają xg_home=NaN dostają uzupełnienie.
    """
    if df_xg.empty or df_main.empty:
        return df_main

    # Normalizuj daty
    df_xg = df_xg.copy()
    df_xg["date"] = pd.to_datetime(df_xg["date"], errors="coerce")
    df_main = df_main.copy()

    if "xg_home" not in df_main.columns:
        df_main["xg_home"] = pd.NA
    if "xg_away" not in df_main.columns:
        df_main["xg_away"] = pd.NA

    # Indeks xG: (home_lower, away_lower, date_str)
    xg_map: dict[tuple, tuple[float, float]] = {}
    for _, r in df_xg.iterrows():
        if pd.isna(r.get("xg_home")) and pd.isna(r.get("xg_away")):
            continue
        key = (
            str(r["home"]).lower()[:12],
            str(r["away"]).lower()[:12],
            str(r["date"])[:10],
        )
        xg_map[key] = (r.get("xg_home"), r.get("xg_away"))

    def _lookup(row):
        h = str(row["home"]).lower()[:12]
        a = str(row["away"]).lower()[:12]
        d = str(row["date"])[:10]
        # Dokładne dopasowanie
        v = xg_map.get((h, a, d))
        if v:
            return pd.Series({"xg_home": v[0], "xg_away": v[1]})
        # ±1 dzień
        for offset in (-1, 1):
            try:
                d2 = (pd.Timestamp(d) + pd.Timedelta(days=offset)).strftime("%Y-%m-%d")
                v = xg_map.get((h, a, d2))
                if v:
                    return pd.Series({"xg_home": v[0], "xg_away": v[1]})
            except (ValueError, TypeError):
                pass
        return pd.Series({"xg_home": pd.NA, "xg_away": pd.NA})

    # Uzupełnij tylko wiersze bez xG
    mask = df_main["xg_home"].isna()
    if mask.any():
        updates = df_main[mask].apply(_lookup, axis=1)
        df_main.loc[mask, "xg_home"] = updates["xg_home"].values
        df_main.loc[mask, "xg_away"] = updates["xg_away"].values

    n_filled = df_main["xg_home"].notna().sum()
    log.info("xG uzupełnione: %d meczów", n_filled)
    return df_main


# ─────────────────────── strażnik jakości datasetu ────────────────────────

# Kolumny, których ubytek realnie zwęża pomiar — nie wszystkie, jakie są w zbiorze.
# `odds_*` niosą ramię RYNKOWE walk-forwardu (`wf_harness.predict_one` je devigauje),
# `hst`/`ast` wchodzą do λ przez `form.sily_ligowe` (WAGA_STRZALOW).
_KOLUMNY_PILNOWANE = ("odds_h", "odds_d", "odds_a", "odds_over25", "hst", "ast")

# O ile punktów procentowych może spaść pokrycie kolumny w JEDNEJ lidze, zanim
# uznamy to za incydent. Skala wzięta z realnych zdarzeń, nie z sufitu: jeden
# sezon znikający z pliku obejmującego jedenaście to ~9 pp i jest najmniejszą
# zmianą, którą chcemy zobaczyć; pojedynczy poprawiony u źródła mecz przesuwa
# pokrycie o ułamek punktu. Ten sam próg stosujemy do liczby meczów w lidze.
_PROG_REGRESJI = 0.05


def regresje_datasetu(stary: pd.DataFrame, nowy: pd.DataFrame) -> list[str]:
    """Lista ubytków nowego zbioru wobec poprzedniego. Pusta = wszystko w porządku.

    Porównanie idzie PER LIGA, bo liga jest jednostką, w której źródło wymienia
    pliki. Suma globalna zamaskowała incydent z 2026-09-03: `new/JPN.csv` dostał
    dołożone, prawie puste kolumny B365C*, przez co Japonia straciła kursy
    w 4353 meczach — ale 39 pozostałych lig w tym samym odświeżeniu urosło,
    więc globalnie wyszło −3347 (3.8%), czyli tyle, ile łatwo wziąć za
    wahliwość źródła. Plik miał przy tym WIĘCEJ wierszy niż poprzedni, komplet
    40 lig i świeższą datę ostatniego meczu.

    Świadomie nie robimy merge'u ze starym zbiorem: dopisałby Japonii kursy
    z poprzedniej wersji i przyczyna (parser biorący pustą kolumnę) nigdy by
    nie wypłynęła. Strażnik ma pokazać sprawę, nie zakleić.

    ZNANE OGRANICZENIE: porównanie jest z wersją BEZPOŚREDNIO poprzednią, więc
    łapie ubytek skokowy, a nie powolne wykrwawianie. Liga tracąca 0.2 pp
    pokrycia tygodniowo przejdzie sto razy i po roku zostanie bez 10 pp. Na to
    trzeba osobnego pomiaru wobec punktu odniesienia sprzed sezonu — tutaj
    świadomie tego nie ma, bo pilnujemy klasy błędu, którą realnie trafiliśmy.
    """
    if stary is None or stary.empty or "league" not in stary.columns:
        return []

    problemy: list[str] = []
    ligi_stare = set(stary["league"].dropna())
    ligi_nowe = set(nowy["league"].dropna()) if "league" in nowy.columns else set()

    for liga in sorted(ligi_stare - ligi_nowe):
        problemy.append(f"{liga}: liga zniknela ze zbioru ({int((stary['league'] == liga).sum())} meczow)")

    for liga in sorted(ligi_stare & ligi_nowe):
        s = stary[stary["league"] == liga]
        n = nowy[nowy["league"] == liga]
        if len(s) and (len(s) - len(n)) / len(s) > _PROG_REGRESJI:
            problemy.append(f"{liga}: meczow {len(s)} -> {len(n)}")

        for kol in _KOLUMNY_PILNOWANE:
            if kol not in s.columns or kol not in n.columns or not len(s) or not len(n):
                continue
            p_stare = float(s[kol].notna().mean())
            p_nowe = float(n[kol].notna().mean())
            if p_stare - p_nowe > _PROG_REGRESJI:
                problemy.append(
                    f"{liga}: pokrycie {kol} {100 * p_stare:.1f}% -> {100 * p_nowe:.1f}%"
                    f" ({int(s[kol].notna().sum())} -> {int(n[kol].notna().sum())} meczow)"
                )

    return problemy


# ─────────────────────────── główna funkcja ───────────────────────────────

def download_all(
    fdco_leagues: list[str] | None = None,
    fdco_seasons: list[str] | None = None,
    fdco_new_countries: list[str] | None = None,
    include_xgabora: bool = False,
    include_xg: bool = False,
    xg_leagues: list[str] | None = None,
    xg_seasons: list[str] | None = None,
    pozwol_na_regresje: bool = False,
) -> pd.DataFrame:
    """
    Pobiera dane ze wszystkich źródeł i łączy w jeden DataFrame.

    Domyślny zakres = dokładnie to, z czego zbudowany jest `full_dataset.parquet`
    na produkcji: WSZYSTKIE klucze `FDCO_LEAGUES` (22) i `FDCO_NEW_LEAGUES` (16),
    ostatnie `LICZBA_SEZONOW` sezonów, BEZ xgabora. Część plików `new/` trzyma
    po dwie rozgrywki, więc w zbiorze wychodzi 40 lig.

    `pozwol_na_regresje=True` przepuszcza zapis mimo ubytku wobec poprzedniego
    pliku — do świadomej decyzji człowieka, gdy źródło naprawdę usunęło ligę.

    Wcześniej domyślne były `["N1"]` + `["POL"]` + xgabora, więc odświeżenie
    danych wywołaniem bez argumentów ścinało dataset z 10 lig do 2 i dokładało
    źródło nazywające ligi kodami ("E0" zamiast "ENG-Premier League") — ten sam
    mecz trafiał do zbioru dwa razy, pod dwiema nazwami ligi.
    """
    frames = []

    print("[HistLoader] Pobieram football-data.co.uk (sezony)...")
    df_fdco = download_fdco_seasons(
        leagues=fdco_leagues or list(FDCO_LEAGUES.keys()),
        seasons=fdco_seasons or ostatnie_sezony(),
    )
    if not df_fdco.empty:
        print(f"  -> {len(df_fdco)} meczow (fdco_season)")
        frames.append(df_fdco)

    print("[HistLoader] Pobieram football-data.co.uk (nowy format)...")
    df_new = download_fdco_new(countries=fdco_new_countries or list(FDCO_NEW_LEAGUES.keys()))
    if not df_new.empty:
        print(f"  -> {len(df_new)} meczow (fdco_new)")
        frames.append(df_new)

    if include_xgabora:
        print("[HistLoader] Pobieram xgabora dataset (226k meczow)...")
        df_xgab = download_xgabora()
        if not df_xgab.empty:
            print(f"  -> {len(df_xgab)} meczow (xgabora)")
            frames.append(df_xgab)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "home", "away"])
    df = df.sort_values("date").reset_index(drop=True)

    # Totale
    df["total_goals"] = df["hg"] + df["ag"]
    df["over25"]  = (df["total_goals"] > 2.5).astype(float)
    df["over15"]  = (df["total_goals"] > 1.5).astype(float)
    df["btts"]    = ((df["hg"] > 0) & (df["ag"] > 0)).astype(float)

    # Opcjonalne: xG z FBref
    if include_xg:
        print("[HistLoader] Pobieram xG z FBref (soccerdata)...")
        df_xg = download_fbref_xg(
            leagues=xg_leagues or FBREF_DEFAULT_LEAGUES,
            seasons=xg_seasons or FBREF_DEFAULT_SEASONS,
        )
        if not df_xg.empty:
            n_before = df["xg_home"].notna().sum() if "xg_home" in df.columns else 0
            df = merge_xg_into_dataset(df, df_xg)
            n_after = df["xg_home"].notna().sum()
            print(f"  -> xG uzupelnione: {n_after - n_before} meczow")
        else:
            print("  -> brak danych xG (soccerdata niedostepne lub brak polaczenia)")

    # Strażnik PRZED zapisem: nowy zbiór nie może być uboższy od tego, który
    # już mamy. Kolejność ma znaczenie — „zapisz, potem zaloguj ostrzeżenie"
    # to dokładnie tryb, w którym incydent JPN (patrz `regresje_datasetu`)
    # przeżył cały dzień na produkcji.
    out_f = CACHE_DIR / "full_dataset.parquet"
    if out_f.exists():
        try:
            poprzedni = pd.read_parquet(out_f)
        except (OSError, ValueError) as e:
            # Nieczytelny poprzednik nie może blokować odświeżenia, ale musi być
            # słyszalny: tracimy wtedy jedyny punkt odniesienia dla porównania.
            log.warning("Nie da sie odczytac poprzedniego datasetu (%s: %s)"
                        " — zapis BEZ sprawdzenia regresji", type(e).__name__, e)
            poprzedni = None
        if poprzedni is not None:
            problemy = regresje_datasetu(poprzedni, df)
            if problemy:
                opis = "\n  - ".join(problemy)
                if not pozwol_na_regresje:
                    raise ValueError(
                        f"Nowy dataset jest UBOZSZY od obecnego — nie nadpisuje {out_f}.\n"
                        f"  - {opis}\n"
                        "Sprawdz zrodlo (czy nie zmienilo kolumn), a gdy ubytek jest"
                        " uzasadniony, powtorz z download_all(pozwol_na_regresje=True)."
                    )
                log.warning("Regresja datasetu przepuszczona swiadomie:\n  - %s", opis)

    df.to_parquet(out_f, index=False)
    print(f"\n[HistLoader] Lacznie: {len(df):,} meczow -> zapisano do {out_f}")
    return df


def load_cached(z_af: bool = True) -> pd.DataFrame:
    """Wczytuje pełny dataset z dysku (bez pobierania), scalony ze statystykami AF.

    Statystyki meczowe z API-Football leżą w OSOBNYM pliku (`af_stats.parquet`),
    bo ta funkcja czyta plik, który `download_all()` nadpisuje w całości — patrz
    docstring `footstats.data.af_stats`. Scalenie przy odczycie jest jedynym
    miejscem, którego cotygodniowe odświeżenie danych nie może skasować.

    `z_af=False` oddaje surowy parquet. Potrzebne wyłącznie do pomiaru A/B:
    oba ramiona muszą iść z TEGO SAMEGO pliku i różnić się dokładnie jedną rzeczą.
    """
    f = CACHE_DIR / "full_dataset.parquet"
    if not f.exists():
        raise FileNotFoundError(f"Brak cache. Uruchom najpierw download_all(). Szukałem w: {f}")
    df = pd.read_parquet(f)
    if not z_af:
        return df

    # Import lokalny — `af_stats` bierze stąd `CACHE_DIR`, więc na poziomie
    # modułu byłby to cykl.
    from footstats.data.af_stats import raport_pokrycia, scal_statystyki

    przed = raport_pokrycia(df)
    df = scal_statystyki(df)
    po = raport_pokrycia(df)
    # Log jest tu po to, żeby BRAK pliku w obrazie nie wyglądał identycznie jak
    # liga, która strzałów po prostu nie ma. To dwa różne stany i pomylenie ich
    # kosztowało już ten projekt cicho zdegradowaną λ w połowie lig.
    log.info(
        "Dataset %d meczow | pokrycie strzalow hst %.1f%% -> %.1f%%, ast %.1f%% -> %.1f%%",
        len(df), 100 * przed["hst"], 100 * po["hst"],
        100 * przed["ast"], 100 * po["ast"],
    )
    return df
