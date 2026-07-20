"""
FootStats Daily Agent — warstwa prezentacji (output)
====================================================
Console (rich), separatory, zapis kuponu do .txt, powiadomienia Windows,
tabele wyników. Wydzielone z `daily_agent.py` (dekompozycja god-modułu,
wzorem `superbet`/`cli`/`analyzer`). Behavior-preserving — `daily_agent`
re-importuje te symbole, więc istniejące ścieżki i patch-targety działają.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


# ── Separatory / błędy ────────────────────────────────────────────────────────

def _sep(tytul: str):
    console.rule(f"[bold cyan]{tytul}[/bold cyan]")


def _blad(msg: str):
    console.print(f"[bold red]BŁĄD:[/bold red] {msg}")
    sys.exit(1)


# ── Zapis kuponu do .txt ──────────────────────────────────────────────────────

def _zapisz_txt(dane: dict, stawka_a: float, stawka_b: float) -> Path:
    """Zapisuje kupon do F:/bot/logs/kupon_YYYY-MM-DD.txt. Zwraca ścieżkę."""
    dzis = datetime.now().strftime("%Y-%m-%d")
    sciezka = LOGS_DIR / f"kupon_{dzis}.txt"

    linie: list[str] = []
    linie.append(f"FootStats Daily Agent — {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    linie.append("=" * 60)

    for label, kupon_key, stawka in [
        ("KUPON A", "kupon_a", stawka_a),
        ("KUPON B", "kupon_b", stawka_b),
        ("KUPON C", "kupon_c", stawka_a),
        ("KUPON D", "kupon_d", stawka_a),
    ]:
        kupon     = dane.get(kupon_key, {})
        zdarzenia = kupon.get("zdarzenia", [])
        if not zdarzenia:
            continue
        linie.append(f"\n{label} — stawka {stawka:.0f} PLN")
        linie.append("-" * 40)
        for z in zdarzenia:
            verified = "✓" if z.get("_verified") else " "
            linie.append(
                f"  {z.get('nr', '?')}. [{verified}] {z.get('mecz','?')}  |  "
                f"{z.get('typ','?')}  @{z.get('kurs', 0):.2f}"
            )
        kurs_l = kupon.get("kurs_laczny", 0) or 0
        wyg    = stawka * kurs_l * 0.88
        linie.append(f"  Kurs łączny: {kurs_l:.2f}  |  Wygrana netto: {wyg:.2f} PLN")

    top3 = dane.get("top3") or []
    if top3:
        linie.append("\nTOP 3 MECZÓW")
        linie.append("-" * 40)
        for i, row in enumerate(top3, 1):
            ev = row.get("ev_netto", 0) or 0
            linie.append(
                f"  {i}. {row.get('mecz','?')}  {row.get('typ','?')}  "
                f"@{row.get('kurs', 0):.2f}  EV={ev:+.1f}%"
            )
            uzas = row.get("uzasadnienie", "")
            if uzas:
                linie.append(f"     {uzas}")

    if dane.get("ostrzezenia"):
        linie.append("\nOSTRZEŻENIA")
        linie.append(str(dane["ostrzezenia"]))

    tekst = "\n".join(linie) + "\n"
    sciezka.write_text(tekst, encoding="utf-8")
    console.print(f"[dim]Kupon zapisany: {sciezka}[/dim]")
    return sciezka


# ── Powiadomienie Windows ─────────────────────────────────────────────────────

def _powiadomienie_windows(tytul: str, tekst: str) -> None:
    """Wyświetla Windows toast notification przez PowerShell (bez dodatkowych pakietów)."""
    ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.BalloonTipTitle = '{tytul.replace("'", "''")}'
$n.BalloonTipText  = '{tekst.replace("'", "''")}'
$n.BalloonTipIcon  = 'Info'
$n.ShowBalloonTip(8000)
Start-Sleep -Milliseconds 8500
$n.Dispose()
"""
    try:
        # fire-and-forget: OK, powiadomienie Windows (czekanie blokuje pipeline)
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        console.print(f"[dim]Powiadomienie nieudane: {e.__class__.__name__}: {e}[/dim]")


# ── Wyświetlanie wyników ──────────────────────────────────────────────────────

def _wyswietl(dane: dict, stawka_a: float, stawka_b: float):
    if "top3" not in dane:
        console.print("[yellow]Brak danych JSON — surowa odpowiedź Groq:[/yellow]")
        console.print(dane.get("_raw", "brak"))
        return

    _sep("TOP 3 MECZÓW")
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("#", width=2)
    t.add_column("Mecz", min_width=32)
    t.add_column("Typ", width=8)
    t.add_column("Kurs", width=6)
    t.add_column("EV%", width=8)
    t.add_column("Uzasadnienie")
    for i, row in enumerate(dane.get("top3") or [], 1):
        ev = row.get("ev_netto", 0) or 0
        kolor = "green" if ev > 5 else "yellow"
        t.add_row(
            str(i),
            row.get("mecz", "?"),
            row.get("typ", "?"),
            f"{row.get('kurs', 0):.2f}",
            f"[{kolor}]{ev:+.1f}%[/{kolor}]",
            row.get("uzasadnienie", ""),
        )
    console.print(t)

    for label, kupon_key, stawka in [
        ("KUPON A", "kupon_a", stawka_a),
        ("KUPON B", "kupon_b", stawka_b),
        ("KUPON C", "kupon_c", stawka_a),
        ("KUPON D", "kupon_d", stawka_a),
    ]:
        kupon = dane.get(kupon_key, {})
        zdarzenia = kupon.get("zdarzenia", [])
        if not zdarzenia:
            continue

        _sep(f"{label} — stawka {stawka:.0f} PLN")
        t2 = Table(show_header=True, header_style="bold blue")
        t2.add_column("#", width=2)
        t2.add_column("Mecz", min_width=30)
        t2.add_column("Typ", width=8)
        t2.add_column("Kurs", width=6)
        t2.add_column("Pewnosc", width=8)
        t2.add_column("Kelly", width=8)
        t2.add_column("Zrodlo", width=10)
        for z in zdarzenia:
            zrodlo  = "[green]Bzzoiro[/green]" if z.get("_verified") else "[dim]Groq[/dim]"
            pct     = z.get("pewnosc_pct")
            pct_str = f"{pct}%" if pct else "?"
            kelly   = z.get("kelly_stake")
            k_str   = f"[cyan]{kelly}PLN[/cyan]" if kelly else "?"
            t2.add_row(
                str(z.get("nr", "")),
                z.get("mecz", "?"),
                z.get("typ", "?"),
                f"{z.get('kurs', 0):.2f}",
                pct_str,
                k_str,
                zrodlo,
            )
        console.print(t2)

        kurs_l  = kupon.get("kurs_laczny", 0) or 0
        wyg     = stawka * kurs_l * 0.88
        szansa  = kupon.get("szansa_wygranej_pct")
        szansa_str = f"  |  Szansa: [bold {'green' if szansa and szansa >= 40 else 'yellow'}]{szansa}%[/bold {'green' if szansa and szansa >= 40 else 'yellow'}]" if szansa else ""
        console.print(
            f"  Kurs łączny: [bold]{kurs_l:.2f}[/bold]  |  "
            f"Wygrana netto: [bold green]{wyg:.2f} PLN[/bold green]"
            f"{szansa_str}"
        )

    if dane.get("ostrzezenia"):
        console.print()
        console.print(Panel(
            str(dane["ostrzezenia"]),
            title="[yellow]Ostrzeżenia[/yellow]",
            border_style="yellow",
        ))
