"""
daily_phases.py – Spójne fazy wzbogacania/scoringu wydzielone z daily_agent.py.

Czyste-ish helpery operujące na liście kandydatów ('wyniki') lub słowniku
'dane' (kupony) — bez zależności od stanu lokalnego main(). Wydzielone w ramach
redukcji god-module daily_agent.py (dług techniczny #3), behavior-preserving.
"""

import logging

from rich.console import Console

from footstats.scrapers.api_football import fetch_odds_af
from footstats.utils.normalize import normalize_team_name

log = logging.getLogger(__name__)
console = Console()

_norm = normalize_team_name


# ── Krok 1b: Injury Lambda Correction ──────────────────────────────────────

def _current_season() -> int:
    """Sezon piłkarski: rok bieżący gdy >czerwiec, inaczej poprzedni (jak API-Football)."""
    from datetime import datetime
    now = datetime.now()
    return now.year if now.month > 6 else now.year - 1


def _goal_shares_for(team: str, side: str | None = None) -> dict[str, float]:
    """
    Udziały w golach graczy drużyny z player_db (Kontuzje v2). Bezpieczny fallback:
    dowolny błąd / brak danych → {} (injury model użyje flat kary). side: tylko log.
    """
    try:
        from footstats.core.player_db import team_goal_shares
        return team_goal_shares(team, _current_season())
    except (ImportError, AttributeError, TypeError, KeyError, ValueError) as e:
        # reference data nie może wywalić pipeline (team_goal_shares łapie sqlite3.Error sam)
        log.debug("goal_shares fallback (%s): %s", team, e)
        return {}


def _apply_injury_corrections(wyniki: list) -> None:
    """
    Koryguje λ i PRAWDOPODOBIEŃSTWA kandydata za kontuzje (dwustronnie):
      brak napastnika/pomocnika → mniej strzela DANA drużyna (OWN λ ↓)
      brak obrońcy/bramkarza    → więcej strzela RYWAL (λ rywala ↑)
    Przelicza pw/pr/pp/bt/o25 z macierzy Poissona dla skorygowanych λ — żeby
    kontuzje realnie wpływały na typy (1X2/O-U/BTTS), nie tylko bet_builder.
    """
    from footstats.core.lambda_optimizer import injury_lambda_factors
    from footstats.core.bet_builder import estimate_lambdas_from_probs, probability_matrix

    for w in wyniki:
        try:
            inj_h = w.get("injuries_home") or []
            inj_a = w.get("injuries_away") or []
            if not inj_h and not inj_a:
                continue

            gs_h = _goal_shares_for(w.get("gospodarz") or "", "home") or None
            gs_a = _goal_shares_for(w.get("goscie") or "", "away") or None
            h_atak, h_leak = injury_lambda_factors(inj_h, goal_shares=gs_h)
            a_atak, a_leak = injury_lambda_factors(inj_a, goal_shares=gs_a)
            if (h_atak, h_leak, a_atak, a_leak) == (1.0, 1.0, 1.0, 1.0):
                continue

            # λ wyjściowe: z lambda_h/a (bet_builder) lub estymowane z pw/pp/o25
            lh = w.get("lambda_h")
            la = w.get("lambda_a")
            if not lh or not la:
                lh, la = estimate_lambdas_from_probs(
                    (w.get("pw") or 0) / 100.0, (w.get("pp") or 0) / 100.0, (w.get("o25") or 0) / 100.0
                )
            # gospodarz strzela: własny atak ↓ + dziura w obronie gościa ↑
            lh_adj = round(lh * h_atak * a_leak, 4)
            la_adj = round(la * a_atak * h_leak, 4)
            w["lambda_h"], w["lambda_a"] = lh_adj, la_adj

            # Przelicz prawdopodobieństwa z macierzy (procenty, jak w kandydacie)
            mat = probability_matrix(lh_adj, la_adj)
            n = len(mat)
            pw = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if h > a)
            pr = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if h == a)
            pp = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if a > h)
            o25 = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if h + a > 2.5)
            bt = sum(mat[h][a] for h in range(1, n) for a in range(1, len(mat[h])))
            w["pw"], w["pr"], w["pp"] = round(pw * 100, 1), round(pr * 100, 1), round(pp * 100, 1)
            w["o25"], w["bt"] = round(o25 * 100, 1), round(bt * 100, 1)
            log.debug(
                "%s vs %s: kontuzje λ %.2f→%.2f / %.2f→%.2f",
                w.get("gospodarz"), w.get("goscie"), lh, lh_adj, la, la_adj,
            )
        except (AttributeError, TypeError, KeyError, ValueError) as e:
            log.debug(f"Injury correction error: {e}")


# ── Krok 2: Forma SofaScore ───────────────────────────────────────────────────

def _wzbogac_forme_top(wyniki: list, top_n: int = 6) -> None:
    """Pobiera formę + kontuzje dla TOP N meczów przez SofaScore."""
    try:
        from footstats.scrapers.form_scraper import pobierz_forme_meczu, PLAYWRIGHT_OK
        if not PLAYWRIGHT_OK:
            console.print("[yellow]SofaScore niedostępny (Playwright) — pomijam formę[/yellow]")
            return
    except ImportError:
        console.print("[yellow]form_scraper niedostępny — pomijam formę[/yellow]")
        return

    def _max_ev(w):
        return max((v for _, v in w.get("typy", [(None, 0)])), default=0)

    top = sorted(wyniki, key=_max_ev, reverse=True)[:top_n]
    console.print(f"[dim]SofaScore: pobieram formę dla {len(top)} meczów...[/dim]")

    for w in top:
        g = w.get("gospodarz", "")
        a = w.get("goscie", "")
        if not g or not a:
            continue
        try:
            forma = pobierz_forme_meczu(g, a)
            fh = forma.get("home", {})
            fa = forma.get("away", {})
            if fh.get("form"):
                w["sofa_forma_g"] = f"{''.join(fh['form'])}({fh.get('goals_scored',0)}:{fh.get('goals_conceded',0)})"
            if fa.get("form"):
                w["sofa_forma_a"] = f"{''.join(fa['form'])}({fa.get('goals_scored',0)}:{fa.get('goals_conceded',0)})"
            # Pełne dane kontuzji (z pozycją) do korekty λ — nie tylko nazwy do wyświetlenia
            w["injuries_home"] = fh.get("injuries", []) or []
            w["injuries_away"] = fa.get("injuries", []) or []
            inj_g = [i.get("name", "?") for i in fh.get("injuries", [])[:3]]
            inj_a = [i.get("name", "?") for i in fa.get("injuries", [])[:3]]
            if inj_g:
                w["sofa_kontuzje_g"] = ", ".join(inj_g)
            if inj_a:
                w["sofa_kontuzje_a"] = ", ".join(inj_a)
        except (AttributeError, TypeError, KeyError):
            pass


def _wzbogac_o_betbuilder(wyniki: list, pobierz_superbet: bool = False) -> None:
    """
    Wzbogaca mecze o sugestie BetBuilder.

    Krok 1 (zawsze): Poisson — szybka estymacja prawdopodobieństw.
    Krok 2 (--bb):   Real kursy z Superbet API via browser (~2-4min dla 5 meczów).
                     Generuje kombinacje z generuj_kombinacje() i zapisuje do
                     w["bet_builder_kombinacje_superbet"] dla kontekstu AI Groq.
    """
    # -- Krok 1: Poisson (zawsze) --
    try:
        from footstats.core.bet_builder import estimate_lambdas_from_probs, get_all_market_suggestions
        from footstats.betbuilder import fmt_bb_sugestie
    except ImportError:
        pass
    else:
        console.print("[dim]BetBuilder: Estymacja macierzy Poissona...[/dim]")
        for w in wyniki:
            pw  = w.get("pw", 0) / 100.0
            pp  = w.get("pp", 0) / 100.0
            o25 = w.get("o25", 0) / 100.0
            if pw > 0 or pp > 0:
                lh, la  = estimate_lambdas_from_probs(pw, pp, o25)
                ref_avg = w.get("referee_avg_y")
                markets = get_all_market_suggestions(lh, la, ref_avg_yellow=ref_avg)
                all_sugestie = [
                    f"[{cat}] {item}"
                    for cat, items in markets.items()
                    for item in items
                ]
                if all_sugestie:
                    w["bet_builder"]         = all_sugestie
                    w["bet_builder_markets"] = markets
                    bb_raw = markets.get("BetBuilder", [])
                    if bb_raw:
                        w["bet_builder_kombinacje"] = fmt_bb_sugestie(bb_raw)

    # -- Krok 2: Real Superbet BB odds (opcjonalnie, --bb) --
    if not pobierz_superbet:
        return

    try:
        from footstats.scrapers.superbet_bb import pobierz_bb_dla_meczow
        from footstats.betbuilder import generuj_kombinacje
    except ImportError:
        console.print("[yellow]BetBuilder Superbet: brak modulu superbet_bb[/yellow]")
        return

    top_n = wyniki[:5]
    mecze_input = [
        {"dom": w.get("gospodarz", ""), "gost": w.get("goscie", "")}
        for w in top_n
        if w.get("gospodarz") and w.get("goscie")
    ]
    if not mecze_input:
        return

    console.print(f"[dim]BetBuilder Superbet: pobieranie kursow dla {len(mecze_input)} meczow (moze ~3min)...[/dim]")
    try:
        bb_data = pobierz_bb_dla_meczow(mecze_input, headless=True)
    except Exception as e:  # noqa: broad-except — Playwright raises varied types
        console.print(f"[yellow]BetBuilder Superbet error: {e}[/yellow]")
        return

    for w in top_n:
        dom   = w.get("gospodarz", "")
        gost  = w.get("goscie", "")
        klucz = f"{dom} vs {gost}"
        typy  = bb_data.get(klucz, [])
        if not typy:
            continue

        typy_filtr = [t for t in typy if 1.15 <= t.kurs <= 10.0][:60]
        if not typy_filtr:
            continue

        combos = generuj_kombinacje(
            typy_filtr,
            min_typy=2,
            max_typy=4,
            min_kurs=3.0,
            min_ev=0.0,
        )
        if not combos:
            continue

        # Fokus na realnym zakresie 5x-25x (atrakcyjne, nie absurdalne)
        zakres = [c for c in combos if 5.0 <= c.kurs_laczny <= 25.0]
        top_combos = sorted(zakres or combos, key=lambda c: c.kurs_laczny)[:12]
        w["bet_builder_kombinacje_superbet"] = [
            {"kurs": c.kurs_laczny, "typy": [{"nazwa": t.nazwa, "kurs": t.kurs} for t in c.typy]}
            for c in top_combos
        ]
        console.print(f"[dim]  BB Superbet {klucz}: {len(combos)} kombinacji ({len(zakres)} w 5-25x)[/dim]")


def _wzbogac_o_inspiracje(wyniki: list, debug: bool = False) -> None:
    """
    Krok opcjonalny (FAZA 15.7): pobiera "Popularne kupony" ze Strefy Inspiracji
    STS + karuzelę BetBuilder ze strony głównej, dopasowuje do kandydatów po
    nazwach drużyn i ocenia sygnał (VALUE/NO_VALUE) wzgledem modelu Poisson.
    Zapisuje wynik w w["inspiracje_signal"] dla kontekstu Groq.

    Niepowodzenie (brak playwright, timeout, błąd sieci) nie przerywa pipeline'u.
    """
    try:
        from footstats.scrapers.sts_inspiracje import (
            PLAYWRIGHT_OK,
            dopasuj_do_predykcji,
            parse_betbuilder_carousel,
            parse_popular_tickets,
            pobierz_betbuilder_carousel,
            pobierz_popularne_kupony,
        )
        from footstats.core.bet_builder import estimate_lambdas_from_probs
    except ImportError as e:
        console.print(f"[dim]Strefa Inspiracji: {e}[/dim]")
        return

    if not PLAYWRIGHT_OK:
        console.print("[dim]Strefa Inspiracji: playwright niedostepny, pomijam[/dim]")
        return

    console.print("[dim]Strefa Inspiracji: pobieranie sygnalow top typerow...[/dim]")
    try:
        tickets = parse_popular_tickets(pobierz_popularne_kupony(debug=debug))
        tickets += parse_betbuilder_carousel(pobierz_betbuilder_carousel(debug=debug))
    except (OSError, RuntimeError) as e:
        console.print(f"[dim]Strefa Inspiracji: blad scrapingu - {e}[/dim]")
        return

    if not tickets:
        console.print("[dim]Strefa Inspiracji: brak kuponow do dopasowania[/dim]")
        return

    predykcje = []
    for w in wyniki:
        pw, pp, o25 = w.get("pw", 0) / 100.0, w.get("pp", 0) / 100.0, w.get("o25", 0) / 100.0
        if pw <= 0 and pp <= 0:
            continue
        lh, la = estimate_lambdas_from_probs(pw, pp, o25)
        predykcje.append({
            "gosp": w.get("gospodarz", ""), "gosc": w.get("goscie", ""),
            "expected_home_goals": lh, "expected_away_goals": la,
        })

    sygnaly = dopasuj_do_predykcji(tickets, predykcje)
    if not sygnaly:
        console.print(f"[dim]Strefa Inspiracji: {len(tickets)} kuponow typerow, 0 dopasowan[/dim]")
        return

    by_team = {(_norm(s["gosp"]), _norm(s["gosc"])): s for s in sygnaly}
    for w in wyniki:
        s = by_team.get((_norm(w.get("gospodarz", "")), _norm(w.get("goscie", ""))))
        if s:
            w["inspiracje_signal"] = s

    n_value = sum(1 for s in sygnaly if s["signal"] == "VALUE")
    console.print(f"[green]Strefa Inspiracji: {len(sygnaly)} dopasowan, {n_value} VALUE[/green]")
    for s in sygnaly:
        ticket = s["ticket"]
        console.print(
            f"[dim]  {s['gosp']} vs {s['gosc']}: typy={ticket['typy']} "
            f"kurs={ticket['total_odds']} -> {s['signal']}[/dim]"
        )


# ── Krok 2b: Fallback kursów API-Football -> SofaScore (gdy Bzzoiro brak) ────

def _uzupelnij_kursy(w: dict, fallback_odds: dict | None) -> bool:
    """Dopisuje brakujące klucze kursów do kandydata `w` (nie nadpisuje istniejących)."""
    if not fallback_odds:
        return False
    existing = dict(w.get("odds") or {})
    for key, val in fallback_odds.items():
        existing.setdefault(key, val)
    w["odds"] = existing
    return True


def _wzbogac_o_kursy_fallback(wyniki: list, top_n: int | None = None) -> None:
    """
    Dla meczów bez kompletnych kursów (home/draw/away) Bzzoiro próbuje uzupełnić
    je dwustopniowo:
      1. API-Football /odds (reuse APISPORTS_KEY + budżet, brak anti-bot) — priorytet.
      2. SofaScore (scraper Playwright) jako drugi fallback, gdy AF nie znalazł kursów
         lub nie uzupełnił wszystkich rynków.

    NIE nadpisuje istniejących kursów Bzzoiro (i nie nadpisuje kursów AF kursami
    SofaScore) — wzbogaca tylko brakujące/puste klucze.
    """
    braki = [
        w for w in wyniki
        if not all((w.get("odds") or {}).get(k) for k in ("home", "draw", "away"))
    ]
    if not braki:
        return
    if top_n is not None:
        braki = braki[:top_n]

    console.print(f"[dim]Fallback kursów: API-Football dla {len(braki)} meczów bez kursów Bzzoiro...[/dim]")

    uzupelniono_af = 0
    nadal_braki = []
    for w in braki:
        g = w.get("gospodarz", "")
        a = w.get("goscie", "")
        data_meczu = w.get("data") or w.get("date") or ""
        if not g or not a:
            continue
        try:
            af_odds = fetch_odds_af(g, a, data_meczu)
        except (OSError, RuntimeError, ValueError) as e:
            log.debug("API-Football odds fallback error %s vs %s: %s", g, a, e)
            af_odds = None

        if _uzupelnij_kursy(w, af_odds):
            uzupelniono_af += 1

        if not all((w.get("odds") or {}).get(k) for k in ("home", "draw", "away")):
            nadal_braki.append(w)

    console.print(f"[cyan]API-Football fallback kursów: uzupełniono {uzupelniono_af}/{len(braki)} meczów[/cyan]")

    if not nadal_braki:
        return

    try:
        from footstats.scrapers.sofascore_odds import fetch_odds, PLAYWRIGHT_OK
        from footstats.scrapers.form_scraper import _sofa_session
    except ImportError:
        console.print("[dim]sofascore_odds niedostępny — pomijam 2. fallback kursów[/dim]")
        return

    if not PLAYWRIGHT_OK:
        console.print("[yellow]SofaScore niedostępny (Playwright) — pomijam 2. fallback kursów[/yellow]")
        return

    console.print(f"[dim]SofaScore (2. fallback): uzupełniam kursy dla {len(nadal_braki)} meczów...[/dim]")

    sess = _sofa_session()
    if sess is None:
        console.print("[yellow]SofaScore: błąd sesji — pomijam 2. fallback kursów[/yellow]")
        return
    p, browser, page = sess

    uzupelniono_sofa = 0
    try:
        for w in nadal_braki:
            g = w.get("gospodarz", "")
            a = w.get("goscie", "")
            data_meczu = w.get("data") or w.get("date") or ""
            if not g or not a:
                continue
            try:
                fallback_odds = fetch_odds(g, a, data_meczu, page=page)
            except (OSError, RuntimeError, ValueError) as e:
                log.debug("SofaScore odds fallback error %s vs %s: %s", g, a, e)
                continue
            if _uzupelnij_kursy(w, fallback_odds):
                uzupelniono_sofa += 1
    finally:
        browser.close()
        p.stop()

    console.print(f"[cyan]SofaScore fallback kursów: uzupełniono {uzupelniono_sofa}/{len(nadal_braki)} meczów[/cyan]")


# ── Krok 4b: Kelly Criterion ──────────────────────────────────────────────────

def _dodaj_kelly(dane: dict, bankroll: float) -> None:
    """Dodaje kelly_stake do każdego zdarzenia w kuponach i top3."""
    try:
        from footstats.core.kelly import kelly_stake
        from footstats.config import AGENT_BANKROLL
        from footstats.core.calibration import get_stake_multiplier, calibration_summary
    except ImportError:
        return

    # Guard: bankroll musi być dodatnią liczbą — DB może zwrócić None
    if not isinstance(bankroll, (int, float)) or bankroll <= 0:
        bankroll = AGENT_BANKROLL

    # Etap 6: kalibracja stawki (Forma Bota 3 kupony + hit-rate 10 kuponów)
    multiplier = get_stake_multiplier()  # łączy oba sygnały
    cal = calibration_summary()
    if cal.get("n", 0) > 0:
        forma_info = f" | Forma3: {cal.get('forma_multiplier', 1.0)}x ({cal.get('forma_note', '')})"
        console.print(
            f"[dim]Kalibracja: hit={cal['hit_rate']:.0%} ({cal['won']}/{cal['n']}) "
            f"→ multiplier={multiplier}x — {cal['note']}{forma_info}[/dim]"
        )
    # Zabezpieczenie: multiplier nigdy None
    if not isinstance(multiplier, (int, float)) or multiplier <= 0:
        multiplier = 1.0
    effective_bankroll = bankroll * multiplier

    try:
        from footstats.core.probability_calibrator import calibrate_confidence
    except ImportError:
        calibrate_confidence = lambda pct: pct / 100.0  # noqa: E731

    for kupon_key in ("kupon_a", "kupon_b", "kupon_c", "kupon_d"):
        for z in dane.get(kupon_key, {}).get("zdarzenia", []):
            p    = calibrate_confidence(z.get("pewnosc_pct") or 50)
            odds = z.get("kurs") or 1.0
            try:
                z["kelly_stake"] = kelly_stake(p, odds, bankroll=effective_bankroll)
            except (TypeError, ZeroDivisionError):
                z["kelly_stake"] = 1.0

    for row in dane.get("top3", []):
        p    = calibrate_confidence(row.get("pewnosc_pct") or 50)
        odds = row.get("kurs") or 1.0
        try:
            row["kelly_stake"] = kelly_stake(p, odds, effective_bankroll)
        except (TypeError, ZeroDivisionError):
            row["kelly_stake"] = 1.0


# ── Krok 6: Walidacja Groq ────────────────────────────────────────────────────

def _waliduj_kupon_groq(dane: dict, stawka: float, kupon_key: str = "kupon_a") -> None:
    from footstats.ai.analyzer import ai_sprawdz_kupon

    kupon     = dane.get(kupon_key, {})
    zdarzenia = kupon.get("zdarzenia", [])
    if not zdarzenia:
        return

    picks_text = "\n".join(
        f"{z.get('nr')}. {z.get('mecz')} | {z.get('typ')} @{z.get('kurs')}"
        for z in zdarzenia
    )
    console.rule(f"[bold cyan]WALIDACJA GROQ — {kupon_key.upper()}[/bold cyan]")
    console.print(ai_sprawdz_kupon(picks_text, stawka=stawka))


# ── Ensemble: roznica_modeli ─────────────────────────────────────────────────

def _oblicz_roznica_modeli(wyniki: list) -> None:
    """
    Oblicza roznica_modeli = max(|P_poisson − P_bzzoiro|) dla win/draw/loss.

    Używa wynik_g/wynik_a z Bzzoiro ML jako przybliżonych lambd Poissona
    (brak potrzeby ładowania bazy historycznej).
    Ustawia pole 'roznica_modeli' in-place na każdym kandydacie.
    """
    try:
        from scipy.stats import poisson as _sps
        from footstats.core.ensemble import ensemble_probs, get_roznica
    except ImportError:
        return

    for k in wyniki:
        pw = k.get("pw", 0) / 100.0
        pr = k.get("pr", 0) / 100.0
        pp = k.get("pp", 0) / 100.0
        if pw + pr + pp < 0.01:
            continue  # brak danych ML Bzzoiro

        p_bzzoiro = {"win": pw, "draw": pr, "loss": pp}

        lh = max(float(k.get("wynik_g", 1) or 1), 0.3)
        la = max(float(k.get("wynik_a", 1) or 1), 0.3)

        p_win = p_draw = p_loss = 0.0
        for i in range(8):
            for j in range(8):
                p = _sps.pmf(i, lh) * _sps.pmf(j, la)
                if i > j:
                    p_win  += p
                elif i == j:
                    p_draw += p
                else:
                    p_loss += p

        p_poisson = {"win": p_win, "draw": p_draw, "loss": p_loss}
        liga = k.get("liga") or None
        p_ens = ensemble_probs(p_poisson, p_bzzoiro, liga=liga)
        k["roznica_modeli"] = round(get_roznica(p_ens, p_poisson, p_bzzoiro), 3)


# ── Faza final: enrichment składów/sędziego ──────────────────────────────────

def _enrichuj_finalna_faza(wyniki: list, api_key: str) -> None:
    """
    Faza final: dla każdego kandydata pobiera składy i sędziego z API-Football.
    Aktualizuje pola lineup_ok, referee_neutral, referee_signal in-place.
    """
    if not api_key:
        console.print("[dim]APISPORTS_KEY niedostępny — pomijam enrichment składów/sędziego[/dim]")
        return

    import requests as _req
    from datetime import date
    from footstats.scrapers.lineup_scraper import get_lineup
    from footstats.scrapers.referee_db import referee_signal, get_referee
    from footstats.scrapers.flashscore_match import scrape_match_with_search
    from footstats.core.lineup_strength import (
        lineup_confidence_penalty_v2, lineup_offensive_strength,
    )

    dzis = date.today().isoformat()
    try:
        resp = _req.get(
            "https://v3.football.api-sports.io/fixtures",
            params={"date": dzis, "status": "NS"},
            headers={"x-apisports-key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        fixtures = resp.json().get("response", [])
    except (OSError, ValueError, KeyError) as e:
        console.print(f"[yellow]API-Football fixtures: {e} — pomijam enrichment[/yellow]")
        return

    # Indeks (norm_home, norm_away) → fixture_data
    idx: dict = {}
    for f in fixtures:
        teams = f.get("teams", {})
        fh = _norm(teams.get("home", {}).get("name", ""))
        fa = _norm(teams.get("away", {}).get("name", ""))
        if fh and fa:
            idx[(fh, fa)] = f

    enriched = 0
    for k in wyniki:
        gh = _norm(k.get("gospodarz", ""))
        ga = _norm(k.get("goscie", ""))

        fixture = idx.get((gh, ga))
        if fixture is None:
            for (fh, fa), f in idx.items():
                if (gh in fh or fh in gh) and (ga in fa or fa in ga):
                    fixture = f
                    break
        if fixture is None:
            continue

        fixture_id = fixture.get("fixture", {}).get("id")

        # Składy
        if fixture_id:
            lineup = get_lineup(fixture_id, api_key)
            k["lineup_ok"] = (
                lineup is not None
                and not lineup.get("home", {}).get("missing_key_players", True)
                and not lineup.get("away", {}).get("missing_key_players", True)
            )
            # Faza 2: siła składu wg goal_share (brak topowego strzelca w XI → kara)
            if lineup is not None:
                gs_h = _goal_shares_for(k.get("gospodarz") or "", "home")
                gs_a = _goal_shares_for(k.get("goscie") or "", "away")
                k["lineup_star_penalty"] = lineup_confidence_penalty_v2(lineup, gs_h, gs_a)
                k["lineup_strength_home"] = round(
                    lineup_offensive_strength((lineup.get("home", {}) or {}).get("startXI", []), gs_h), 3)
                k["lineup_strength_away"] = round(
                    lineup_offensive_strength((lineup.get("away", {}) or {}).get("startXI", []), gs_a), 3)
        else:
            k["lineup_ok"] = None

        # Sędzia
        ref_name = (fixture.get("fixture", {}).get("referee") or "").split(",")[0].strip()
        if ref_name:
            ref_data = get_referee(ref_name)
            sig = referee_signal(ref_name)
            k["referee_neutral"] = sig in ("NEUTRALNY", "NIEZNANY")
            k["referee_name"] = ref_name
            k["referee_signal"] = sig
            if ref_data:
                k["referee_avg_y"] = ref_data.get("avg_yellow")
                k["referee_matches"] = ref_data.get("n_matches")

        # Fallback Flashscore (jeśli brak sędziego lub dla topowych kuponów)
        # Pobieramy absencje tylko jeśli mecz jest 'ciekawy' lub jesteśmy w fazie FINAL
        szukaj_fs = not k.get("referee_name")
        if szukaj_fs:
            fs_data = scrape_match_with_search(k.get("gospodarz"), k.get("goscie"))
            if fs_data.get("success"):
                if not k.get("referee_name") and fs_data.get("referee"):
                    k["referee_name"] = fs_data["referee"]
                    k["referee_signal"] = referee_signal(fs_data["referee"])
                    # Spróbuj jeszcze raz pobrać statystyki dla nowego nazwiska
                    ref_data = get_referee(fs_data["referee"])
                    if ref_data:
                        k["referee_avg_y"] = ref_data.get("avg_yellow")

                # Absencje Flashscore
                abs_h = [f"{a['name']} ({a['reason']})" for a in fs_data["absences"]["home"]]
                abs_a = [f"{a['name']} ({a['reason']})" for a in fs_data["absences"]["away"]]
                if abs_h: k["fs_absencje_g"] = ", ".join(abs_h)
                if abs_a: k["fs_absencje_a"] = ", ".join(abs_a)

                if fs_data.get("stadium"):
                    k["stadium"] = fs_data["stadium"]

        enriched += 1
        console.print(
            f"[dim]  {k.get('gospodarz')} vs {k.get('goscie')}: "
            f"lineup_ok={k.get('lineup_ok')} | sędzia={k.get('referee_signal', 'N/A')}[/dim]"
        )

    console.print(f"[cyan]Final enrichment: {enriched}/{len(wyniki)} kandydatów wzbogacono[/cyan]")


def _zapisz_next_final_txt(wyniki: list) -> None:
    """
    Zapisuje czas uruchomienia fazy final (pierwszy mecz − 70 min) do data/next_final.txt.
    Fallback: 13:30 gdy brak danych o godzinie meczu.
    """
    from datetime import datetime as _dt, timedelta
    from pathlib import Path

    DATA_DIR = Path(__file__).parents[3] / "data"
    DATA_DIR.mkdir(exist_ok=True)

    czasy = []
    # (format, ile znaków wartości). Wcześniej fmt[:len(val[:16])] ucinał format
    # (np. ISO "%Y-%m-%dT%H:%M:%S"→"...%H:%M:%" z gołym %) → kickoff ISO 'T'
    # NIGDY się nie parsował → faza final spadała na fallback 13:30 (zły -70min).
    _FORMATY = (
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%d %H:%M", 16),
        ("%H:%M", 5),
    )
    for k in wyniki:
        for pole in ("kickoff", "godzina", "datetime", "data", "time", "date"):
            val = k.get(pole)
            if val and isinstance(val, str):
                for fmt, n in _FORMATY:
                    try:
                        t = _dt.strptime(val[:n], fmt)
                        if t.hour > 0:  # ignoruj daty bez godziny
                            czasy.append(t)
                        break
                    except ValueError:
                        continue

    if czasy:
        pierwszy = min(czasy)
        final_time = pierwszy - timedelta(minutes=70)
        txt = final_time.strftime("%H:%M")
    else:
        txt = "13:30"  # fallback: mecze popołudniowe

    out = DATA_DIR / "next_final.txt"
    out.write_text(txt, encoding="utf-8")
    console.print(f"[dim]next_final.txt → {txt} (czas startu fazy final)[/dim]")
