import logging

import requests
import pandas as pd
from datetime import datetime
from statistics import median
from footstats.utils.cache import (
    _af_cache_get, _af_cache_set, af_budget_status,
    _af_load_disk_cache, _af_budget_load, _af_budget_save,
    AF_BUDGET_DAILY, AF_WARN_THRESHOLD, AF_BLOCK_THRESHOLD,
)
from footstats.utils.logging import bezpieczny_budget_use, BladBudzetu
from footstats.utils.console import console
from footstats.utils.helpers import _s
from footstats.utils.normalize import (
    PROG_DOPASOWANIA_MECZU,
    normalize_team_name,
    team_similarity,
)

log = logging.getLogger(__name__)

# ================================================================
#  MODUL 4b – API-FOOTBALL (api-sports.io) v2.7
#  Darmowy plan: 100 req/dzien, 1200+ lig (Ekstraklasa, MLS, Saudi...)
# ================================================================

# Mapowanie nazw lig API-Football na wewnetrzne kody i id
_APISPORTS_LIGI = {
    # id : {kod_wewn, nazwa, kraj, druzyny}
    39:  {"kod": "PL",  "nazwa": "Premier League",        "kraj": "England",     "druzyny": 20},
    140: {"kod": "PD",  "nazwa": "Primera Division",       "kraj": "Spain",       "druzyny": 20},
    135: {"kod": "SA",  "nazwa": "Serie A",                "kraj": "Italy",       "druzyny": 20},
    78:  {"kod": "BL1", "nazwa": "Bundesliga",             "kraj": "Germany",     "druzyny": 18},
    61:  {"kod": "FL1", "nazwa": "Ligue 1",                "kraj": "France",      "druzyny": 18},
    94:  {"kod": "PPL", "nazwa": "Primeira Liga",          "kraj": "Portugal",    "druzyny": 18},
    88:  {"kod": "DED", "nazwa": "Eredivisie",             "kraj": "Netherlands", "druzyny": 18},
    40:  {"kod": "ELC", "nazwa": "Championship",           "kraj": "England",     "druzyny": 24},
    2:   {"kod": "CL",  "nazwa": "UEFA Champions League",  "kraj": "Europe",      "druzyny": 36},
    71:  {"kod": "BSA", "nazwa": "Brasileirao Serie A",    "kraj": "Brazil",      "druzyny": 20},
    106: {"kod": "EKS", "nazwa": "PKO BP Ekstraklasa",     "kraj": "Poland",      "druzyny": 18},
    253: {"kod": "MLS", "nazwa": "MLS",                    "kraj": "USA",         "druzyny": 29},
    307: {"kod": "SPL", "nazwa": "Saudi Pro League",       "kraj": "Saudi Arabia","druzyny": 18},
    262: {"kod": "LMX", "nazwa": "Liga MX",                "kraj": "Mexico",      "druzyny": 18},
    144: {"kod": "PRO", "nazwa": "Pro League",             "kraj": "Belgium",     "druzyny": 18},
    179: {"kod": "SPO", "nazwa": "Scottish Premiership",   "kraj": "Scotland",    "druzyny": 12},
}

# Jedna definicja, dwa uzycia (tu i w bramce). Wczesniej detekcja bledu konta
# zyla wylacznie w tym pliku, wiec piec surowych `requests.get` w
# `results_updater`/`evening_agent` nie rozpoznawalo zawieszenia w ogole.
from footstats.core.apisports_gate import blad_konta as _blad_konta  # noqa: E402


class APIFootball:
    """
    Klient api-sports.io (API-Football).
    Darmowy: 100 req/dzien, wszystkie endpointy, 1200+ lig.
    Header: x-apisports-key: KEY
    """
    BASE = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str):
        self.headers = {"x-apisports-key": api_key}
        self._valid: bool | None = None
        self._req_today: int = 0

    def waliduj(self) -> tuple[bool, str]:
        """
        Sprawdza klucz przez /status endpoint (1 req).
        Pobiera tez aktualny licznik reqow z serwera (nadrzedny vs nasz lokalny).
        """
        try:
            r = requests.get(f"{self.BASE}/status",
                             headers=self.headers, timeout=15)
            if r.status_code == 200:
                surowe = r.json()

                # Zawieszone konto / zly klucz wracaja jako HTTP 200 z `errors`,
                # a `response` jest wtedy PUSTA LISTA. Wczesniej kod robil na niej
                # `.get()` i leciał nieprzechwyconym AttributeError — a
                # `SourceManager` tego nie lapie, wiec CLI padalo przy starcie.
                blad = _blad_konta(surowe)
                if blad:
                    self._valid = False
                    return False, blad

                d = surowe.get("response") or {}
                if not isinstance(d, dict):
                    self._valid = False
                    return False, "nieoczekiwany format odpowiedzi /status"
                used = d.get("requests", {}).get("current", 0)
                lim  = d.get("requests", {}).get("limit_day", 100)
                self._req_today = used
                self._valid = True

                # Zsynchronizuj lokalny licznik z serwerowym (serwer jest prawda)
                bud = _af_budget_load()
                if used > bud.get("uzyto", 0):
                    bud["uzyto"] = used
                    _af_budget_save(bud)

                pozostalo = lim - used
                kol = "green" if pozostalo > AF_WARN_THRESHOLD else (
                      "yellow" if pozostalo > AF_BLOCK_THRESHOLD else "red")
                return True, (f"[{kol}]OK – {used}/{lim} req/dzien | "
                              f"pozostalo: {pozostalo}[/{kol}]")

            elif r.status_code == 401:
                self._valid = False
                return False, "Nieprawidlowy klucz API-Football (401)"
            else:
                self._valid = False
                return False, f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError, KeyError) as e:
            self._valid = False
            return False, str(e)

    def _get(self, endpoint: str, params: dict = None,
             force_network: bool = False) -> dict | None:
        """
        Pobiera dane z API-Football z pelna strategia oszczedzania:
          1. Sprawdz disk cache (TTL 24h) – bez zadnego requesta
          2. Jesli cache wazny: uzyj bez pytania sieci
          3. Jesli cache wygasl / brak:
             a. Sprawdz budzet (< AF_BLOCK_THRESHOLD = blokada)
             b. Wyslij request, zrejestruj w budzecie
             c. Zapisz na dysk (porownaj z starym przed nadpisaniem)
        force_network=True: pomija cache i pobiera swiezo (uzywa requesta).
        """
        cache_key = f"af:{endpoint}:{params}"

        # 1. Disk cache – zawsze proba. PRZED bramka: cache to nasze wlasne dane,
        # a nie ruch do dostawcy, wiec zamknieta bramka nie ma powodu go odcinac.
        if not force_network:
            cached = _af_cache_get(cache_key)
            if cached is not None:
                return cached

        # 1b. Bramka (`core.apisports_gate`) — jedyne miejsce decydujace, czy
        # w ogole wolno ruszyc siec. Zatrzaskuje sie sama po blokadzie konta.
        from footstats.core.apisports_gate import wlaczone as _af_wlaczone

        if not _af_wlaczone():
            log.info("API-Football wylaczony przez bramke — %s bez zapytania", endpoint)
            return None

        # 2. Sprawdz budzet zanim wykonamy request
        bud = af_budget_status()
        if bud["krytyczny"]:
            # Krytyczny budzet: zwroc co mamy (nawet wygasle), albo None
            stare = _af_load_disk_cache().get(cache_key, {}).get("data")
            if stare:
                console.print(
                    "[yellow]⚠️  Krytyczny budzet AF – uzywam wygaslych danych z cache.[/yellow]"
                )
                return stare
            console.print("[bold red]⛔ Brak cache i budzet krytyczny – pominięto.[/bold red]")
            return None

        # 3. Wyslij request
        try:
            pozostalo = bezpieczny_budget_use(endpoint)
        except BladBudzetu:
            # Budzet zablokowany – sprobuj wygasle dane.
            # Wolajacy NIE MA jak odroznic swiezej odpowiedzi od wygaslej kopii,
            # wiec bez tego logu potok jedzie na starych danych i wyglada zdrowo.
            stare = _af_load_disk_cache().get(cache_key, {}).get("data")
            log.warning("Budzet API-Football wyczerpany dla %s — oddaje %s",
                        endpoint,
                        "WYGASLE dane z cache" if stare else "None (brak cache)")
            return stare

        try:
            r = requests.get(
                f"{self.BASE}{endpoint}",
                headers=self.headers, params=params, timeout=15
            )
            self._req_today += 1

            if r.status_code == 200:
                data = r.json()

                # api-sports NIE uzywa kodow HTTP do problemow z kontem —
                # zawieszenie, zly klucz i przekroczony plan wracaja jako
                # HTTP 200 z {"errors": {...}, "response": []}. Bez tej kontroli
                # pusta odpowiedz szla do cache na 24h (awaria konta psula dane
                # jeszcze dlugo po jej usunieciu), a wolajacy bral `response: []`
                # za "brak meczow dzis". Patrz `_blad_konta`.
                blad = _blad_konta(data)
                if blad:
                    self._valid = False
                    # Blokada konta zatrzaskuje bramke dla CALEGO procesu —
                    # inaczej kazdy kolejny wolajacy powtarzalby ten sam
                    # odrzucony request az do konca doby.
                    from footstats.core.apisports_gate import zglos_odpowiedz

                    zglos_odpowiedz(data)
                    console.print(
                        f"[bold red]API-Football odrzucil zapytanie (HTTP 200): {blad}[/bold red]\n"
                        "[dim]Sprawdz konto na dashboard.api-football.com — "
                        "to nie jest chwilowa awaria sieci.[/dim]"
                    )
                    return None

                # Sprawdz stare dane przed zapisem
                stare = _af_load_disk_cache().get(cache_key, {}).get("data")
                _af_cache_set(cache_key, data, stare)
                console.print(
                    f"[dim]AF req uzyto: {bud['uzyto']+1}/{AF_BUDGET_DAILY} "
                    f"| pozostalo ~{pozostalo-1}[/dim]"
                )
                return data

            elif r.status_code == 429:
                console.print(
                    "[bold red]API-Football HTTP 429 – limit dzienny wyczerpany na serwerze![/bold red]\n"
                    "[dim]Dane beda dostepne jutro. Uzywam cache jesli dostepny.[/dim]"
                )
                stare = _af_load_disk_cache().get(cache_key, {}).get("data")
                return stare

            elif r.status_code in (401, 403):
                self._valid = False
                console.print(f"[red]API-Football: blad autoryzacji ({r.status_code})[/red]")
                return None

            return None

        except requests.exceptions.Timeout:
            console.print("[yellow]API-Football: timeout – uzywam cache.[/yellow]")
            stare = _af_load_disk_cache().get(cache_key, {}).get("data")
            return stare
        except (requests.RequestException, ValueError, KeyError) as e:
            console.print(f"[yellow]API-Football blad sieci: {e}[/yellow]")
            return None

    def ligi_dodatkowe(self) -> list:
        """Zwraca liste lig dostepnych przez API-Football (z predefiniowanej mapy)."""
        wynik = []
        for api_id, info in _APISPORTS_LIGI.items():
            wynik.append({
                "nazwa":   info["nazwa"],
                "kod":     info["kod"],
                "kraj":    info["kraj"],
                "druzyny": info["druzyny"],
                "api_id":  api_id,
                "zrodlo":  "api-sports.io",
            })
        return sorted(wynik, key=lambda x: x["nazwa"])

    def wyniki_liga(self, api_id: int, sezon: int = None) -> pd.DataFrame | None:
        """Pobiera wyniki dla ligi po api_id."""
        if sezon is None:
            sezon = datetime.now().year if datetime.now().month > 6 else datetime.now().year - 1
        dane = self._get("/fixtures", params={
            "league": api_id, "season": sezon, "status": "FT", "last": 100
        })
        if not dane:
            return None
        mecze = []
        for m in dane.get("response", []):
            goals = m.get("goals", {})
            gg, ga = goals.get("home"), goals.get("away")
            if gg is None or ga is None:
                continue
            teams = m.get("teams", {})
            gosp = _s(teams.get("home", {}).get("name"))
            gosc = _s(teams.get("away", {}).get("name"))
            date_str = m.get("fixture", {}).get("date", "")[:10]
            mecze.append({
                "data":        date_str,
                "data_full":   m.get("fixture", {}).get("date", date_str),
                "gospodarz":   gosp,
                "goscie":      gosc,
                "gole_g":      int(gg),
                "gole_a":      int(ga),
                "kolejka":     m.get("league", {}).get("round"),
                "stage":       "REGULAR_SEASON",
                "competition": _APISPORTS_LIGI.get(api_id, {}).get("kod", str(api_id)),
            })
        return pd.DataFrame(mecze) if mecze else None

    def nadchodzace_liga(self, api_id: int, sezon: int = None) -> pd.DataFrame | None:
        """Pobiera nadchodzace mecze dla ligi."""
        if sezon is None:
            sezon = datetime.now().year if datetime.now().month > 6 else datetime.now().year - 1
        dane = self._get("/fixtures", params={
            "league": api_id, "season": sezon, "status": "NS", "next": 40
        })
        if not dane:
            return None
        mecze = []
        for m in dane.get("response", []):
            teams   = m.get("teams", {})
            gosp    = _s(teams.get("home", {}).get("name"))
            gosc    = _s(teams.get("away", {}).get("name"))
            date_str= m.get("fixture", {}).get("date", "")[:10]
            mecze.append({
                "data":        date_str,
                "data_full":   m.get("fixture", {}).get("date", date_str),
                "godzina":     m.get("fixture", {}).get("date", "")[:16] + " UTC",
                "gospodarz":   gosp,
                "goscie":      gosc,
                "kolejka":     m.get("league", {}).get("round"),
                "stage":       "REGULAR_SEASON",
                "first_leg_g": None,
                "first_leg_a": None,
            })
        return pd.DataFrame(mecze) if mecze else None

    def tabela_liga(self, api_id: int, sezon: int = None) -> pd.DataFrame | None:
        """Pobiera tabele dla ligi."""
        if sezon is None:
            sezon = datetime.now().year if datetime.now().month > 6 else datetime.now().year - 1
        dane = self._get("/standings", params={"league": api_id, "season": sezon})
        if not dane:
            return None
        try:
            tabela = dane["response"][0]["league"]["standings"][0]
        except (IndexError, KeyError) as e:
            # Tak wyglada m.in. ZAWIESZONE konto: HTTP 200, pusta `response`.
            # 01.08 konto bylo suspended i potok cicho stracil tabele, sklady
            # i sedziego (patrz `project_apifootball_zawieszone`).
            log.warning("Odpowiedz /standings dla ligi %s sezon %s nie ma tabeli"
                        " (%s: %s) — liga zostaje BEZ tabeli",
                        api_id, sezon, type(e).__name__, e)
            return None
        wiersze = []
        for w in tabela:
            wiersze.append({
                "Poz.":    w["rank"],
                "Druzyna": _s(w["team"].get("name")),
                "M":       w["all"]["played"],
                "W":       w["all"]["win"],
                "R":       w["all"]["draw"],
                "P":       w["all"]["lose"],
                "BZ":      w["all"]["goals"]["for"],
                "BS":      w["all"]["goals"]["against"],
                "Bramki":  f"{w['all']['goals']['for']}:{w['all']['goals']['against']}",
                "+/-":     w["goalsDiff"],
                "Pkt":     w["points"],
            })
        return pd.DataFrame(wiersze) if wiersze else None

    def kandydaci_liga(
        self,
        api_id: int,
        godziny: int = 72,
        prog_pw: float = 0.50,
    ) -> list[dict]:
        """
        Pobiera nadchodzące mecze ligi + predykcje API-Football.
        Zwraca listę w formacie kompatybilnym z Bzzoiro (pw/pr/pp/o25/bt itd.)
        gotową do połączenia z wynikami szybkie_pewniaczki_2dni().

        api_id   – id ligi w API-Football (np. 106 = Ekstraklasa)
        godziny  – ile godzin do przodu (72 = 3 dni)
        prog_pw  – minimalny prog prawdopodobieństwa (0.50 = 50%)
        """
        from datetime import timezone
        sezon = datetime.now().year if datetime.now().month > 6 else datetime.now().year - 1

        # 1. Pobierz nadchodzące mecze
        dane = self._get("/fixtures", params={
            "league": api_id, "season": sezon, "status": "NS", "next": 20
        })
        if not dane:
            return []

        now_utc = datetime.now(timezone.utc)
        wyniki  = []

        for m in dane.get("response", []):
            # Filtruj po oknie czasowym
            date_str = m.get("fixture", {}).get("date", "")
            if not date_str:
                continue
            try:
                match_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                diff_h   = (match_dt - now_utc).total_seconds() / 3600
                if diff_h < 0 or diff_h > godziny:
                    continue
            except ValueError:
                log.warning("Mecz %s ma date %r nie do sparsowania — wypada z puli"
                            " kandydatow", m.get("fixture", {}).get("id"), date_str)
                continue

            fix_id   = m.get("fixture", {}).get("id")
            teams    = m.get("teams", {})
            gosp     = _s(teams.get("home", {}).get("name", ""))
            gosc     = _s(teams.get("away", {}).get("name", ""))
            liga_str = _APISPORTS_LIGI.get(api_id, {}).get("nazwa", str(api_id))

            # 2. Pobierz predykcje dla tego meczu (1 req/mecz)
            pred_data = self._get("/predictions", params={"fixture": fix_id})
            pw = pr = pp = o25 = bt = 50.0
            odds: dict = {}

            if pred_data:
                pred_list = pred_data.get("response", [])
                if pred_list:
                    p = pred_list[0]
                    pct = p.get("predictions", {}).get("percent", {})
                    try:
                        # WSZYSTKIE TRZY albo zadna. `pct.get(k, "50%") or "50%"`
                        # podstawialo domyslna wartosc PER POLE, wiec brak samego
                        # `away` dawal realne 60/20 obok domyslnego 25 — suma 105%.
                        brakujace = [k for k in ("home", "draw", "away")
                                     if not str(pct.get(k) or "").strip()]
                        if brakujace:
                            raise ValueError(f"brak pol: {brakujace}")
                        _pw = float(str(pct["home"]).replace("%", ""))
                        _pr = float(str(pct["draw"]).replace("%", ""))
                        _pp = float(str(pct["away"]).replace("%", ""))
                    except (ValueError, TypeError, KeyError) as e:
                        # WSZYSTKO ALBO NIC. Wczesniej przypisanie szlo wprost do
                        # pw/pr/pp, wiec blad na `draw` zostawial REALNE `pw` obok
                        # DOMYSLNYCH pr/pp (50/50) — mieszanka szla prosto do progu
                        # selekcji `max_p` i sumowala sie nawet do 150%.
                        # 50/50/50 to wartosci z resetu na poczatku iteracji,
                        # NIE "25%" z dawnych `pct.get(k, "25%")` — tamte nigdy
                        # nie byly osiagalne jako komplet.
                        log.warning("Predykcje API-Football dla meczu %s nie do"
                                    " odczytania (%s: %s) — zostaja wartosci"
                                    " domyslne 50/50/50, czyli BRAK sygnalu",
                                    fix_id, type(e).__name__, e)
                    else:
                        pw, pr, pp = _pw, _pr, _pp

                    # Kursy z predykcji API: brak w /predictions – zostawiamy puste

            # Filtruj po progu
            max_p = max(pw, pr, pp) / 100.0
            if max_p < prog_pw:
                continue

            wyniki.append({
                "gospodarz": gosp,
                "goscie":    gosc,
                "liga":      liga_str,
                "data":      date_str[:10],
                "godzina":   date_str[11:16],
                "pw":        pw,
                "pr":        pr,
                "pp":        pp,
                "o25":       o25,
                "bt":        bt,
                "odds":      odds,
                "metoda":    "API-Football",
                "typy": [
                    ("1", pw / 100),
                    ("X", pr / 100),
                    ("2", pp / 100),
                ],
            })

        return wyniki

    # Etykieta wartosci u dostawcy -> nasz klucz kursu. Jedna tabela zamiast
    # trzech galezi `if nazwa == ...`, zeby dodanie rynku bylo jedna linia.
    _RYNKI_AF: dict[str, dict[str, str]] = {
        "Match Winner": {"home": "home", "draw": "draw", "away": "away"},
        "Goals Over/Under": {"over 2.5": "over_2_5", "under 2.5": "under_2_5"},
        # Obie strony, nie tylko "yes". Bez "no" model moze typowac BTTS NIE,
        # ale nikt nie potrafi tego wycenic — noga byla kasowana po cichu (15.08).
        "Both Teams Score": {"yes": "btts", "no": "btts_no"},
    }

    def kursy_fixture(self, fix_id: int) -> dict:
        """
        Kursy bukmacherskie dla fixture'a przez /odds (1 req, cache'owane).

        Kurs rynku to MEDIANA wszystkich bukmacherow, ktorzy go notuja — nie kurs
        pierwszego z listy, jak bylo do 2026-09-03.

        ZMIERZONE na 20 meczach z naszych lig (Match Winner, strona gospodarza):

            max      vs pierwszy: +6.99%
            mediana  vs pierwszy: +0.61%   (mediana roznic 0.00%)
            Pinnacle vs pierwszy: +3.09%

        DLACZEGO NIE MAX, choc kusi: te kursy ida do EV, Kelly'ego, `total_odds`
        kuponu i ROI, wiec branie najlepszego z dwunastu podnioslby wynik
        paper-tradingu o ~7% bez jednego wygranego zakladu wiecej. To mechanizm,
        ktorym backtesty produkuja nieistniejacy edge — a tu jest juz zmierzone,
        ze przewagi nad rynkiem nie ma.

        DLACZEGO MEDIANA, skoro srednio nie zmienia nic: "pierwszy z listy" to nie
        jest zaden kurs, tylko kolejnosc, w jakiej dostawca zwrocil bukmacherow.
        Pojedyncze mecze roznia sie do 19%, a wynik potrafil sie zmienic bez zadnej
        zmiany po naszej stronie.

        I DRUGI, MOCNIEJSZY POWOD: `scrapers/odds_api.py` (The Odds API) agreguje
        mediana OD POCZATKU, z tym samym uzasadnieniem — "max zawyzalby EV kursem,
        ktorego user u swojego bukmachera nie dostanie". Oba zrodla wypelniaja TO
        SAMO pole `odds`, wiec ta sciezka byla po prostu odstepstwem: zapisany kurs
        zalezal od tego, ktore zrodlo akurat zadzialalo.

        ZBIERANIE OD WSZYSTKICH domyka tez luki: na 14 meczach `Goals Over/Under`
        byl u pierwszego bukmachera w 11, a u ktoregokolwiek w 14. Te 21% meczow
        traci lo kurs na Over/Under 2.5 mimo istniejacego rynku, a
        `system_paper.najlepszy_typ` pomija kazdy typ bez kursu.

        Pusty dict gdy brak danych/bukmacherow — zero falszywych wartosci.
        """
        dane = self._get("/odds", {"fixture": fix_id})
        if not dane:
            return {}

        response = dane.get("response", [])
        if not response:
            return {}

        zebrane: dict[str, list[float]] = {}
        for bookmaker in response[0].get("bookmakers", []):
            for bet in bookmaker.get("bets", []):
                etykiety = self._RYNKI_AF.get(bet.get("name", ""))
                if not etykiety:
                    continue
                for v in bet.get("values", []):
                    klucz = etykiety.get((v.get("value", "") or "").strip().lower())
                    if not klucz:
                        continue
                    odd = _parse_odd(v.get("odd"))
                    if odd is None:
                        continue
                    zebrane.setdefault(klucz, []).append(odd)

        return {k: round(median(sorted(v)), 2) for k, v in zebrane.items() if v}

    def znajdz_fixture_id(self, home: str, away: str, data: str) -> int | None:
        """
        Szuka fixture_id meczu home vs away w dniu `data` przez /fixtures?date=.

        Dopasowanie przez `team_similarity` (próg `PROG_DOPASOWANIA_MECZU`), NIE po
        podciągu. Podciąg uznawał rezerwy za pierwszy zespół — "Legia" łapała
        "Legia II" — a stąd biorą się KURSY i statystyki meczu. Rezerwy grają
        zwykle w ten sam dzień, więc oba mecze bywają w jednej odpowiedzi.

        Zwracany jest NAJLEPSZY kandydat, nie pierwszy napotkany: kolejność
        odpowiedzi API to nie ranking trafności.

        Cache wyniku odbywa się na poziomie _get (jeden request /fixtures na
        dzień, reużywany dla wielu meczów tego samego dnia).
        """
        dane = self._get("/fixtures", {"date": data[:10]})
        if not dane:
            return None

        najlepszy_id, najlepszy_wynik = None, 0.0
        for m in dane.get("response", []):
            teams = m.get("teams", {})
            fh = _s(teams.get("home", {}).get("name", ""))
            fa = _s(teams.get("away", {}).get("name", ""))
            if not normalize_team_name(fh) or not normalize_team_name(fa):
                continue

            wynik = min(team_similarity(home, fh), team_similarity(away, fa))
            if wynik >= PROG_DOPASOWANIA_MECZU and wynik > najlepszy_wynik:
                najlepszy_id, najlepszy_wynik = m.get("fixture", {}).get("id"), wynik

        return najlepszy_id


def _parse_odd(raw: str | float | None) -> float | None:
    """Konwertuje surowy kurs decimal z API-Football (string) na float. None gdy niepoprawny."""
    if raw is None:
        return None            # brak kursu to stan normalny, nie awaria
    try:
        return float(raw)
    except (ValueError, TypeError):
        # Wartosc JEST, tylko nie jest liczba — to juz nie jest brak danych.
        log.warning("Kurs %r z API-Football nie jest liczba — traktuje jak brak", raw)
        return None


def fetch_odds_af(home: str, away: str, data: str) -> dict | None:
    """
    Fallback kursów przez API-Football /odds — alternatywa dla SofaScore (403 anti-bot).

    Reużywa istniejącego klucza APISPORTS_KEY + wbudowany budżet/cache klienta
    APIFootball. Zwraca dict {home, draw, away, over_2_5, under_2_5, btts}
    (tylko realnie znalezione rynki) albo None gdy brak klucza/meczu/kursów.
    """
    from footstats.core.apisports_gate import klucz as _klucz_af

    klucz = _klucz_af()
    if not klucz:
        return None

    klient = APIFootball(klucz)
    fix_id = klient.znajdz_fixture_id(home, away, data)
    if fix_id is None:
        return None

    odds = klient.kursy_fixture(fix_id)
    return odds or None
