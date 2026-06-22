"""FootStats CLI – wyodrebnione czyste komendy/helpery (MODUL 18, refactor).

Funkcje przeniesione z cli.py: bez zaleznosci od stanu globalnego/petli
interaktywnej, jedynie parametry wejsciowe i rendering Rich.
"""
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table
from rich import box

from footstats.utils.console import console
from footstats.core.importance import ImportanceIndex
from footstats.core.fatigue import HeurystaZmeczeniaRotacji
from footstats.core.h2h import AnalizaH2H
from footstats.core.fortress import HomeFortress
from footstats.core.classifier import KlasyfikatorMeczu
from footstats.core.form import AnalizaDomWyjazd
from footstats.scrapers.bzzoiro import _bzz_parse_prob
from footstats.ai.analyzer import (
    ai_analiza_pewniaczki, ai_sprawdz_kupon, ai_groq_dostepny,
)


def _wyswietl_ai_pewniaczki(dane: dict, stawka: float = 5.0):
    """Renderuje wynik JSON z ai_analiza_pewniaczki() za pomocą Rich."""
    if "top3" not in dane:
        raw = dane.get("_raw") or dane.get("uzasadnienie") or str(dane)
        console.print(Panel(
            str(raw),
            title="[bold yellow]🤖 AI – Analiza Pewniaczków + Kupony[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        ))
        return

    # TOP 3
    tbl = Table(
        title="🥇 TOP 3 Pojedyncze Typy",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold yellow",
        padding=(0, 1),
    )
    tbl.add_column("Mecz", style="cyan", no_wrap=True, max_width=32)
    tbl.add_column("Typ", style="bold white", justify="center", width=6)
    tbl.add_column("Kurs", justify="right", width=6)
    tbl.add_column("EV netto", justify="right", width=10)
    tbl.add_column("Uzasadnienie", style="dim")

    for t in dane.get("top3", []):
        ev = t.get("ev_netto")
        try:
            ev_str = f"[green]+{float(ev):.1f}%[/green]" if ev is not None and float(ev) > 0 else f"[red]{float(ev):.1f}%[/red]"
        except (TypeError, ValueError):
            ev_str = str(ev) if ev is not None else "?"
        tbl.add_row(
            t.get("mecz", "?"),
            t.get("typ", "?"),
            str(t.get("kurs", "?")),
            ev_str,
            t.get("uzasadnienie", ""),
        )
    console.print(tbl)

    def _kupon_panel(kupon: dict, title: str, color: str):
        if not kupon:
            return
        lines = []
        for z in kupon.get("zdarzenia", []):
            lines.append(f"  {z.get('nr', '?')}. {z.get('mecz', '?')}  [bold]{z.get('typ', '?')}[/bold] @ {z.get('kurs', '?')}")
        kl = kupon.get("kurs_laczny", "?")
        wn = kupon.get("wygrana_netto", "?")
        lines.append(f"\n  Kurs łączny: [bold]{kl}[/bold]  →  Stawka {stawka:.0f} PLN  →  [bold green]~{wn} PLN netto[/bold green]")
        console.print(Panel(
            "\n".join(lines),
            title=f"[bold {color}]{title}[/bold {color}]",
            border_style=color,
            padding=(0, 1),
        ))

    _kupon_panel(dane.get("kupon_a"), "💰 KUPON A  (~50 PLN)", "green")
    _kupon_panel(dane.get("kupon_b"), "🚀 KUPON B  (~100 PLN)", "magenta")

    ost = dane.get("ostrzezenia")
    if ost:
        console.print(Panel(
            f"[yellow]{ost}[/yellow]",
            title="[bold red]⚠️  Ryzyka[/bold red]",
            border_style="red",
            padding=(0, 2),
        ))

#  MODUL 18 - GLOWNA PETLA
# ================================================================

def _ai_blok_pewniaczki(wyniki_p: list):
    """
    Blok AI po wyswietleniu Szybkich Pewniakow.
    Pyta czy uruchomic analize Groq, wyswietla wynik i oferuje
    sprawdzenie wlasnego kuponu.
    """
    if not wyniki_p:
        return
    if not ai_groq_dostepny():
        console.print("[dim yellow]AI niedostepne – dodaj GROQ_API_KEY w .env (opcja K)[/dim yellow]")
        return

    if not Confirm.ask(
        "[bold yellow]🤖 Analiza AI + propozycja kuponów (Groq llama-3.1-8b)?[/bold yellow]",
        default=True,
    ):
        return

    # Analiza listy pewniaczków
    console.print("[dim yellow]AI analizuje typy...[/dim yellow]")
    try:
        with Progress(SpinnerColumn(style="yellow"),
                      TextColumn("[yellow]Groq: analizuję pewniaczki...[/yellow]"),
                      console=console, transient=True) as pg:
            pg.add_task("", total=None)
            analiza = ai_analiza_pewniaczki(wyniki_p)
        _wyswietl_ai_pewniaczki(analiza)
    except (ValueError, KeyError, RuntimeError, OSError) as e:
        console.print(f"[red]AI blad: {e}[/red]")
        return

    # Opcja: sprawdz wlasny kupon
    if not Confirm.ask("[dim]Sprawdzić własny kupon przez AI?[/dim]", default=False):
        return

    console.print(
        "[dim]Wpisz typy kuponu, np.:[/dim]\n"
        "[dim cyan]PSG 1X @1.31, Bayern wygrana @1.55, Leverkusen 1 @1.88[/dim cyan]"
    )
    picks_text = Prompt.ask("[bold cyan]Twój kupon[/bold cyan]").strip()
    if not picks_text:
        return

    try:
        stawka_str = Prompt.ask("[yellow]Stawka (PLN)[/yellow]", default="5")
        stawka = float(stawka_str)
    except ValueError:
        stawka = 5.0

    console.print("[dim yellow]AI sprawdza kupon...[/dim yellow]")
    try:
        with Progress(SpinnerColumn(style="cyan"),
                      TextColumn("[cyan]Groq: oceniam kupon...[/cyan]"),
                      console=console, transient=True) as pg:
            pg.add_task("", total=None)
            ocena = ai_sprawdz_kupon(picks_text, stawka, wzorzec_ml=wyniki_p)
        console.print(Panel(
            ocena,
            title="[bold cyan]🤖 AI – Ocena Twojego Kuponu[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        ))
    except (ValueError, KeyError, RuntimeError, AttributeError) as e:
        console.print(f"[red]AI blad: {e}[/red]")


def _reinicjuj_systemy(df_tabela, df_wyniki, n_druzyn, kod_ligi):
    """Tworzy/odswierza wszystkie systemy analityczne po zmianie ligi."""
    return {
        "importance":     ImportanceIndex(df_tabela, n_druzyn),
        "heurystyka_eng": HeurystaZmeczeniaRotacji(df_wyniki),
        "h2h_sys":        AnalizaH2H(df_wyniki),
        "fortress_sys":   HomeFortress(df_wyniki),
        "klasyfikator":   KlasyfikatorMeczu(df_wyniki, kod_ligi),
        "dw_sys":         AnalizaDomWyjazd(df_wyniki),
    }


def _wyswietl_menu_startowe(bzzoiro):
    """
    Ekran startowy po walidacji kluczy API.
    Daje mozliwosc uruchomienia Szybkich Pewniaczek 48h (opcja P)
    PRZED zaladowaniem jakiejkolwiek ligi – zero reqow FDB.
    """
    console.print()
    if bzzoiro:
        console.print(Panel(
            "[bold yellow]⚡ P[/bold yellow]  – [bold yellow]Szybkie Pewniaczki 48h[/bold yellow]  "
            "[dim](Bzzoiro ML, Scout Bot EV, bez ladowania ligi)[/dim]\n"
            "[bold]Enter[/bold] – Zaladuj konkretna lige i pelna analize",
            border_style="dim yellow",
            title="[dim]Co chcesz zrobic?[/dim]",
            padding=(0, 2),
        ))
    else:
        console.print(Panel(
            "[bold]Enter[/bold]  Zaladuj konkretna lige\n"
            "[dim yellow]Dodaj klucz BZZOIRO_KEY aby odblokować Szybkie Pewniaczki[/dim yellow]",
            border_style="dim",
            title="[dim]Start[/dim]",
            padding=(0, 2),
        ))
    console.print()


def _analiza_kuponu(bzzoiro):
    """
    Opcja A - Analiza Kuponu Bukmacherskiego.
    Uzytkownik wpisuje mecze z kuponu, Scout Bot ocenia EV i ryzyko.

    Format: Gospodarz vs Goscie | TYP | KURS
    Typy:   1  X  2  1X  X2  12  BTTS  Over2.5  Under2.5
    """
    console.print(Panel(
        "[bold]Wpisz mecze z kuponu[/bold] - jeden na linie:\n"
        "[dim]Format:  Gospodarz vs Goscie | TYP | KURS\n"
        "Przyklad: Real Madryt vs Getafe | 1 | 1.40\n"
        "          Leeds vs Sunderland | 1X | 1.26\n"
        "Typy: 1  X  2  1X  X2  12  BTTS  Over2.5  Under2.5\n"
        "Pusty wiersz = koniec[/dim]",
        border_style="magenta",
        title="[bold magenta]ANALIZA KUPONU – Scout Bot[/bold magenta]",
        padding=(0, 2)
    ))

    wpisy = []
    while True:
        linia = Prompt.ask("[dim magenta]>[/dim magenta]", default="").strip()
        if not linia:
            break
        wpisy.append(linia)

    if not wpisy:
        console.print("[yellow]Brak wpisow.[/yellow]")
        return

    mecze_kuponu = []
    for linia in wpisy:
        czesci = [c.strip() for c in linia.split("|")]
        mecz_str = czesci[0] if czesci else linia
        typ_str  = czesci[1].upper().strip() if len(czesci) > 1 else "?"
        try:
            kurs = float(czesci[2].replace(",", ".")) if len(czesci) > 2 else None
        except (ValueError, IndexError):
            kurs = None
        druz = [d.strip() for d in mecz_str.replace(" - ", " vs ").split(" vs ", 1)]
        g = druz[0] if druz else mecz_str
        a = druz[1] if len(druz) > 1 else "?"
        mecze_kuponu.append({"g": g, "a": a, "typ": typ_str, "kurs": kurs})

    if not mecze_kuponu:
        console.print("[yellow]Brak poprawnych wpisow.[/yellow]")
        return

    bzz_indeks = {}
    if bzzoiro and getattr(bzzoiro, "_valid", False):
        console.print("[dim]Pobieranie ML Bzzoiro...[/dim]")
        try:
            for ev in bzzoiro.predykcje_tygodnia():
                g_b = str(ev.get("gosp", "") or "").strip().lower()
                a_b = str(ev.get("gosc", "") or "").strip().lower()
                if g_b and a_b:
                    bzz_indeks[g_b + "|" + a_b] = ev
        except (ValueError, KeyError, RuntimeError, OSError, ConnectionError) as ex:
            console.print(f"[yellow]Bzzoiro: {ex}[/yellow]")

    TYP_MAP = {
        "1": "pw", "X": "pr", "2": "pp",
        "1X": "pw_pr", "X2": "pr_pp", "12": "pw_pp",
        "BTTS": "bt", "BTTSTAK": "bt",
        "OVER2.5": "o25", "UNDER2.5": "u25",
    }

    console.print()
    kurs_aku = 1.0
    ev_lista = []

    for mc in mecze_kuponu:
        g, a, typ, kurs = mc["g"], mc["a"], mc["typ"], mc["kurs"]
        console.rule(
            f"[bold white]{g}[/bold white] vs [bold white]{a}[/bold white]"
            + (f"  [dim]{typ}  @{kurs}[/dim]" if kurs else f"  [dim]{typ}[/dim]")
        )

        klucz_ml = g.lower() + "|" + a.lower()
        ev_ml = bzz_indeks.get(klucz_ml)
        p_model = None
        ml_info = "[dim]Brak ML (sprawdz nazwy druzyn)[/dim]"

        if ev_ml:
            wyp = _bzz_parse_prob(ev_ml.get("pred_ml"))
            if wyp:
                pw, pr, pp, bt, o25 = wyp
                u25 = round(100 - o25, 1)
                probs = {
                    "pw": pw, "pr": pr, "pp": pp,
                    "pw_pr": pw+pr, "pr_pp": pr+pp, "pw_pp": pw+pp,
                    "bt": bt, "o25": o25, "u25": u25,
                }
                ml_info = (
                    f"[dim]ML: 1={pw:.0f}%  X={pr:.0f}%  2={pp:.0f}%  "
                    f"BTTS={bt:.0f}%  Ov2.5={o25:.0f}%[/dim]"
                )
                typ_k = typ.replace(" ", "").replace(".", "").upper()
                p_model = probs.get(TYP_MAP.get(typ_k))

        console.print("  " + ml_info)

        ev_str = "–"
        ocena  = "[dim]brak danych[/dim]"
        ev_val = None
        if p_model is not None and kurs:
            ev_val = round(p_model / 100.0 * kurs - 1.0, 3)
            ev_str = f"{ev_val*100:+.1f}%"
            if ev_val > 0.05:
                ocena = "[bold green]WARTOSC+[/bold green]"
            elif ev_val > 0.01:
                ocena = "[green]LEKKO+[/green]"
            elif ev_val >= -0.01:
                ocena = "[dim]NEUTRALNY[/dim]"
            elif kurs and kurs < 1.35:
                ocena = "[yellow]NISKI KURS[/yellow]"
            else:
                ocena = "[red]EV UJEMNY[/red]"
            ev_lista.append(ev_val)

        p_str = f"[cyan]{p_model:.0f}%[/cyan]" if p_model is not None else "[dim]?[/dim]"
        k_str = f"[yellow]@{kurs}[/yellow]" if kurs else "[dim]brak kursu[/dim]"
        console.print(
            f"  Typ: [bold]{typ}[/bold]  Kurs: {k_str}  "
            f"P_ML: {p_str}  EV: {ev_str}  {ocena}"
        )
        if kurs and kurs < 1.3:
            console.print("  [yellow]Kurs < 1.30 – jedna strata kasuje kilka zyskow w AKU[/yellow]")
        if p_model is not None and p_model < 55:
            console.print(f"  [red]P_ML={p_model:.0f}% < 55% – ryzykowny typ[/red]")
        if kurs:
            kurs_aku *= kurs
        console.print()

    console.rule("[bold]Podsumowanie kuponu[/bold]")
    console.print(f"  Kurs AKU: [bold yellow]{kurs_aku:.2f}[/bold yellow]")
    if ev_lista:
        ev_aku = 1.0
        for e in ev_lista:
            ev_aku *= (1 + e)
        ev_aku -= 1.0
        kol = "green" if ev_aku > 0 else ("yellow" if ev_aku > -0.1 else "red")
        console.print(
            f"  EV kuponu: [{kol}]{ev_aku*100:+.1f}%[/{kol}]  "
            f"[dim](na {len(ev_lista)}/{len(mecze_kuponu)} zdarzeniach z ML)[/dim]"
        )
        if ev_aku > 0.02:
            console.print("  [bold green]Kupon na plusie EV[/bold green]")
        elif ev_aku < -0.15:
            console.print("  [red]Kupon zdecydowanie ujemny EV – niepolecany[/red]")
        else:
            console.print("  [yellow]EV bliski zeru – typowe kursy bookmaker[/yellow]")
    else:
        console.print("  [dim]Brak danych ML do obliczenia EV.[/dim]")
    console.print()
