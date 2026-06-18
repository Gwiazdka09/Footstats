import time
from datetime import datetime, timedelta
from rich.table import Table
from rich.panel import Panel
from rich import box
from footstats.utils.console import console
from footstats.utils.helpers import _s
from footstats.config import PEWNIACZEK_PROG
from footstats.scrapers.bzzoiro import BzzoiroClient, _bzz_parse_prob
from footstats.core.weekly_picks import _typy_pewne
from footstats.core.probability_calibrator import calibrate_confidence

#  MODUL 13d – SZYBKIE PEWNIACZKI (2 DNI) + SCOUT BOT  (v2.7.1)
# ================================================================
#
#  Dostepne PRZED zaladowaniem ligi (w glownym menu startowym).
#  Nie wymaga zadnych reqow poza Bzzoiro (juz zaladowanym na start).
#
#  Szybkie Pewniaczki 48h:
#    - Skanuje nadchodzace 48h z Bzzoiro ML
#    - Filtruje typy >= prog%
#    - Grupuje wg dni
#    - Pokazuje kursy bukmacherskie z Bzzoiro
#
#  Scout Bot – ocena ryzyka przed meczem:
#    - Dla kazdego pewniaczka: ocenia dodatkowe czynniki ryzyka
#    - Sprawdza spread kursow (niski kurs = mala wartosc)
#    - Liczy wartosc oczekiwana: EV = P * kurs - 1
#    - Ostrzega gdy ML sugeruje zbyt duza pewnosc (overconfidence)
#    - Ocenia: ZYSK (+) / NEUTRALNY (0) / STRATA (-) na dluga mete
#
#  Analiza kuponu:
#    - Ocenia wprowadzony kupon bukmacherski
#    - Sprawdza kazdy mecz przez Bzzoiro ML
#    - Wylicza EV kazdego zdarzenia i AKU
# ================================================================


def szybkie_pewniaczki_2dni(
    bzzoiro: "BzzoiroClient",
    prog: float = PEWNIACZEK_PROG,
    godziny: int = 48,
    df_mecze: object = None,
) -> list:
    """
    Skanuje nadchodzace mecze (domyslnie 48h) z Bzzoiro ML.

    Nie wymaga zaladowania zadnej ligi. Dziala wylacznie na danych ML.
    Kazdy mecz oceniany jest przez Scout Bot (EV, wartosc zakl., ryzyko).

    Parametry:
        bzzoiro  – klient BzzoiroClient
        prog     – minimalny prog pewnosci (domyslnie 75%)
        godziny  – horyzont czasowy w godzinach (domyslnie 48)

    Zwraca liste slownikow z pewniaczkami + ocena Scout Bota.
    """
    if not bzzoiro or not getattr(bzzoiro, "_valid", False):
        console.print("[yellow]Bzzoiro niedostepne – brak danych ML.[/yellow]")
        return []

    if df_mecze is None:
        try:
            from footstats.data.historical_loader import load_cached
            df_mecze = load_cached()
        except (FileNotFoundError, ImportError, OSError, ValueError):
            df_mecze = None

    # Data-quality guard: waliduj df_mecze (kolumny/typy) przed użyciem w Poissonie.
    # Gdy niepoprawny → log + df_mecze=None (Poisson pominięty, zostaje Bzzoiro ML).
    if df_mecze is not None:
        try:
            from footstats.utils.logging import waliduj_df_wyniki
            if not waliduj_df_wyniki(df_mecze, "df_mecze (quick_picks)"):
                df_mecze = None
        except ImportError:
            pass

    teraz    = datetime.now()
    granica  = teraz + timedelta(hours=godziny)

    console.print(f"[dim]🔍 Skanowanie Bzzoiro ML na {godziny}h...[/dim]")
    try:
        lista_ml = bzzoiro.predykcje_tygodnia()
    except (RuntimeError, OSError, ValueError) as e:
        console.print(f"[red]Bzzoiro blad: {e}[/red]")
        return []

    # 11.4: Understat xG prefetch dla drużyn z top-5 lig przed pętlą Poissona
    try:
        from footstats.scrapers.understat_xg import fetch_team_xg, _to_slug, _cache_get
        from footstats.config import LIGI_POISSON_TOP5
        _season = teraz.year if teraz.month >= 7 else teraz.year - 1
        _top5_vals = set(LIGI_POISSON_TOP5.values())
        _top5_teams = {
            t for m in lista_ml
            if (m.get("liga") or "") in _top5_vals
            for t in (m.get("gospodarz", ""), m.get("goscie", ""))
            if t
        }
        _missing = [t for t in _top5_teams if not _cache_get(_to_slug(t), _season)]
        if _missing:
            console.print(f"[dim]xG prefetch top-5: {len(_missing)} drużyn...[/dim]")
            for _team in _missing:
                try:
                    fetch_team_xg(_team, _season)
                except (OSError, ValueError, RuntimeError):
                    pass
    except (ImportError, AttributeError):
        pass

    # 11.9 + A1(06-17): Inicjalizacja systemów λ przed pętlą.
    # fortress/h2h/heurystyka/klasyfikator budowane z df_mecze (historia).
    # ImportanceIndex POMINIĘTY — wymaga tabeli ligi (standings), niedostępnej
    # w ścieżce Bzzoiro. Patrz TODO A1 (źródło standings).
    fortress_sys = None
    h2h_sys = None
    heur_sys = None
    klas_sys = None
    if df_mecze is not None:
        try:
            from footstats.core.fortress import HomeFortress
            from footstats.core.h2h import AnalizaH2H
            from footstats.core.fatigue import HeurystaZmeczeniaRotacji
            from footstats.core.classifier import KlasyfikatorMeczu
            fortress_sys = HomeFortress(df_mecze)
            h2h_sys      = AnalizaH2H(df_mecze)
            heur_sys     = HeurystaZmeczeniaRotacji(df_mecze)
            klas_sys     = KlasyfikatorMeczu(df_mecze)
        except (ImportError, AttributeError):
            pass

    console.print(f"[dim]   Pobrano {len(lista_ml)} wydarzen.[/dim]")

    wyniki = []
    for ev in lista_ml:
        g    = str(ev.get("gosp",  "") or "").strip()
        a    = str(ev.get("gosc",  "") or "").strip()
        liga = str(ev.get("liga",  "") or "?")
        d    = str(ev.get("data",  "") or "")[:10]
        godz = str(ev.get("godzina","") or "–")[:5]

        if not g or not a or not d:
            continue

        # Pomiń mecze już rozegrane lub w trakcie
        status = str(ev.get("status", "") or "").lower()
        if status and status not in ("notstarted", "scheduled", ""):
            continue

        # Filtruj tylko mecze w horyzoncie czasowym
        try:
            dm = datetime.strptime(
                f"{d} {godz}" if godz not in ("–","") else d,
                "%Y-%m-%d %H:%M" if godz not in ("–","") else "%Y-%m-%d"
            )
        except ValueError:
            try:
                dm = datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                continue
        if not (teraz <= dm <= granica):
            continue

        pred_ml = ev.get("pred_ml")
        odds    = ev.get("odds") or {}

        if not pred_ml:
            continue

        # Parsuj ML przez universalny parser (wszystkie formaty Bzzoiro)
        wyp = _bzz_parse_prob(pred_ml)
        if wyp is None:
            continue
        pw_raw, pr_raw, pp_raw, bt_raw, o25_raw = wyp

        # ── 11.2: Probability Calibrator — koryguje overconfidence ML ──
        # Surowe prob Bzzoiro: 70% → realna ~62% historycznie.
        # calibrate_confidence(0-100) -> 0-1, ×100 by zachowac format.
        pw  = round(calibrate_confidence(pw_raw)  * 100.0, 1)
        pr  = round(calibrate_confidence(pr_raw)  * 100.0, 1)
        pp  = round(calibrate_confidence(pp_raw)  * 100.0, 1)
        # A3 (06-17): kalibracja per-wynik łamie sumę 1X2 (≠100%) — renormalizuj
        # do prawidłowego rozkładu (1/X/2 to zdarzenia rozłączne i wyczerpujące).
        _s1x2 = pw + pr + pp
        if _s1x2 > 0:
            pw  = round(pw / _s1x2 * 100.0, 1)
            pr  = round(pr / _s1x2 * 100.0, 1)
            pp  = round(pp / _s1x2 * 100.0, 1)
        bt  = round(calibrate_confidence(bt_raw)  * 100.0, 1)
        o25 = round(calibrate_confidence(o25_raw) * 100.0, 1)
        u25 = round(100.0 - o25, 1)

        # ── 11.4+11.9: Poisson ensemble z fortress/h2h — blend z Bzzoiro ──
        # A2 (06-17): wagi per-liga z ensemble_probs (domyślnie 70/30 Poisson/Bzzoiro,
        # Faza 16.4) zamiast sztywnego 50/50. Wagi są teraz realnie używane i strojone.
        poisson_blend = False
        _fort_g = None
        _h2h_g  = None
        _h2h_a  = None
        if df_mecze is not None:
            try:
                from footstats.core.poisson import predict_match
                from footstats.core.ensemble import ensemble_probs
                _fort_g = fortress_sys.analiza(g) if fortress_sys else None
                _h2h_g  = h2h_sys.analiza(g, a)  if h2h_sys  else None
                _h2h_a  = h2h_sys.analiza(a, g)  if h2h_sys  else None
                # A1: zmęczenie/rotacja + typ meczu (stage=LIGA dla danych Bzzoiro)
                _heur_g = heur_sys.analiza(g, d) if heur_sys else None
                _heur_a = heur_sys.analiza(a, d) if heur_sys else None
                _klas = klas_sys.klasyfikuj(g, a, "REGULAR_SEASON", d) if klas_sys else None
                _pred_p = predict_match(
                    g, a, df_mecze,
                    heurystyka_g=_heur_g, heurystyka_a=_heur_a,
                    h2h_g=_h2h_g, h2h_a=_h2h_a,
                    fortress_g=_fort_g, klasyfikacja=_klas,
                )
                if _pred_p:
                    _p_pois = {"pw": _pred_p["p_wygrana"], "pr": _pred_p["p_remis"],
                               "pp": _pred_p["p_przegrana"], "bt": _pred_p["btts"],
                               "o25": _pred_p["over25"]}
                    _p_bzz  = {"pw": pw, "pr": pr, "pp": pp, "bt": bt, "o25": o25}
                    _bl = ensemble_probs(_p_pois, _p_bzz, liga=liga)
                    pw  = round(_bl["pw"], 1)
                    pr  = round(_bl["pr"], 1)
                    pp  = round(_bl["pp"], 1)
                    bt  = round(_bl["bt"], 1)
                    o25 = round(_bl["o25"], 1)
                    u25 = round(100.0 - o25, 1)
                    poisson_blend = True
            except (ImportError, AttributeError, ValueError, KeyError, TypeError):
                pass  # Poisson niedostępny → zostaw Bzzoiro

        # Zbierz typy pewne (na skalibrowanych prob)
        typy = _typy_pewne(pw, pr, pp, bt, o25, u25, g, a, prog)
        if not typy:
            continue

        # ── Scout Bot: ocena wartosci kazdego typu ──────────────────
        # Expected Value (EV) = P_skalibrowane * kurs - 1
        # EV > 0 = zysk na dluga mete, EV < 0 = strata
        scout = _scout_bot_ocen(typy, odds, pw, pr, pp, bt, o25, u25)

        # Oczekiwany wynik (most likely score ML)
        ms = (pred_ml.get("most_likely_score") or {})
        wg = int(ms.get("home", 1)); wa = int(ms.get("away", 0))

        wyniki.append({
            "data":       d,
            "godzina":    godz,
            "dt":         dm,           # datetime do sortowania
            "gospodarz":  g,
            "goscie":     a,
            "liga":       liga,
            "typy":       typy,
            "pw": pw, "pr": pr, "pp": pp,
            "bt": bt, "o25": o25,
            "pw_raw": pw_raw, "pr_raw": pr_raw, "pp_raw": pp_raw,
            "bt_raw": bt_raw, "o25_raw": o25_raw,
            "wynik_g":    wg,
            "wynik_a":    wa,
            "odds":         odds,
            "scout":        scout,
            "poisson_blend": poisson_blend,
            "fortress_g":   _fort_g,
            "h2h_g":        _h2h_g,
        })

    # Sortuj: najpierw czasowo, potem najlepsza szansa malejaco
    wyniki.sort(key=lambda x: (x["dt"], -max(v for _, v in x["typy"])))
    return wyniki


def _scout_bot_ocen(
    typy: list,
    odds: dict,
    pw: float, pr: float, pp: float,
    bt: float, o25: float, u25: float,
) -> dict:
    """
    Scout Bot: ocenia wartosc kazdego typu przez pryzmat EV i spread.

    Logika:
      EV = P_model * kurs_bukmacher - 1.0
      EV > 0   → zysk w dlugim terminie (warto brac)
      EV 0.0   → neutralnie
      EV < 0   → strata strukturalna (bookmaker ma przewage)

    Oceny ryzyka:
      ✅ WARTOSC  – EV > +3% i ML >= 70%
      ⚡ SLABA    – EV 0-3% lub ML 60-70%
      ⚠️  UWAGA   – kurs < 1.3 (bookmaker zabezpiecza sie nisko)
      ❌ STRATA   – EV < 0 (bookmaker przecenia szanse)

    Parametry:
        typy  – lista (opis, szansa%) z _typy_pewne()
        odds  – dict kursow z Bzzoiro {home, draw, away, btts, over_2_5 ...}
        pw..u25 – prawdopodobienstwta z ML (%)

    Zwraca slownik: {oceny: [(opis, ev, ocena_str)], best_ev, ostrzezenia}
    """
    # Mapowanie typow na prawdopodobienstwta i klucze kursow
    P_MAP = {
        "1":        (pw,   "home"),
        "1X":       (pw + pr, None),
        "X2":       (pr + pp, None),
        "12":       (pw + pp, None),
        "2":        (pp,   "away"),
        "X":        (pr,   "draw"),
        "BTTS":     (bt,   "btts"),
        "Over 2.5": (o25,  "over_2_5"),
        "Under 2.5":(u25,  "under_2_5"),
    }

    oceny = []
    all_ev = []
    ostrzezenia = []

    for typ_opis, szansa in typy:
        # Dopasuj typ do P_MAP
        p_val = szansa / 100.0   # juz jako ulamek
        kurs  = None
        for klucz, (p_ref, odds_key) in P_MAP.items():
            if klucz in typ_opis.upper() or klucz in typ_opis:
                # Sprawdz kurs
                if odds_key and isinstance(odds, dict):
                    k = odds.get(odds_key)
                    if k:
                        try:
                            kurs = float(str(k).replace(",", "."))
                        except (ValueError, TypeError):
                            kurs = None
                break

        if kurs and kurs > 1.0:
            ev = round(p_val * kurs - 1.0, 3)
        else:
            ev = None

        # Okresl ocene
        if ev is None:
            # Brak kursu – tylko ocena ML
            if szansa >= 82:
                ocena = "✅ ML WYSOKI"
            elif szansa >= 72:
                ocena = "⚡ ML SREDNI"
            else:
                ocena = "⚠️  ML GRANICZNY"
        elif ev > 0.05:
            ocena = "✅ WARTOSC+"     # EV > 5%: wyraznie na plus
        elif ev > 0.01:
            ocena = "⚡ LEKKO+"      # EV 1-5%: slaba wartosc
        elif ev >= -0.01:
            ocena = "➖ NEUTRALNY"   # EV ~0: wash
        elif kurs and kurs < 1.35:
            ocena = "⚠️  NISKI KURS" # Kursy ponizej 1.35 sa ryzykowne w AKU
        else:
            ocena = "❌ EV UJEMNY"   # EV < -1%: strata

        if kurs and kurs < 1.3:
            ostrzezenia.append(
                f"Kurs {kurs} jest bardzo niski – 1 strata kasuje wiele zyskow w AKU"
            )
        if szansa >= 90:
            ostrzezenia.append(
                f"{typ_opis[:20]}: ML {szansa:.0f}% – overconfidence, sprawdz w innym zrodle"
            )

        oceny.append({
            "typ":   typ_opis,
            "ev":    ev,
            "kurs":  kurs,
            "ocena": ocena,
        })
        if ev is not None:
            all_ev.append(ev)

    best_ev = max(all_ev) if all_ev else None

    return {
        "oceny":        oceny,
        "best_ev":      best_ev,
        "ostrzezenia":  list(set(ostrzezenia)),   # deduplikacja
    }


def wyswietl_szybkie_pewniaczki(
    wyniki: list,
    prog: float = PEWNIACZEK_PROG,
    godziny: int = 48,
):
    """
    Wyswietla Szybkie Pewniaczki 48h z ocena Scout Bota.

    Grupuje mecze wg dni.
    Dla kazdego pewniaczka pokazuje:
      - Typy z szansa
      - Kursy bukmacherskie
      - EV (Expected Value) z ocena
      - Ostrzezenia Scout Bota
    """
    if not wyniki:
        console.print(Panel(
            f"[yellow]Brak pewniakow >= {prog:.0f}% w nastepnych {godziny}h.[/yellow]\n"
            "[dim]Sprobuj obnizyc prog lub sprawdz za kilka godzin.[/dim]",
            border_style="yellow", title="Szybkie Pewniaczki"
        ))
        return

    teraz = datetime.now()
    granica_dt = teraz + timedelta(hours=godziny)

    # Naglowek
    console.print(Panel(
        f"[bold yellow]⚡ SZYBKIE PEWNIACZKI  "
        f"[white]{len(wyniki)} meczow >= {prog:.0f}%[/white] ⚡[/bold yellow]\n"
        f"[dim]Teraz: {teraz.strftime('%d.%m %H:%M')} → "
        f"{granica_dt.strftime('%d.%m %H:%M')}  "
        f"| Tylko ML Bzzoiro | Scout Bot EV aktywny[/dim]",
        border_style="yellow",
        title="[bold yellow]⚡ SZYBKIE PEWNIACZKI 48h – FootStats[/bold yellow]",
        padding=(0, 2),
    ))
    console.print()

    # Grupuj wg daty
    dni: dict = {}
    for p in wyniki:
        d = p["data"]
        dni.setdefault(d, []).append(p)

    for dzien, mecze in sorted(dni.items()):
        try:
            dzien_str = datetime.strptime(dzien, "%Y-%m-%d").strftime("%A, %d.%m.%Y")
        except ValueError:
            dzien_str = dzien
        console.print(f"\n[bold cyan]── {dzien_str} ──[/bold cyan]")

        for p in mecze:
            g, a = p["gospodarz"], p["goscie"]
            kol  = "green" if p.get("scout", {}).get("best_ev", -1) and p["scout"]["best_ev"] > 0.03 else "white"

            console.print(
                f"  [bold {kol}]{g} vs {a}[/bold {kol}]  "
                f"[dim]{p['godzina']}  {p['liga']}[/dim]  "
                f"[dim yellow]Typ: {p['wynik_g']}:{p['wynik_a']}[/dim yellow]"
            )
            console.print(
                f"  [dim]ML:  1={p['pw']:.0f}%  X={p['pr']:.0f}%  2={p['pp']:.0f}%  "
                f"BTTS={p['bt']:.0f}%  Over2.5={p['o25']:.0f}%[/dim]"
            )

            # Kursy z Bzzoiro
            odds = p.get("odds", {}) or {}
            if isinstance(odds, dict) and any(odds.values()):
                o1 = odds.get("home", "–"); ox = odds.get("draw", "–"); o2 = odds.get("away", "–")
                console.print(f"  [dim]Kursy: 1={o1}  X={ox}  2={o2}[/dim]")

            # Typy pewne + ocena Scout Bota
            scout = p.get("scout", {})
            oceny_idx = {oc["typ"]: oc for oc in scout.get("oceny", [])}

            t_s = Table(box=box.SIMPLE, show_header=False, pad_edge=False, padding=(0, 1))
            t_s.add_column("Typ",   style="white",        width=28)
            t_s.add_column("Sz.",   style="bold yellow",  width=7,  justify="right")
            t_s.add_column("Kurs",  style="dim cyan",     width=6,  justify="right")
            t_s.add_column("EV",    style="dim",          width=8,  justify="right")
            t_s.add_column("Ocena", style="bold",         width=18)

            for tn, tv in p["typy"]:
                oc    = oceny_idx.get(tn, {})
                kurs  = f"{oc.get('kurs','–')}" if oc.get("kurs") else "–"
                ev    = f"{oc.get('ev',0)*100:+.1f}%" if oc.get("ev") is not None else "–"
                ocena = oc.get("ocena", "")
                # Kolor oceny
                if "WARTOSC" in ocena:  kol_o = "bold green"
                elif "LEKKO"  in ocena: kol_o = "green"
                elif "STRATA" in ocena or "UJEMNY" in ocena: kol_o = "red"
                elif "UWAGA"  in ocena or "NISKI"  in ocena: kol_o = "yellow"
                else:                   kol_o = "dim"
                t_s.add_row(tn, f"{tv:.1f}%", kurs, ev, f"[{kol_o}]{ocena}[/{kol_o}]")

            console.print(t_s)

            # Ostrzezenia Scout Bota
            for ost in scout.get("ostrzezenia", []):
                console.print(f"  [yellow]⚠️  Scout: {ost}[/yellow]")

            console.print()

    # Legenda EV
    console.print(
        "[dim]EV = Expected Value: % zysku/straty na dluga mete per 1 PLN postawiony\n"
        "✅ WARTOSC+ = EV>5%  ⚡ LEKKO+ = EV 1-5%  ➖ = neutralnie  "
        "❌ = strata strukturalna  ⚠️ = niski kurs < 1.35[/dim]\n"
    )


# ================================================================
#  MODUL 18 - GLOWNA PETLA
