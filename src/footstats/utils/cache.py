import json
import logging
import os
import time
from datetime import datetime
from footstats.utils.paths import katalog_cache
from footstats.config import CACHE_TTL_MIN
from footstats.utils.console import console

# ================================================================
#  MODUL 3 - HTTP + CACHE + RATE GUARD  (v2.7.1)
# ================================================================
#
#  Strategia cache dla 3 zrodel:
#
#    football-data.org  →  pamiec RAM,  TTL = CACHE_TTL_MIN  (30 min)
#    api-sports.io      →  dysk JSON,   TTL = 24h (1 req = 1% budzetu!)
#    sports.bzzoiro.com →  pamiec RAM,  TTL = CACHE_TTL_MIN  (30 min)
#
#  api-sports.io: 100 req/dzien = OSZCZEDNOSC KRYTYCZNA:
#    - Zawsze najpierw sprawdzaj dysk, potem siec
#    - TTL 24h: dane z wczoraj wciaz wazne dla historii/tabeli
#    - Nadpisuj tylko gdy dane sie roznia (n meczow, pozycje tabeli)
#    - Licznik dzienny: zapisany na dysku, reset o polnocy
#    - Ostrzezenie gdy < 20 req pozostalo
#    - BLOKADA gdy < 5 req (rezerwowe na krytyczne zapytania)
# ================================================================

log = logging.getLogger(__name__)

# Ostrzegamy RAZ NA PROCES, nie przy kazdym zapytaniu: `_af_load_disk_cache`
# wola sie per request (do 100/dzien), a uszkodzony plik jest stanem TRWALYM —
# setna kopia tej samej linii nie wnosi nic, a topi reszte logu.
_zgloszono_brak_katalogu = False
_zgloszono_uszkodzony_plik = False

_RAM_CACHE: dict = {}   # football-data.org + bzzoiro (in-memory)
MAX_RAM_ENTRIES = 200

CACHE_DIR     = katalog_cache("api_football")
AF_CACHE_FILE = CACHE_DIR / "af_cache.json"      # dane API-Football
AF_BUDGET_FILE= CACHE_DIR / "af_budget.json"      # licznik dzienny

AF_CACHE_TTL_H   = 24    # Disk cache TTL dla API-Football (godziny)

# Dzienny budzet API-Football. 100 to byl limit planu Free; od 2026-09-02 konto
# jest na planie **Pro** — zmierzone przez `/status`:
#   {"plan": "Pro", "active": true, "requests": {"limit_day": 7500}}
#   naglowki: x-ratelimit-limit: 300 (na MINUTE), x-ratelimit-requests-limit: 7500
# Stara wartosc 100 nie powodowalaby bledow, tylko CICHE dlawienie: `_get`
# oddaje wtedy wygasle dane z cache zamiast pytac siec, wiec potok wygladalby
# zdrowo jadac na wczorajszych danych. Czytane z env, zeby zmiana planu nie
# wymagala redeployu kodu.
AF_BUDGET_DAILY  = int(os.getenv("AF_BUDGET_DAILY", "7500"))

# Progi wyprowadzone z budzetu, nie wpisane osobno — przy dwoch niezaleznych
# liczbach zmiana planu poprawialaby jedna i zostawiala druga (20 pozostalych
# z 7500 to nie jest "ostrzezenie", to zaokraglenie).
AF_WARN_THRESHOLD  = max(20, AF_BUDGET_DAILY // 5)    # ostrzegaj gdy tyle req zostalo
AF_BLOCK_THRESHOLD = max(5, AF_BUDGET_DAILY // 20)    # blokuj automaty gdy tyle zostalo

# ── Rate guard (football-data.org, 10 req/min) ──────────────────────

_req_count = 0
_req_window_start = datetime.now()

def _rate_guard():
    global _req_count, _req_window_start
    now   = datetime.now()
    delta = (now - _req_window_start).total_seconds()
    if delta >= 60:
        _req_count = 0
        _req_window_start = now
    _req_count += 1
    if _req_count >= 9 and delta < 60:
        czekaj = int(61 - delta)
        console.print(
            f"[bold yellow]Zbliżamy sie do limitu API (9/min). "
            f"Czekam {czekaj}s...[/bold yellow]"
        )
        time.sleep(czekaj + 1)
        _req_count = 1
        _req_window_start = datetime.now()

# ── RAM cache (FDB + Bzzoiro) ────────────────────────────────────────

def _cache_get(klucz: str):
    wpis = _RAM_CACHE.get(klucz)
    if wpis:
        delta = (datetime.now() - wpis["ts"]).total_seconds()
        if delta < CACHE_TTL_MIN * 60:
            console.print(f"[dim cyan]Cache HIT [{int(delta//60)}min]: {klucz[:55]}[/dim cyan]")
            return wpis["data"]
    return None

def uniewaznij_cache(prefiks: str) -> int:
    """
    Usuwa z cache'u RAM wpisy o danym prefiksie klucza. Zwraca ile usunięto.

    Po co: `CACHE_TTL_MIN` = 30 minut, a KROK 1 i KROK 3b dziennego agenta
    chodzą w TYM SAMYM procesie, w odstępie kilku-kilkunastu minut. Drugie
    zapytanie trafiało więc w cache i porównywało bajt w bajt te same dane —
    `Odswiezono kursy LIVE: 0/46` było gwarantowane konstrukcją, nie
    obserwacją rynku.

    Pusty prefiks jest odrzucany: pasowałby do każdego klucza i po cichu
    wyczyściłby cały cache, w tym wpisy API-Football, gdzie jedno zapytanie
    to 1% dziennego budżetu.
    """
    if not prefiks:
        raise ValueError(
            "uniewaznij_cache wymaga niepustego prefiksu — pusty skasowalby "
            "caly cache, w tym drogie wpisy API-Football"
        )
    do_usuniecia = [k for k in _RAM_CACHE if k.startswith(prefiks)]
    for k in do_usuniecia:
        del _RAM_CACHE[k]
    if do_usuniecia:
        log.debug("Cache: uniewazniono %d wpisow o prefiksie %r",
                  len(do_usuniecia), prefiks)
    return len(do_usuniecia)


def _ram_cache_cleanup(ttl_minutes: int = 60):
    """Remove expired entries from RAM cache."""
    now = datetime.now()
    expired = [k for k, v in _RAM_CACHE.items()
               if (now - v["ts"]).total_seconds() > ttl_minutes * 60]
    for k in expired:
        del _RAM_CACHE[k]
    if expired:
        console.print(f"[dim]RAM Cache cleanup: removed {len(expired)} expired entries[/dim]")

def _cache_set(klucz: str, dane):
    if len(_RAM_CACHE) >= MAX_RAM_ENTRIES:
        oldest_key = min(_RAM_CACHE.keys(), key=lambda k: _RAM_CACHE[k]["ts"])
        del _RAM_CACHE[oldest_key]
        console.print(f"[dim]RAM Cache evicted oldest: {oldest_key[:40]}[/dim]")
    _RAM_CACHE[klucz] = {"ts": datetime.now(), "data": dane}

# ── Disk cache (API-Football, TTL 24h) ──────────────────────────────

def _af_ensure_dir():
    global _zgloszono_brak_katalogu
    try:
        CACHE_DIR.mkdir(exist_ok=True)
    except OSError as e:
        if not _zgloszono_brak_katalogu:
            # Bez katalogu KAZDY zapis cache pada po cichu, wiec kazde zapytanie
            # idzie do sieci i zjada dzienny budzet API-Football (100 req).
            log.warning("Nie moge zalozyc %s (%s) — cache dyskowy NIE DZIALA,"
                        " kazde zapytanie zuzyje budzet API", CACHE_DIR, e)
            _zgloszono_brak_katalogu = True

def _af_load_disk_cache() -> dict:
    """Laduje caly plik cache z dysku."""
    _af_ensure_dir()
    if AF_CACHE_FILE.exists():
        try:
            return json.loads(AF_CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            global _zgloszono_uszkodzony_plik
            if not _zgloszono_uszkodzony_plik:
                # `{}` znaczy "cache pusty", czyli to samo co pierwszy przebieg.
                # Roznica jest zasadnicza: uszkodzony plik NIE naprawi sie sam
                # i kazde zapytanie bedzie szlo do sieci az ktos go skasuje.
                log.warning("Plik cache %s nie do odczytania (%s) — traktuje jak"
                            " PUSTY; skasuj go, inaczej budzet API bedzie ginal",
                            AF_CACHE_FILE, e)
                _zgloszono_uszkodzony_plik = True
            return {}
    return {}

def _af_save_disk_cache(cache: dict):
    """Zapisuje cache na dysk."""
    _af_ensure_dir()
    try:
        AF_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=None, separators=(',',':')),
            encoding="utf-8"
        )
    except OSError as e:
        console.print(f"[yellow]Cache: zapis dysku nieudany: {e}[/yellow]")

def _af_cache_get(klucz: str) -> dict | None:
    """
    Sprawdza disk cache API-Football.
    Zwraca dane jesli istnieja i TTL < 24h. Inaczej None.
    """
    cache = _af_load_disk_cache()
    wpis  = cache.get(klucz)
    if not wpis:
        return None
    try:
        ts    = datetime.fromisoformat(wpis["ts"])
        delta = (datetime.now() - ts).total_seconds()
        if delta < AF_CACHE_TTL_H * 3600:
            wiek_h = int(delta // 3600)
            wiek_m = int((delta % 3600) // 60)
            console.print(
                f"[dim yellow]💾 AF Cache HIT "
                f"[{wiek_h}h {wiek_m}min]: {klucz[:55]}[/dim yellow]"
            )
            return wpis["data"]
    except (ValueError, KeyError) as e:
        # Wpis JEST, ale nie umiemy odczytac jego wieku — traktujemy jak brak,
        # czyli platne zapytanie do API. Cicho wygladalo to jak zwykly cache MISS.
        log.warning("Wpis cache %r ma zepsuty znacznik czasu (%s: %s) —"
                    " traktuje jak MISS, poleci zapytanie do API", klucz[:55],
                    type(e).__name__, e)
    return None

def _af_cache_set(klucz: str, dane: dict, stare_dane: dict | None = None):
    """
    Zapisuje dane do disk cache API-Football.
    Jesli stare_dane podane: porownuje czy warto nadpisac
    (nadpisuje tylko jesli dane sie roznia lub sa bogatsze).
    """
    cache = _af_load_disk_cache()

    # Sprawdz czy warto nadpisac
    if stare_dane is not None and klucz in cache:
        # Prosta heurystyka: porownaj liczbe elementow odpowiedzi
        n_nowe = len(dane.get("response", dane)) if isinstance(dane, dict) else len(dane)
        n_star = len(stare_dane.get("response", stare_dane)) if isinstance(stare_dane, dict) else len(stare_dane)
        if n_nowe <= n_star:
            console.print(
                f"[dim]AF Cache: nowe dane ({n_nowe}) nie bogatsze niz stare "
                f"({n_star}) – zatrzymuje stary cache.[/dim]"
            )
            return  # Nie nadpisuj – oszczednosc reqow w przyszlosci

    cache[klucz] = {
        "ts":   datetime.now().isoformat(),
        "data": dane,
    }
    _af_save_disk_cache(cache)
    console.print(f"[dim yellow]💾 AF Cache SAVE: {klucz[:55]}[/dim yellow]")

def af_cache_info() -> dict:
    """Zwraca info o disk cache: liczba wpisow, rozmiar, najstarszy/najnowszy."""
    cache = _af_load_disk_cache()
    if not cache:
        return {"wpisy": 0, "rozmiar_kb": 0, "najstarszy": None, "najnowszy": None}
    tsy = []
    for w in cache.values():
        try:
            tsy.append(datetime.fromisoformat(w["ts"]))
        except (ValueError, KeyError):
            # CISZA CELOWA: to funkcja STATYSTYCZNA (ile wpisow, najstarszy,
            # najnowszy). Zepsuty wpis wypada z licznika i nie wplywa na zadna
            # decyzje — o samym zepsuciu glosno mowi juz `_af_cache_get`.
            pass
    rozm = AF_CACHE_FILE.stat().st_size // 1024 if AF_CACHE_FILE.exists() else 0
    return {
        "wpisy":     len(cache),
        "rozmiar_kb": rozm,
        "najstarszy": min(tsy).strftime("%d.%m %H:%M") if tsy else None,
        "najnowszy":  max(tsy).strftime("%d.%m %H:%M") if tsy else None,
    }

def af_cache_clear():
    """Usuwa caly disk cache API-Football."""
    if AF_CACHE_FILE.exists():
        AF_CACHE_FILE.unlink()
        console.print("[yellow]Disk cache API-Football wyczyszczony.[/yellow]")

# ── Budzet dzienny API-Football ──────────────────────────────────────

def _af_budget_load() -> dict:
    """Laduje stan budzetu z dysku."""
    _af_ensure_dir()
    if AF_BUDGET_FILE.exists():
        try:
            d = json.loads(AF_BUDGET_FILE.read_text(encoding="utf-8"))
            # Reset o polnocy
            dzien = d.get("dzien", "")
            if dzien != datetime.now().strftime("%Y-%m-%d"):
                return {"dzien": datetime.now().strftime("%Y-%m-%d"), "uzyto": 0, "historia": []}
            return d
        except (OSError, ValueError):
            console.print("[yellow]Cache: błąd odczytu budżetu AF — reset do zera.[/yellow]")
    return {"dzien": datetime.now().strftime("%Y-%m-%d"), "uzyto": 0, "historia": []}

def _af_budget_save(budzet: dict):
    _af_ensure_dir()
    try:
        AF_BUDGET_FILE.write_text(
            json.dumps(budzet, ensure_ascii=False, separators=(',',':')),
            encoding="utf-8"
        )
    except OSError as e:
        console.print(f"[yellow]Cache: zapis budżetu nieudany: {e}[/yellow]")

# af_budget_use() usunieta 2026-07-30 — zastapiona przez
# utils/logging.bezpieczny_budget_use (typed BladBudzetu + pelne logowanie stanu).
# Swap zrobiony w commicie 25f6bc92a, ale stara funkcja zostala; CHANGELOG:433
# oznaczal ja jako "martwy w prod, kandydat do usuniecia". Ten sam plik budzetu
# i te same progi, wiec liczniki sie nie rozjezdzaja.

def af_budget_status() -> dict:
    """Zwraca aktualny status budzetu."""
    b = _af_budget_load()
    uzyto     = b.get("uzyto", 0)
    pozostalo = max(0, AF_BUDGET_DAILY - uzyto)
    return {
        "dzien":     b.get("dzien", "?"),
        "uzyto":     uzyto,
        "pozostalo": pozostalo,
        "limit":     AF_BUDGET_DAILY,
        "procent":   round(uzyto / AF_BUDGET_DAILY * 100, 1),
        "historia":  b.get("historia", [])[-5:],   # ostatnie 5
        "krytyczny": pozostalo < AF_BLOCK_THRESHOLD,
        "ostrzezenie": pozostalo < AF_WARN_THRESHOLD,
    }
