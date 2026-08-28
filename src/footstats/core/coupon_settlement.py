"""
coupon_settlement.py – Rozliczanie ACTIVE kuponów z fallback na FlashScore/football-data.org.

Hierarchia źródeł wyników (każdy kolejny to fallback):
  1. API-Football (v3.football.api-sports.io) – tylko ~3 dni wstecz (Free plan)
  2. football-data.org – pełna historia
  3. FlashScore mobi – ~7 dni wstecz
  4. Tabela predictions w DB

Po rozliczeniu:
  - WIN: zaktualizuj bankroll
  - LOSE: wyślij do post_match_analyzer (RAG feedback)
  - legs_json: każdy leg dostaje pola `result` i `leg_won` dla UI

Użycie:
    from footstats.core.coupon_settlement import settle_active_coupons
    settle_active_coupons(days_back=60, dry_run=False, verbose=True)
"""

import json
import logging
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

from footstats.core import match_linker
from footstats.utils.betting import oblicz_tip_correct, powod_nierozliczalny
from footstats.utils.normalize import normalize_team_name, team_similarity

# Kupony ACTIVE bez wyniku po tylu dniach (legi z nieobsługiwanych lig/friendly)
# oznaczamy VOID, żeby nie blokowały na zawsze i nie liczyły się do accuracy/M1.
VOID_AFTER_DAYS = 10

# Najdluzej siegajace zrodlo wynikow. `flashscore.mobi` obsluguje ~7 dni wstecz
# (`flashscore_results.py`), darmowy plan API-Football tylko `dzis +/-1 dzien`
# (`results_updater.AF_HORYZONT_DNI`). Poza tym oknem wyniku nie zdobedzie zadna
# sciezka — i to jest OK, nie awaria.
HORYZONT_ZRODEL_DNI = 7


def data_jeszcze_osiagalna(mdate: str, dzis: date | None = None) -> bool:
    """Czy ktorekolwiek zrodlo moze jeszcze oddac wynik meczu z tej daty."""
    try:
        dzien = datetime.fromisoformat(str(mdate)[:10]).date()
    except (TypeError, ValueError):
        return False
    return 0 <= ((dzis or date.today()) - dzien).days <= HORYZONT_ZRODEL_DNI


def czeka_zbyt_dlugo(mdate: str, dzis: date | None = None) -> bool:
    """Czy brak wyniku dla meczu z tej daty jest juz PODEJRZANY.

    Wezsze niz `data_jeszcze_osiagalna` o jedna dobe i to jest caly sens. Tamta
    odpowiada na pytanie "czy zrodlo w ogole odpowie", ta na "czy powinnismy juz
    ten wynik miec". Zlanie obu w jedno dalo falszywy alarm 24.08 o 14:35 UTC:
    `/cron/settle` zwrocil {settled: 0, czekajace_w_zasiegu: 14}, alarm poszedl
    na Telegram, a wszystkie 14 kuponow bylo na mecze z TEGO DNIA, z ktorych
    pierwszy zaczynal sie dopiero o 15:30. Rozliczono zero, bo nie bylo czego.

    Powtarzaloby sie CODZIENNIE: draft tworzy kupony o 05:30 UTC, `settle-morning`
    rusza o 06:00 — zawsze przed pierwszym gwizdkiem.

    Prog to cala doba, nie "dzis po ostatnim meczu", bo kupon trzyma sama DATE
    (`match_date_first`) bez godziny — mecze brazylijskie z tej puli zaczynaly sie
    22:30 i 23:00 UTC, wiec nawet przebieg o 21:30 UTC nie moze zakladac, ze dzien
    jest zamkniety.
    """
    try:
        dzien = datetime.fromisoformat(str(mdate)[:10]).date()
    except (TypeError, ValueError):
        return False
    return 1 <= ((dzis or date.today()) - dzien).days <= HORYZONT_ZRODEL_DNI


def rozliczanie_stoi(settled: int, czekajace_w_zasiegu: int) -> str | None:
    """Opis cichej awarii rozliczania albo None, gdy stan wyglada zdrowo.

    ZMIERZONE: od 16.08 do 23.08 kazdy przebieg konczyl sie `settled: 0` przy 20+
    kuponach czekajacych. Przyczyna — zawieszone konto API-Football — nie zapalila
    zadnego alarmu; skutek zauwazyl dopiero `pipeline-health`, posrednio.

    Warunek CELOWO nie brzmi "rozliczono 0 przy niepustej kolejce". Kolejka potrafi
    byc pelna kuponow, ktorych wyniku juz nikt nie odda (poza horyzontem zrodel) —
    taki alarm palilby sie codziennie i przestal cokolwiek znaczyc. To dokladnie
    ten blad, ktory naprawialismy 23.08 rano przy alarmie o "ZERO predykcji".
    Pytamy wiec waziej: czy cos, co JESZCZE da sie zdobyc, mimo to nie zostalo
    rozliczone.
    """
    if settled > 0 or czekajace_w_zasiegu <= 0:
        return None
    return (f"rozliczono 0 kuponow, choc {czekajace_w_zasiegu} czeka na wyniki"
            f" wciaz osiagalne (do {HORYZONT_ZRODEL_DNI} dni wstecz)"
            f" — zrodla wynikow moglo zabraknac (konto? klucz? nazwy druzyn?)")


def kupony_przepadly(ile: int) -> str | None:
    """Opis kuponow skasowanych przez uplyw czasu albo None, gdy zaden nie przepadl.

    ODDZIELONE od `rozliczanie_stoi` swiadomie. Tamten pyta "czy cos, co JESZCZE
    da sie zdobyc, nie zostalo rozliczone" i dla tych kuponow milczy poprawnie —
    mecz sprzed 9 dni jest poza `HORYZONT_ZRODEL_DNI`, wiec nie ma go skad wziac.
    Tu pytamy o skutek, ktory tamten warunek z definicji przepuszcza: kupon
    ZNIKA z accuracy i ROI, a system uznaje to za normalna prace.

    ZMIERZONE 24.08: 20 kuponow z 15.08 czekalo na VOID nazajutrz. Same VOID-y byly
    poprawne — wyniku naprawde nie bylo skad wziac po zawieszeniu konta API-Football.
    Bledna byla cisza: jedyny slad to `print` pod `verbose`.

    Alarm nie mowi "napraw rozliczanie", tylko "sprawdz, czy selekcja nie bierze
    meczow, ktorych nie umiemy rozliczyc" — bo to jest zwykle prawdziwa przyczyna.
    """
    if ile <= 0:
        return None
    return (f"{ile} kuponow skasowanych (VOID) — mecz starszy niz"
            f" {VOID_AFTER_DAYS} dni i zadne zrodlo nie oddalo wyniku."
            " Te kupony wypadaja z accuracy i ROI. Sprawdz, czy zrodla zyja"
            " i czy selekcja nie bierze lig spoza ich pokrycia.")


def dziennik_utknal(ile: int) -> str | None:
    """Opis kuponow dziennika, ktore nie doczekaja sie wyniku, albo None.

    LUSTRO `kupony_przepadly`, ale skutek jest odwrotny i dlatego alarm tez musi
    byc inny. Tamten mowi "kupon ZNIKNAL"; ten mowi "kupon ZOSTAL i zostanie".

    ZMIERZONE 25.08: kupon #149 (chinska ekstraklasa, mecz 15.08) wisi ACTIVE
    dziesiaty dzien. `settle_manual_coupons` nie ma progu czasowego — sprawdza
    kupon w kolko, za kazdym razem trafia na `unresolved` i za kazdym razem
    liczy go jako zwykly `skipped`, nie do odroznienia od kuponu z wczoraj.

    DLACZEGO NIE VOID: `set_coupon_result` przyjmuje wylacznie kupony ACTIVE
    (CAS-guard). Automatyczne skasowanie odebraloby uzytkownikowi jedyna droge
    wpisania wyniku, ktory on moze znac, a my nie. Dziennik jest jego zapisem —
    my tylko przyznajemy sie, ze nie umiemy go sprawdzic.
    """
    if ile <= 0:
        return None
    return (f"{ile} kuponow z dziennika czeka na wynik dluzej niz"
            f" {VOID_AFTER_DAYS} dni i same sie nie rozlicza. Zostaja ACTIVE"
            " celowo — domknac je mozna tylko recznie w Historii"
            " (WYGRANY / PRZEGRANY / ANULOWANY). Zwykle powod: liga spoza"
            " zasiegu naszych zrodel wynikow.")


def _poza_terminem(mdate: str) -> bool:
    """Czy mecz z dziennika jest juz tak stary, ze wynik nie przyjdzie sam.

    Prog wspolny z kuponami AI (`VOID_AFTER_DAYS`) — po nim system uznaje,
    ze zrodla juz nic nie oddadza.
    """
    try:
        dzien = date.fromisoformat((mdate or "")[:10])
    except (TypeError, ValueError):
        # Daty nie da sie odczytac — nie zgadujemy, wiec kupon liczy sie jako
        # zwykly `skipped` i alarm o nim milczy. Ale MILCZEC O SAMEJ ZLEJ DACIE
        # nie wolno: taki wpis nigdy nie zostanie uznany za przeterminowany,
        # czyli wypada z jedynego mechanizmu, ktory go pilnuje.
        log.warning("Kupon dziennika z nieczytelna data meczu (%r) — pomijam"
                    " w liczeniu przeterminowanych", mdate)
        return False
    return (date.today() - dzien).days >= VOID_AFTER_DAYS



def _get_fixtures_api(api_key: str, date_str: str) -> list[dict]:
    """Pobiera fixtures z API-Football dla całej daty (bez filtrowania po lidze).

    Deleguje do `results_updater._fetch_fixtures_by_date` — wczesniej byla tu
    WLASNA, identyczna kopia tego zapytania (surowy `requests.get` pod ten sam
    endpoint). Kopia nie znala progu zasiegu darmowego planu, wiec przy kazdym
    przebiegu pytala o daty, na ktore API z definicji odpowiada odmowa:
    23.08 bylo to 21 kuponow z 14-15.08, po dwie daty kazdy, dwa razy dziennie.
    """
    from footstats.scrapers.results_updater import _fetch_fixtures_by_date

    return _fetch_fixtures_by_date(api_key, date_str)


def _get_matches_fdb(fdb_key: str, date_str: str) -> list[dict]:
    """Pobiera zakończone mecze z football-data.org (pełna historia)."""
    import requests
    from requests import RequestException
    if not fdb_key:
        return []
    try:
        r = requests.get(
            "https://api.football-data.org/v4/matches",
            headers={"X-Auth-Token": fdb_key},
            params={"dateFrom": date_str, "dateTo": date_str, "status": "FINISHED"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("matches", [])
    except (RequestException, ValueError, KeyError) as e:
        log.debug("football-data.org error for date %s: %s", date_str, e)
        return []


def _znajdz_wynik_fdb(home: str, away: str, matches: list[dict]) -> str | None:
    """Fuzzy-match meczu w danych z football-data.org. Zwraca 'HG-AG' lub None.

    Używa `team_similarity`, a NIE surowego `SequenceMatcher` na znormalizowanych
    nazwach. Poprzednia wersja robiła to drugie i miała dwie wady naraz:

      Legia / Legia Warszawa              0.53 -> poprawny wariant GUBIONY
      Manchester United / Manchester City 0.83 -> FAŁSZYWE dopasowanie (>=0.70)
      Dundee United / Dundee FC           0.82 -> FAŁSZYWE dopasowanie

    Drugi przypadek jest groźny: to źródło omijało całą ochronę przed kolizją
    nazw dodaną do `team_similarity` (commit 24cefa674), więc kupon na Manchester
    United mógł zostać rozliczony wynikiem Manchesteru City. `team_similarity`
    daje tam 0.50 i blokuje dopasowanie, a jednocześnie poprawnie łapie warianty
    skrócone (0.80).

    DRUGA POPRAWKA: para liczona jest przez `min`, nie przez ŚREDNIĄ. Poprzednia
    wersja uśredniała, więc jedno idealne trafienie przepychało złe dopasowanie
    drugiej strony:

        kupon "Legia - Lech Poznan"  vs  mecz "Legia - Lechia Gdansk"
        1.00 + 0.58 = srednia 0.79 >= 0.70  ->  ROZLICZALO

    Lech Poznan i Lechia Gdansk to dwa rozne kluby Ekstraklasy, oba grajace
    z Legia. Wymiana `SequenceMatcher` na `team_similarity` (wyzej) tego NIE
    zalatwila — usrednianie bylo osobna droga do tego samego bledu.
    """
    best_score = 0.0
    best_result: str | None = None
    for m in matches:
        fh = m.get("homeTeam", {}).get("name", "")
        fa = m.get("awayTeam", {}).get("name", "")
        score = min(team_similarity(home, fh), team_similarity(away, fa))
        if score >= 0.70 and score > best_score:
            ft = m.get("score", {}).get("fullTime", {})
            hg, ag = ft.get("home"), ft.get("away")
            if hg is not None and ag is not None:
                best_score = score
                best_result = f"{hg}-{ag}"
    return best_result


def _manual_zrodla_zewnetrzne() -> bool:
    """Czy dziennik kuponów może sięgnąć po wynik do źródeł zewnętrznych (D5).

    DLACZEGO TA FLAGA ISTNIEJE: `settle_manual_coupons` rozlicza wyłącznie z naszych
    `predictions` i jest all-legs-or-nothing, więc kupon na mecz, którego sami nie
    typowaliśmy, nie rozliczy się NIGDY. Zmierzone 24.08 na sześciu kuponach
    dziennika (#164-169): predykcję ma 1 noga z 12. To nie awaria, tylko dwa różne
    zbiory meczów — kupony powstają z `quick_picks`/Bzzoiro (~30 kandydatów
    dziennie), a `predictions` zapisuje tylko ścieżka `top3`/`kupon_d`.

    DLACZEGO DOMYŚLNIE OFF: `_find_leg_result` odpytuje API-Football i football-data,
    czyli zużywa limit darmowego planu — ten sam limit, którego brak zatrzymał
    rozliczanie na osiem dni w sierpniu. Włączenie to świadoma decyzja o wydatku.

    Czytane przy każdym wywołaniu — flip bez redeploya.
    """
    import os

    return os.getenv("MANUAL_SETTLE_EXTERNAL", "").strip() in ("1", "true", "True")


def _find_leg_result(
    home: str,
    away: str,
    mdate: str,
    fixtures_cache: dict[str, list],
    fdb_cache: dict[str, list],
    api_key: str,
    fdb_key: str,
) -> str | None:
    """
    Szuka wyniku meczu home-away dla mdate, a jeśli brak — dla mdate+1.

    Terminarz bywa przesuwany o 1 dzień po stronie API już po utworzeniu
    kuponu (match_date_first ustalony wcześniej), co bez tego fallbacku
    skutkuje fuzzy-matchem do innego meczu tego dnia (fałszywy wynik) albo
    wieczną PARTIAL (None na zawsze, bo szukamy zawsze tej samej, błędnej daty).
    """
    from footstats.core.backtest import _connect
    from footstats.scrapers.flashscore_results import get_match_result
    from footstats.scrapers.results_updater import _znajdz_wynik

    candidate_dates = [mdate]
    try:
        next_day = (datetime.fromisoformat(mdate) + timedelta(days=1)).date().isoformat()
        candidate_dates.append(next_day)
    except ValueError:
        pass

    for d in candidate_dates:
        if d not in fixtures_cache:
            fixtures_cache[d] = _get_fixtures_api(api_key, d) if api_key else []

        pending_mock = {"team_home": home, "team_away": away}
        res = _znajdz_wynik(pending_mock, fixtures_cache[d])

        if not res:
            norm_home = normalize_team_name(home)
            norm_away = normalize_team_name(away)
            if norm_home != home.lower() or norm_away != away.lower():
                norm_mock = {"team_home": norm_home, "team_away": norm_away}
                res = _znajdz_wynik(norm_mock, fixtures_cache[d])

        if not res:
            if d not in fdb_cache:
                fdb_cache[d] = _get_matches_fdb(fdb_key, d)
            res = _znajdz_wynik_fdb(home, away, fdb_cache[d])

        if res:
            if isinstance(res, tuple):
                res = res[0]
            if d != mdate:
                log.info("Mecz %s vs %s: wynik znaleziony na %s (przesuniety terminarz, kupon mial %s)", home, away, d, mdate)
            return res

    # Źródło 3: FlashScore – ostatni fallback PO sprawdzeniu obu dat w API-Football/fdb,
    # bo cache FlashScore bywa zapisany pod błędną datą (przesuniety terminarz) i ma
    # niższy priorytet niż "twarde" wyniki z API-Football/football-data.org.
    for d in candidate_dates:
        res = get_match_result(home, away, d, cache_enabled=True)
        if res:
            if isinstance(res, tuple):
                res = res[0]
            if d != mdate:
                log.info("Mecz %s vs %s: wynik znaleziony na %s (przesuniety terminarz, kupon mial %s)", home, away, d, mdate)
            return res

    # Źródło 4: tabela predictions w DB (sprawdź obie daty)
    for d in candidate_dates:
        try:
            with _connect() as pred_conn:
                pred_row = pred_conn.execute(
                    "SELECT actual_result FROM predictions WHERE match_date=? AND (team_home LIKE ? OR team_away LIKE ?) LIMIT 1",
                    (d, f"%{home}%", f"%{away}%"),
                ).fetchone()
            if pred_row and pred_row["actual_result"]:
                return pred_row["actual_result"]
        except (OSError, ValueError, RuntimeError) as e:
            # Kierunek jest bezpieczny (brak wyniku → kupon zostaje ACTIVE), ale awaria
            # bazy w ścieżce rozliczeń nie może być niewidoczna — bez logu wygląda
            # identycznie jak „mecz jeszcze nierozegrany".
            log.warning("Odczyt predictions dla %s vs %s (%s) nieudany: %s", home, away, d, e)

    # Źródło 5: agregator multi-source (consensus) — dokłada football-data.co.uk (CSV)
    # + cross-walidowany FlashScore, niezależne od źródeł 1-4 (AF /fixtures + football-data.org
    # API + FlashScore cache + DB). Ostatni fallback gdy żadne twarde źródło nie pokryło meczu.
    try:
        from footstats.scrapers.sources.aggregator import consensus_result

        for d in candidate_dates:
            res = consensus_result(home, away, d)
            if res:
                if d != mdate:
                    log.info(
                        "Mecz %s vs %s: wynik z konsensusu multi-source na %s (kupon mial %s)",
                        home, away, d, mdate,
                    )
                return res
    except (ImportError, OSError, ValueError, RuntimeError) as e:
        # jw. — cisza tutaj oznaczałaby, że konsensus multi-source „nie znalazł wyniku",
        # podczas gdy realnie w ogóle nie zadziałał.
        log.warning("Konsensus multi-source dla %s vs %s nieosiągalny: %s", home, away, e)

    return None


def settle_active_coupons(
    days_back: int = 3,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Rozlicza ACTIVE kupony z fallback na FlashScore.

    Args:
        days_back: Ile dni wstecz sprawdzać
        dry_run: Tylko pokaż co by zmienił
        verbose: Drukuj log

    Returns:
        {"settled": N, "partial": M, "errors": K}
    """
    from footstats.core.backtest import _connect, init_db
    from footstats.scrapers.results_updater import _get_api_key

    init_db()

    today = datetime.now().date()
    # days_back zostaje w sygnaturze (API/callers); okno "za stary" liczymy per
    # kupon przez VOID_AFTER_DAYS (patrz too_old niżej).

    # Cleanup stale-DRAFT: kupony DRAFT z przeszla data meczu nigdy nie zostaly
    # awansowane do ACTIVE (np. final phase nie pykl) -> nigdy by nie settlowaly
    # i rosly w nieskonczonosc. Po VOID_AFTER_DAYS oznaczamy VOID (nigdy nie byly zywym
    # zakladem, nie licza sie do accuracy/M1).
    void_cutoff = (today - timedelta(days=VOID_AFTER_DAYS)).isoformat()
    stale_voided = 0
    if not dry_run:
        with _connect() as conn:
            cur = conn.execute(
                """UPDATE coupons SET status='VOID'
                   WHERE status='DRAFT' AND substr(match_date_first,1,10) < ?""",
                (void_cutoff,),
            )
            stale_voided = cur.rowcount or 0
    if verbose and stale_voided:
        print(f"[CouponSettlement] Stale-DRAFT → VOID: {stale_voided}")

    # UWAGA: NIE robimy bulk-VOID stale-ACTIVE. Wcześniej kupon ACTIVE >10d był
    # VOID-owany ZANIM spróbowaliśmy pobrać wynik → kupony których wynik dopiero
    # dochodził z wolnych źródeł (FlashScore ~7d, football-data) znikały jako VOID
    # zamiast się rozliczyć (tracone wygrane/przegrane, zwł. System paper single-leg).
    # Teraz VOID dla stale-ACTIVE zapada DOPIERO po nieudanej próbie rozliczenia (niżej).

    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, legs_json, total_odds, stake_pln, match_date_first, user_id
               FROM coupons
               WHERE status = 'ACTIVE' AND match_date_first <= ?
                 AND (kupon_type IS NULL OR kupon_type <> 'manual')""",
            (today.isoformat(),),
        ).fetchall()

    if not rows:
        if verbose:
            print("[CouponSettlement] Brak ACTIVE kuponów do rozliczenia.")
        return {"settled": 0, "partial": 0, "errors": 0, "voided": stale_voided,
                "voided_brak_wyniku": 0, "czekajace_w_zasiegu": 0}

    if verbose:
        print(f"[CouponSettlement] ACTIVE kuponów do sprawdzenia: {len(rows)}")

    import os
    api_key = _get_api_key()
    fdb_key = os.getenv("FOOTBALL_API_KEY", "").strip()
    stats = {"settled": 0, "partial": 0, "errors": 0, "voided": stale_voided,
             "voided_brak_wyniku": 0, "czekajace_w_zasiegu": 0}
    fixtures_cache: dict[str, list] = {}
    fdb_cache: dict[str, list] = {}

    for row in rows:
        coupon_id = row["id"]
        owner_uid = row["user_id"]
        legs = json.loads(row["legs_json"])
        total_odds = row["total_odds"]
        stake = row["stake_pln"]
        match_date = row["match_date_first"]
        mdate = match_date[:10]

        # Wiek kuponu — decyzja VOID zapada PO nieudanej próbie rozliczenia (nie przed),
        # żeby kupon z dopiero-dostępnym wynikiem zdążył się rozliczyć zamiast zniknąć.
        try:
            leg_date = datetime.fromisoformat(match_date).date()
            too_old = (today - leg_date).days >= VOID_AFTER_DAYS
        except (ValueError, TypeError):
            too_old = False

        leg_results: list[int | None] = []
        any_leg_lost = False
        updated_legs = [dict(leg) for leg in legs]  # kopia do zapisu per-leg results

        for leg_idx, leg in enumerate(legs):
            home = leg.get("home", "")
            away = leg.get("away", "")

            if not home or not away:
                mecz = leg.get("mecz", "")
                if " vs " in mecz:
                    home, away = mecz.split(" vs ", 1)
                elif " - " in mecz:
                    home, away = mecz.split(" - ", 1)
                home, away = home.strip(), away.strip()

            # 4 źródła wyników, kolejno mdate i mdate+1 (przesuniety terminarz)
            res = _find_leg_result(home, away, mdate, fixtures_cache, fdb_cache, api_key, fdb_key)

            correct = oblicz_tip_correct(leg["tip"], res)
            leg_results.append(correct)

            # Zapisz per-leg wynik do updated_legs (dla UI)
            updated_legs[leg_idx]["result"] = res
            updated_legs[leg_idx]["leg_won"] = (
                True if correct == 1 else (False if correct == 0 else None)
            )

            if verbose:
                status_text = "OK" if correct == 1 else "MISS" if correct == 0 else "WAITING"
                print(f"    - {leg.get('home','?')} vs {leg.get('away','?')} (Tip: {leg['tip']}, Res: {res or '?'}) -> {status_text}")

            if correct == 0:
                any_leg_lost = True

        # Nierozliczalne: brak nóg lub brakujące wyniki (i nic dotąd nie przegrane)
        if (not leg_results or None in leg_results) and not any_leg_lost:
            # Dogrywka/karne: wynik JEST, ale rynków 90-minutowych nie da się z niego
            # rozliczyć (patrz `powod_nierozliczalny`). Czekanie `VOID_AFTER_DAYS`
            # niczego nie zmieni — źródło nie dośle wyniku regulaminowego. Anulujemy
            # od razu i Z PODANYM POWODEM, zamiast dziesięciu dni ciszy zakończonych
            # anulowaniem, którego potem nikt nie umie wytłumaczyć.
            blokady = [
                (lg.get("mecz") or f"{lg.get('home','?')} vs {lg.get('away','?')}", powod)
                for lg in updated_legs
                if (powod := powod_nierozliczalny(lg.get("result")))
            ]
            if blokady:
                opis = "; ".join(f"{mecz} ({powod})" for mecz, powod in blokady)
                if not dry_run:
                    with _connect() as conn:
                        conn.execute(
                            "UPDATE coupons SET status='VOID', legs_json=? WHERE id=?",
                            (json.dumps(updated_legs, ensure_ascii=False), coupon_id),
                        )
                stats["voided"] += 1
                log.warning("Kupon #%s → VOID: wyniku nie da sie rozliczyc — %s",
                            coupon_id, opis)
                if verbose:
                    print(f"  [VOID] Kupon #{coupon_id} — {opis}\n")
                continue

            if too_old:
                # >= VOID_AFTER_DAYS i wciąż nierozliczalne (mecz dawno rozegrany,
                # brak wyniku w żadnym źródle) → VOID. Nie wisi ACTIVE w nieskończoność.
                if not dry_run:
                    with _connect() as conn:
                        conn.execute(
                            "UPDATE coupons SET status='VOID' WHERE id=?", (coupon_id,)
                        )
                stats["voided"] += 1
                stats["voided_brak_wyniku"] += 1
                # Osobny licznik i log, bo to NIE jest to samo co VOID po karnych.
                # Tamto jest normalną pracą systemu, to jest skutek awarii źródeł —
                # kupon wypada z accuracy i ROI. Do 24.08 jedynym śladem był `print`
                # pod `verbose`, więc 20 kuponów mogło zniknąć bez linijki w logu.
                mecze = ", ".join(
                    lg.get("mecz") or f"{lg.get('home', '?')} vs {lg.get('away', '?')}"
                    for lg in updated_legs
                ) or "?"
                log.warning(
                    "Kupon #%s → VOID: brak wyniku po %sd (mecz %s) — %s",
                    coupon_id, VOID_AFTER_DAYS, mdate, mecze,
                )
                if verbose:
                    print(f"  [VOID] Kupon #{coupon_id} — brak wyniku po {VOID_AFTER_DAYS}d → VOID\n")
                continue
            # W oknie → zapisz znane per-leg wyniki (partial update) i czekaj
            if not dry_run:
                try:
                    with _connect() as conn:
                        conn.execute(
                            "UPDATE coupons SET legs_json=? WHERE id=?",
                            (json.dumps(updated_legs, ensure_ascii=False), coupon_id),
                        )
                except (OSError, ValueError) as e:
                    log.debug("Błąd zapisu partial legs_json dla #%s: %s", coupon_id, e)
            stats["partial"] += 1
            # Rozdzielamy "czeka, bo jeszcze nie ma wyniku" od "czeka, bo wyniku
            # juz nikt nie odda". Bez tego rozroznienia alarm o stojacym
            # rozliczaniu nie da sie ustawic tak, zeby nie wyl codziennie.
            # `czeka_zbyt_dlugo`, nie `data_jeszcze_osiagalna`: mecz z DZISIAJ moze
            # sie jeszcze nie odbyc, a wtedy brak wyniku jest stanem normalnym.
            if czeka_zbyt_dlugo(mdate):
                stats["czekajace_w_zasiegu"] += 1
            if verbose:
                print(f"  [PARTIAL] Kupon #{coupon_id} — czekam na brakujące wyniki\n")
            continue

        # Finalne rozliczenie
        all_correct = all(r == 1 for r in leg_results) and not any_leg_lost
        new_status = "WON" if all_correct else "LOST"
        payout = round(stake * total_odds, 2) if all_correct else 0.0
        roi = round((payout - stake) / stake * 100, 1) if stake else 0.0

        if verbose:
            tag = "DRY" if dry_run else "SETTLE"
            print(f"  [{tag}] Kupon #{coupon_id} → {new_status} | wypłata: {payout} PLN | ROI: {roi}%\n")

        if not dry_run:
            try:
                with _connect() as conn:
                    # CAS-guard (D3): UPDATE tylko gdy kupon WCIĄŻ ACTIVE. Równoległe
                    # settle (Scheduler 06:00/21:30 + evening) mogą oba wybrać ten sam
                    # kupon — bez guardu drugi proces kredytowałby bankroll drugi raz.
                    cur = conn.execute(
                        "UPDATE coupons SET status=?, payout_pln=?, roi_pct=?, legs_json=? "
                        "WHERE id=? AND status='ACTIVE'",
                        (new_status, payout, roi,
                         json.dumps(updated_legs, ensure_ascii=False), coupon_id),
                    )
                    settled_now = (cur.rowcount or 0) == 1
                    if not settled_now:
                        log.warning(
                            "Kupon #%s nie jest już ACTIVE — rozliczony równolegle, pomijam kredyt/RAG",
                            coupon_id,
                        )
                    else:
                        log.info("Kupon #%s → %s | payout=%.2f | roi=%.1f%%", coupon_id, new_status, payout, roi)

                    if settled_now and all_correct and payout > 0 and owner_uid is not None:
                        # Kredytuj WŁAŚCICIELA kuponu (nie MAX(id)!), brutto/przed
                        # podatkiem, 100% — spójnie z evening_agent.credit_win.
                        cur_balance = conn.execute(
                            "SELECT balance FROM bankroll_state WHERE user_id=?",
                            (owner_uid,),
                        ).fetchone()
                        if cur_balance:
                            new_balance = round(cur_balance["balance"] + payout, 2)
                            conn.execute(
                                "UPDATE bankroll_state SET balance=?, updated_at=? WHERE user_id=?",
                                (new_balance, datetime.now().isoformat(), owner_uid),
                            )
                            conn.execute(
                                "INSERT INTO bankroll_history "
                                "(timestamp, change_pln, new_balance, type, description, user_id) "
                                "VALUES (?,?,?,?,?,?)",
                                (
                                    datetime.now().isoformat(),
                                    payout,
                                    new_balance,
                                    "WIN",
                                    f"Kupon #{coupon_id} WON",
                                    owner_uid,
                                ),
                            )
                        else:
                            # D7: WON bez wiersza bankroll_state — nie może przejść w ciszy
                            log.warning(
                                "Kupon #%s WON, brak bankroll_state dla user_id=%s — kredyt pominięty",
                                coupon_id, owner_uid,
                            )

                if settled_now and not all_correct:
                    failed_legs = [lg for lg in updated_legs if lg.get("leg_won") is False]
                    parts = [
                        f"Leg #{i+1}: {lg.get('home','?')} vs {lg.get('away','?')} "
                        f"Tip:{lg.get('tip','?')} Wynik:{lg.get('result','?')}"
                        for i, lg in enumerate(updated_legs) if lg.get("leg_won") is False
                    ]
                    lose_reason = (
                        f"PRZEGRANY kupon ({len(legs)} legów, {len(failed_legs)} chybionych). "
                        + "; ".join(parts)
                    )
                    _send_to_rag_feedback(coupon_id, updated_legs, mdate, lose_reason, verbose=verbose)

                if settled_now:
                    stats["settled"] += 1
            except (KeyError, TypeError, ValueError, OSError) as e:
                log.error("Błąd rozliczania kuponu ID=%s: %s", coupon_id, e)
                stats["errors"] += 1
        else:
            stats["settled"] += 1  # dry_run: count without DB write

    if verbose:
        print(
            f"\n[CouponSettlement] Rozliczonych: {stats['settled']} | "
            f"Częściowych: {stats['partial']} | Błędów: {stats['errors']}"
        )
    return stats


def _send_to_rag_feedback(coupon_id: int, legs: list, mdate: str, reason: str, verbose: bool = True) -> None:
    """
    Wysyła info o przegranych legach kuponu do ai_feedback (RAG learning).

    ai_feedback.match_id ma FK do predictions.id (nie coupons.id), więc dla
    każdego przegranego lega szukamy odpowiadającej predykcji po dacie i drużynach.

    Args:
        coupon_id: ID kuponu (do logu/kontekstu)
        legs: Lista leg'ów kuponu (z polami home/away/tip/result/leg_won)
        mdate: Data meczów kuponu (YYYY-MM-DD)
        reason: Powód porażki (do logu)
        verbose: Drukuj log
    """
    from footstats.ai.post_match_analyzer import _zapisz_feedback
    from footstats.core.backtest import _connect

    if verbose:
        log.info("Kupon #%s: %s", coupon_id, reason)

    for i, leg in enumerate(legs):
        if leg.get("leg_won") is not False:
            continue

        home = leg.get("home", "")
        away = leg.get("away", "")

        try:
            with _connect() as conn:
                pred_row = conn.execute(
                    "SELECT id FROM predictions "
                    "WHERE match_date=? AND team_home LIKE ? AND team_away LIKE ? LIMIT 1",
                    (mdate, f"%{home}%", f"%{away}%"),
                ).fetchone()

            if not pred_row:
                log.debug("Brak predictions dla %s vs %s (%s) — pomijam RAG feedback", home, away, mdate)
                continue

            prediction_details = {
                "coupon_id": coupon_id,
                "tip": leg.get("tip", "?"),
                "result": leg.get("result", "?"),
            }
            leg_reason = (
                f"Kupon #{coupon_id}, leg #{i + 1}: {home} vs {away} "
                f"Tip:{leg.get('tip', '?')} Wynik:{leg.get('result', '?')}"
            )

            _zapisz_feedback(
                match_id=pred_row["id"],
                prediction_details=prediction_details,
                reason=leg_reason,
            )

            if verbose:
                log.info("Wysłano feedback do RAG dla kuponu #%s, leg #%s", coupon_id, i + 1)
        except (ImportError, AttributeError, TypeError, ValueError, OSError) as e:
            log.warning("Błąd wysyłania feedback do RAG dla kuponu #%s, leg #%s: %s", coupon_id, i + 1, e)


def settle_manual_coupons(dry_run: bool = False, verbose: bool = True) -> dict:
    """
    Auto-rozlicza kupony manual (dziennik, Etap C planu J4c).

    Zasada nadrzędna „co mamy — my": noga jest rozliczalna TYLKO gdy
    `link_leg` zwróci matched="exact" ORAZ zlinkowana predykcja ma niepusty
    `actual_result` (czyli wynik meczu już mamy w naszej bazie). Jakakolwiek
    noga niepewna (brak dopasowania, brak wyniku, nierozliczalny tip) →
    CAŁY kupon zostaje ACTIVE — konserwatywnie, bez rozliczenia częściowego;
    user domknie go ręcznie przez `set_coupon_result`.

    ZERO zewnętrznych API — DOMYŚLNIE. W odróżnieniu od `settle_active_coupons`
    (kupony AI) ta funkcja nie woła `_find_leg_result`/FlashScore/football-data,
    żeby nie generować dodatkowego ruchu do zewnętrznych źródeł dla wpisów
    ręcznych.

    Kolejność źródeł (każde kolejne to fallback):
      1. `predictions` przez `link_leg` — nasza predykcja z wynikiem;
      2. `model_log` przez `wynik_z_model_log` — TA SAMA nasza baza, tylko
         szersza (161 vs 424 wiersze na prod 28.08), bo `predictions` zapisuje
         wyłącznie ścieżkę `top3`/`kupon_d`, a dziennik kalibracyjny każdy
         oceniony mecz. Darmowe, więc PRZED zewnętrznymi API;
      3. źródła zewnętrzne — tylko pod flagą (niżej).

    D5: `MANUAL_SETTLE_EXTERNAL=1` otwiera ten fallback dla nóg, dla których NIE
    mamy własnej predykcji z wynikiem — bez niego kupon na mecz spoza naszych
    typów zostaje ACTIVE na zawsze (zmierzone 24.08: 11 z 12 nóg dziennika).
    Nasze dane zachowują pierwszeństwo, all-legs-or-nothing zostaje bez zmian.
    Patrz `_manual_zrodla_zewnetrzne`. Bankroll-neutralne: dziennik nie rusza `bankroll_state` ani
    `bankroll_history` (spójnie z `/api/coupon/manual` i ręcznym
    `set_coupon_result`). Bez RAG-feedbacku i bez Telegrama.

    Args:
        dry_run: tylko licz statystyki, bez zapisu do DB.
        verbose: drukuj PL logi na stdout.

    Returns:
        {"settled": N, "skipped": M, "errors": K}
    """
    from footstats.core.backtest import _connect, init_db

    init_db()

    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, legs_json, total_odds, stake_pln, match_date_first, user_id
               FROM coupons
               WHERE status = 'ACTIVE' AND kupon_type = 'manual'"""
        ).fetchall()

    stats = {"settled": 0, "skipped": 0, "errors": 0, "z_zewnatrz": 0,
             "z_model_log": 0, "przeterminowane": 0}
    if not rows:
        if verbose:
            print("[SettleManual] Brak ACTIVE kuponów manual do rozliczenia.")
        return stats

    if verbose:
        print(f"[SettleManual] ACTIVE kuponów manual do sprawdzenia: {len(rows)}")

    # D5: fallback na zewnętrzne źródła wyników. Cache trzymamy PONAD pętlą kuponów —
    # osobny cache na kupon mnożyłby zapytania o tę samą datę przez liczbę kuponów.
    zewnetrzne = _manual_zrodla_zewnetrzne()
    fixtures_cache: dict[str, list] = {}
    fdb_cache: dict[str, list] = {}
    api_key = fdb_key = ""
    if zewnetrzne:
        import os

        from footstats.scrapers.results_updater import _get_api_key
        api_key = _get_api_key() or ""
        fdb_key = os.getenv("FOOTBALL_API_KEY", "").strip()

    for row in rows:
        coupon_id = row["id"]
        try:
            legs = json.loads(row["legs_json"])
            mdate = (row["match_date_first"] or "")[:10]
            total_odds = row["total_odds"]
            stake = row["stake_pln"]

            leg_results: list[int] = []
            unresolved = False
            for leg in legs:
                home = leg.get("home", "")
                away = leg.get("away", "")
                lr = match_linker.link_leg(home, away, mdate)

                # NASZE DANE PIERWSZE — są darmowe i pochodzą z tego samego
                # przebiegu co typ. Zewnętrzne źródła to fallback, nie zamiennik.
                if lr.matched and lr.prediction and lr.prediction.get("actual_result"):
                    wynik = lr.prediction["actual_result"]
                elif (z_dziennika := match_linker.wynik_z_model_log(home, away, mdate)):
                    # `model_log` to TA SAMA nasza baza, tylko szersza:
                    # `predictions` zapisuje jedynie ścieżkę top3/kupon_d
                    # (161 wierszy na prod 28.08), `model_log` każdy oceniony
                    # mecz (424). Darmowe, więc pytane PRZED zewnętrznymi API.
                    wynik = z_dziennika
                    stats["z_model_log"] += 1
                elif zewnetrzne:
                    wynik = _find_leg_result(home, away, mdate, fixtures_cache,
                                             fdb_cache, api_key, fdb_key)
                    if wynik:
                        stats["z_zewnatrz"] += 1
                else:
                    wynik = None

                if not wynik:
                    unresolved = True
                    break
                correct = oblicz_tip_correct(leg.get("tip", ""), wynik)
                if correct is None:
                    unresolved = True
                    break
                leg_results.append(correct)

            # Guard (defense-in-depth, analogicznie do settle_active_coupons ~L322):
            # kupon bez nóg (legs_json="[]") NIE może "wygrać" przez all([])==True.
            # W praktyce niemożliwe (_validate_manual_coupon odrzuca puste nogi),
            # ale traktujemy jak nierozwiązany — belt-and-suspenders.
            if not leg_results:
                unresolved = True

            if unresolved:
                stats["skipped"] += 1
                # `skipped` sam w sobie nie odroznia "poczekamy do jutra" od
                # "nie doczekamy sie nigdy" — a to druga sytuacja wymaga czlowieka.
                if _poza_terminem(mdate):
                    stats["przeterminowane"] += 1
                if verbose:
                    print(f"  [ACTIVE] Kupon manual #{coupon_id} — noga bez pewnego wyniku, zostaje ACTIVE")
                continue

            all_won = all(c == 1 for c in leg_results)
            new_status = "WON" if all_won else "LOST"
            payout = round(stake * total_odds, 2) if all_won else 0.0

            if verbose:
                tag = "DRY" if dry_run else "SETTLE"
                print(f"  [{tag}] Kupon manual #{coupon_id} → {new_status} | wypłata: {payout} PLN")

            if not dry_run:
                from footstats.core.coupon_tracker import update_coupon_status

                zmieniono = update_coupon_status(
                    coupon_id, new_status, payout_pln=payout, expected_status="ACTIVE"
                )
                if not zmieniono:
                    # CAS-guard: kupon rozliczony ręcznie równolegle (set_coupon_result)
                    # zdążył zmienić status — nie kredytujemy/nie liczymy jako settled.
                    log.warning(
                        "Kupon manual #%s nie jest już ACTIVE — rozliczony równolegle, pomijam",
                        coupon_id,
                    )
                    continue

            stats["settled"] += 1
        except (KeyError, TypeError, ValueError, OSError) as e:
            log.error("Błąd rozliczania kuponu manual ID=%s: %s", coupon_id, e)
            stats["errors"] += 1

    if stats["przeterminowane"]:
        # WARNING, nie `print` pod `verbose` — w Cloud Logging nie ma stdout tej
        # funkcji, a bez tej linijki kupon utknięty na stałe wygląda w logach
        # dokładnie tak samo jak wczorajszy, który jeszcze się rozliczy.
        log.warning(
            "Dziennik: %d kuponów ACTIVE mimo %d dni od meczu — wynik nie przyjdzie"
            " sam, domknąć może tylko użytkownik (set_coupon_result)",
            stats["przeterminowane"], VOID_AFTER_DAYS,
        )

    if verbose:
        print(
            f"\n[SettleManual] Rozliczonych: {stats['settled']} | "
            f"Pominiętych: {stats['skipped']} | Błędów: {stats['errors']}"
        )
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    settle_active_coupons(days_back=3, dry_run=False, verbose=True)
