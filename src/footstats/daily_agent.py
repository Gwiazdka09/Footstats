"""
FootStats Daily Agent
=====================
Codzienne uruchamianie o 8:00: Bzzoiro → forma → Groq → gotowy kupon.

Użycie:
    python -m footstats.daily_agent
    python -m footstats.daily_agent --stawka 10 --dni 2
    python -m footstats.daily_agent --tylko-kupon   # bez formy (szybciej)
    python -m footstats.daily_agent --waliduj       # + Groq walidacja kuponu A
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from footstats.utils.normalize import normalize_team_name
from footstats.core.checkpoint import save_predictions_batch, load_predictions_batch, list_checkpoints, cleanup_old_checkpoints
from footstats.core.lambda_optimizer import injury_correction

log = logging.getLogger(__name__)

console = Console()

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sep(tytul: str):
    console.rule(f"[bold cyan]{tytul}[/bold cyan]")


def _blad(msg: str):
    console.print(f"[bold red]BŁĄD:[/bold red] {msg}")
    sys.exit(1)


_norm = normalize_team_name


# ── Krok 1: Bzzoiro ───────────────────────────────────────────────────────────

def _pobierz_kandydatow(dni: int = 2) -> tuple[list, dict]:
    """
    Bzzoiro ML → (wyniki, indeks_kursow).
    indeks_kursow: klucz=(norm_gosp, norm_gosc) → {odds, gospodarz, goscie, liga}
    """
    from dotenv import load_dotenv
    load_dotenv()

    from footstats.scrapers.bzzoiro import BzzoiroClient, ENV_BZZOIRO
    from footstats.core.quick_picks import szybkie_pewniaczki_2dni
    from footstats.config import AGENT_KANDYDAT_PROG

    klucz = os.getenv(ENV_BZZOIRO, "")
    if not klucz:
        _blad("Brak BZZOIRO_API_KEY w .env")

    c = BzzoiroClient(klucz)
    ok, msg = c.waliduj()
    if not ok:
        console.print(f"[bold red]Bzzoiro: {msg}[/bold red]")

    wyniki = szybkie_pewniaczki_2dni(c, prog=AGENT_KANDYDAT_PROG, godziny=dni * 24) if ok else []
    console.print(f"[dim]Bzzoiro: {len(wyniki)} kandydatów w oknie {dni*24}h[/dim]")

    # Health-check zrodla (dlug techniczny #2): alert gdy 0 wydarzen / niedostepne.
    try:
        from footstats.utils.telegram_notify import check_and_alert_source_down
        check_and_alert_source_down("Bzzoiro", ok=ok, n_wyniki=len(wyniki))
    except (ImportError, OSError, RuntimeError) as e:
        log.warning("Health-check Bzzoiro nie powiodl sie: %s", e)

    # Buduj indeks: (norm_gosp, norm_gosc) → dane meczu
    indeks: dict = {}
    for w in wyniki:
        g = w.get("gospodarz", "")
        a = w.get("goscie", "")
        indeks[(_norm(g), _norm(a))] = {
            "odds":      w.get("odds", {}),
            "gospodarz": g,
            "goscie":    a,
            "liga":      w.get("liga", ""),
            "pred":      w.get("pred") or {},
        }

    return wyniki, indeks


# ── Krok 3b: Live odds refresh (faza final) ──────────────────────────────────

def _odswiez_kursy_live(indeks: dict, dni: int = 3) -> dict:
    """Re-fetch Bzzoiro odds and update indeks with fresh data."""
    from footstats.scrapers.bzzoiro import BzzoiroClient, ENV_BZZOIRO
    from footstats.core.quick_picks import szybkie_pewniaczki_2dni
    from footstats.config import AGENT_KANDYDAT_PROG

    klucz = os.getenv(ENV_BZZOIRO, "")
    if not klucz:
        console.print("[yellow]Brak BZZOIRO_API_KEY — pomijam odświeżenie kursów[/yellow]")
        return indeks

    try:
        c = BzzoiroClient(klucz)
        ok, msg = c.waliduj()
        if not ok:
            console.print(f"[yellow]Bzzoiro niedostępny: {msg} — używam starych kursów[/yellow]")
            return indeks

        fresh = szybkie_pewniaczki_2dni(c, prog=AGENT_KANDYDAT_PROG, godziny=dni * 24)
        updated = 0
        for w in fresh:
            g = w.get("gospodarz", "")
            a = w.get("goscie", "")
            key = (_norm(g), _norm(a))
            if key in indeks:
                old_odds = indeks[key].get("odds", {})
                new_odds = w.get("odds", {})
                if new_odds and new_odds != old_odds:
                    indeks[key]["odds"] = new_odds
                    updated += 1

        console.print(f"[green]Odświeżono kursy LIVE: {updated}/{len(indeks)} meczów zaktualizowanych[/green]")
    except (OSError, ValueError, KeyError) as e:
        console.print(f"[yellow]Błąd odświeżenia kursów: {e} — używam starych kursów[/yellow]")

    return indeks


# ── Krok 1b/2: enrichment (kontuzje, forma, BetBuilder, inspiracje) ─────────
# Wydzielone do core/daily_phases.py (dług techniczny #3) — re-eksport poniżej.
from footstats.core.daily_phases import (
    _apply_injury_corrections,
    _wzbogac_forme_top,
    _wzbogac_o_betbuilder,
    _wzbogac_o_inspiracje,
    _wzbogac_o_kursy_fallback,
)


# ── Krok 3: Groq AI ───────────────────────────────────────────────────────────

def _analizuj_groq(
    wyniki: list,
    cel_wygrana_a: float | None = None,
    cel_wygrana_b: float | None = None,
    stawka: float = 10.0,
) -> dict:
    from footstats.ai.analyzer import ai_analiza_pewniaczki, ai_groq_dostepny
    if not ai_groq_dostepny():
        _blad("Brak GROQ_API_KEY w .env")
    console.print("[dim]Groq: analizuję i buduję kupony...[/dim]")
    return ai_analiza_pewniaczki(
        wyniki,
        pobierz_forme=False,
        cel_wygrana_a=cel_wygrana_a,
        cel_wygrana_b=cel_wygrana_b,
        stawka=stawka,
    )


# ── Krok 4: Weryfikacja halucynacji ──────────────────────────────────────────

_TYP_DO_ODDS_KEY = {
    "1":           "home",
    "2":           "away",
    "x":           "draw",
    "over 2.5":    "over_2_5",
    "over":        "over_2_5",
    "o2.5":        "over_2_5",
    "under 2.5":   "under_2_5",
    "under":       "under_2_5",
    "btts":        "btts",
    "obie strzelą": "btts",
}


# FAZA 17.2: twardy filtr longshotów
_MAX_KURS_LONGSHOT = 4.0      # kurs > 4.0 ⇒ implied prob < 25% = longshot
_MIN_PROB_MODELU = 40.0       # p_modelu < 40% ⇒ odrzuć (model nie wspiera typu)


def _prob_modelu_dla_typu(typ: str, pred: dict) -> float | None:
    """Prawdopodobieństwo modelu (%) dla danego typu tipa. None jeśli brak danych."""
    if not pred:
        return None
    t = typ.strip().lower()
    if t in ("1", "1x"):
        return pred.get("p_wygrana")
    if t == "x":
        return pred.get("p_remis")
    if t in ("2", "x2"):
        return pred.get("p_przegrana")
    if t.startswith("over"):
        return pred.get("over25")
    if t.startswith("under"):
        return pred.get("under25")
    if t == "btts":
        return pred.get("btts")
    return None


def _powod_odrzucenia_longshot(typ: str, kurs: float | None, pred: dict) -> str | None:
    """Zwraca powód odrzucenia nogi (longshot) lub None jeśli noga OK."""
    if kurs is not None and kurs > _MAX_KURS_LONGSHOT:
        return f"kurs {kurs:.2f} > {_MAX_KURS_LONGSHOT} (longshot)"
    p_mod = _prob_modelu_dla_typu(typ, pred)
    if p_mod is not None and p_mod < _MIN_PROB_MODELU:
        return f"p_modelu {p_mod:.0f}% < {_MIN_PROB_MODELU:.0f}%"
    return None


def _znajdz_mecz(mecz_str: str, indeks: dict) -> dict | None:
    """
    Próbuje dopasować string 'Drużyna A vs Drużyna B' do indeksu Bzzoiro.
    Zwraca wpis indeksu lub None jeśli brak dopasowania.
    """
    parts = mecz_str.lower().replace(" - ", " vs ").split(" vs ")
    if len(parts) != 2:
        return None
    ng, na = _norm(parts[0].strip()), _norm(parts[1].strip())

    # 1. Dokładne dopasowanie
    if (ng, na) in indeks:
        return indeks[(ng, na)]

    # 2. Częściowe dopasowanie (substring w obu kierunkach)
    for (ig, ia), dane in indeks.items():
        if (ng in ig or ig in ng) and (na in ia or ia in na):
            return dane

    return None


def _weryfikuj_noge(z: dict, indeks: dict, usuniete: list[str]) -> dict | None:
    """
    Weryfikuje pojedynczą nogę (top3 row lub zdarzenie kuponu):
    - mecz musi istnieć w Bzzoiro i mieć realny kurs dla typu (inaczej usuń)
    - podmienia kurs na rzeczywisty Bzzoiro/BetExplorer (anty-halucynacja Groq)
    - twardy filtr longshotów (17.2)
    Zwraca zmodyfikowaną nogę lub None jeśli odrzucona (dopisuje powód do `usuniete`).
    """
    mecz_str = z.get("mecz", "")
    typ_raw  = z.get("typ", "").strip()
    wpis     = _znajdz_mecz(mecz_str, indeks)

    if wpis is None:
        usuniete.append(f"{mecz_str} [{typ_raw}] — brak w Bzzoiro")
        return None

    odds_key    = _TYP_DO_ODDS_KEY.get(typ_raw.lower())
    rzeczywisty = (wpis["odds"] or {}).get(odds_key) if odds_key else None
    if not rzeczywisty:
        usuniete.append(f"{mecz_str} [{typ_raw}] — brak realnego kursu w Bzzoiro (kurs Groq niezweryfikowany)")
        return None

    z["kurs"]      = float(rzeczywisty)
    z["mecz"]      = f"{wpis['gospodarz']} vs {wpis['goscie']}"
    z["_verified"] = True

    # 11.6: Arbitraż — porównaj z BetExplorer cache (bez Playwright)
    try:
        from footstats.scrapers.kursy import najlepszy_kurs_z_cache
        be = najlepszy_kurs_z_cache(wpis["gospodarz"], wpis["goscie"])
        if be:
            _be_map = {"odds_1": be.get("k1"), "odds_x": be.get("kX"), "odds_2": be.get("k2")}
            be_kurs = _be_map.get(odds_key)
            if be_kurs and be_kurs > z["kurs"]:
                z["kurs"]   = float(be_kurs)
                z["_zrodlo"] = "betexplorer"
    except (ImportError, AttributeError, TypeError):
        pass

    # FAZA 17.2: twardy filtr longshotów (na finalnym kursie + pred Poissona)
    powod = _powod_odrzucenia_longshot(typ_raw, z.get("kurs"), wpis.get("pred") or {})
    if powod:
        usuniete.append(f"{mecz_str} [{typ_raw}] — {powod}")
        return None

    return z


def _weryfikuj_kupony(dane: dict, indeks: dict) -> dict:
    """
    Weryfikuje top3 + każdą nogę w kupon_a..d przez Bzzoiro (anty-halucynacja Groq):
    - podmienia kurs na rzeczywisty lub usuwa nogę bez realnego kursu
    - twardy filtr longshotów (17.2)
    Zwraca zmodyfikowany słownik dane.
    """
    usuniete: list[str] = []

    # FAZA 17.3: top3 też weryfikowane (wcześniej halucynacje wchodziły do predictions)
    top3 = dane.get("top3", [])
    if top3:
        zweryfikowane_top3 = [
            z for z in (_weryfikuj_noge(row, indeks, usuniete) for row in top3) if z is not None
        ]
        dane["top3"] = zweryfikowane_top3

    for kupon_key in ("kupon_a", "kupon_b", "kupon_c", "kupon_d"):
        kupon = dane.get(kupon_key, {})
        zdarzenia = kupon.get("zdarzenia", [])
        if not zdarzenia:
            continue

        zweryfikowane = [
            z for z in (_weryfikuj_noge(z, indeks, usuniete) for z in zdarzenia) if z is not None
        ]

        # Przenumeruj
        for i, z in enumerate(zweryfikowane, 1):
            z["nr"] = i

        # Przelicz kurs łączny i wygraną
        if zweryfikowane:
            kurs_l = 1.0
            for z in zweryfikowane:
                kurs_l *= z.get("kurs", 1.0)
            kupon["zdarzenia"]   = zweryfikowane
            kupon["kurs_laczny"] = round(kurs_l, 2)
        else:
            dane[kupon_key] = {}

    if usuniete:
        ostrzegawcze = dane.get("ostrzezenia", "") or ""
        dane["ostrzezenia"] = ostrzegawcze + "\n⚠️  USUNIĘTE HALUCYNACJE: " + " | ".join(usuniete)
        console.print(f"[red]Usunięto {len(usuniete)} halucynowanych nóg:[/red]")
        for u in usuniete:
            console.print(f"  [dim]- {u}[/dim]")

    return dane


# ── Krok 5a: Zapis do pliku TXT ──────────────────────────────────────────────

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

    top3 = dane.get("top3", [])
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


# ── Krok 5b: Powiadomienie Windows ───────────────────────────────────────────

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


# ── Krok 5: Wyświetl wyniki ───────────────────────────────────────────────────

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
    for i, row in enumerate(dane.get("top3", []), 1):
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


# ── Krok 1b: API-Football Ekstraklasa ───────────────────────────────────────

def _pobierz_apifootball_ekstraklasa(dni: int = 3) -> list[dict]:
    """Dociąga kandydatów z Ekstraklasy przez API-Football (jeśli klucz dostępny)."""
    from dotenv import load_dotenv
    load_dotenv()
    klucz = os.getenv("APISPORTS_KEY", "").strip()
    if not klucz:
        return []
    try:
        from footstats.scrapers.api_football import APIFootball
        af = APIFootball(klucz)
        return af.kandydaci_liga(api_id=106, godziny=dni * 24, prog_pw=0.50)
    except (OSError, ValueError, KeyError) as e:
        console.print(f"[dim]API-Football Ekstraklasa: {e}[/dim]")
        return []


# ── Krok 4b/6: Kelly Criterion + walidacja Groq (core/daily_phases.py) ─────
from footstats.core.daily_phases import _dodaj_kelly, _waliduj_kupon_groq


# ── CLI ───────────────────────────────────────────────────────────────────────

# ── Ensemble + faza final + decision score helpers (core/daily_phases.py) ──
from footstats.core.daily_phases import (
    _oblicz_roznica_modeli,
    _enrichuj_finalna_faza,
    _zapisz_next_final_txt,
)


# ── Nowe: fazy i decision score ────────────────────────────────────────────

from footstats.core.daily_filters import (
    _pre_filtruj_kursy, _pre_filtruj_tokenow,
    _pre_filtruj_value_bet, _pre_filtruj_ligi,
)

def _ocen_zdarzenia_decision_score(dane: dict, phase: str = "draft") -> None:
    """
    Oblicza Decision Score dla nóg kuponu PO KROKU 3 (Groq).
    Teraz 'pewnosc_pct' i 'ev_netto' są rzeczywiste — scoring ma sens.
    Annotuje zdarzenia polem 'decision_score'. Nie usuwa nóg z kuponu.
    """
    from footstats.core.decision_score import score_kandydat, PROG_DRAFT, PROG_FINAL
    threshold = PROG_FINAL if phase == "final" else PROG_DRAFT

    _sep(f"DECISION SCORE — post-Groq [{phase.upper()}] (próg ≥ {threshold})")

    for kupon_key in ("kupon_a", "kupon_b", "kupon_c", "kupon_d"):
        zdarzenia = dane.get(kupon_key, {}).get("zdarzenia", [])
        if not zdarzenia:
            continue
        console.print(f"[dim]{kupon_key.upper()}:[/dim]")
        for z in zdarzenia:
            pct = z.get("pewnosc_pct") or 50
            w = {
                "ev_netto":       z.get("ev_netto", 0),
                "pewnosc":        pct,   # score_kandydat auto-normalizuje int>1 → /100
                "czynniki":       z.get("czynniki", []),
                "roznica_modeli": z.get("roznica_modeli", 0.0),
                "accuracy":       z.get("accuracy"),
            }
            ctx = {
                "lineup_ok":       z.get("lineup_ok"),
                "referee_neutral": z.get("referee_neutral", True),
            }
            sc, reasons = score_kandydat(w, context=ctx, phase=phase)
            # BetBuilder leg z pozytywnym EV dostaje bonus — Poisson math potwierdza edge
            if z.get("betbuilder") and (z.get("ev_netto") or 0) > 0:
                sc += 5
                reasons.append("BetBuilder leg EV>0 (+5)")
            z["decision_score"] = sc
            z["decision_reasons"] = reasons
            ikona = "[green]✅[/green]" if sc >= threshold else "[yellow]⚠️ [/yellow]"
            console.print(
                f"  {ikona} {z.get('mecz', '?')} [{z.get('typ', '?')}] "
                f"score={sc}/{threshold} | pewność={pct}%"
            )


def _decision_score_kandydat(kandydat: dict, phase: str = "draft") -> tuple[int, list[str]]:
    """Wrapper — konwertuje kandydata Bzzoiro → format decision_score."""
    from footstats.core.decision_score import score_kandydat
    w = {
        "ev_netto":       kandydat.get("ev_netto", 0),
        "pewnosc":        kandydat.get("pewnosc", 0.5),
        "czynniki":       kandydat.get("czynniki", []),
        "roznica_modeli": kandydat.get("roznica_modeli", 0.0),
        "accuracy":       kandydat.get("accuracy", 0.0),
    }
    context = {
        "lineup_ok":       kandydat.get("lineup_ok", None),
        "referee_neutral": kandydat.get("referee_neutral", True),
    }
    return score_kandydat(w, context=context, phase=phase)


def _filtruj_przez_decision_score(
    kandydaci: list[dict],
    phase: str = "draft",
    prog: int | None = None,
) -> list[dict]:
    """
    Filtruje kandydatów przez decision_score.
    Dodaje 'decision_score' i 'decision_reasons' do każdego kandydata.
    Zwraca tylko kandydatów >= prog.
    """
    from footstats.core.decision_score import PROG_DRAFT, PROG_FINAL
    threshold = prog if prog is not None else (PROG_FINAL if phase == "final" else PROG_DRAFT)

    wynik = []
    for k in kandydaci:
        sc, reasons = _decision_score_kandydat(k, phase=phase)
        k["decision_score"] = sc
        k["decision_reasons"] = reasons
        if sc >= threshold:
            wynik.append(k)
    return wynik


from footstats.core.daily_io import _zapisz_kupon_do_db

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FootStats Daily Agent")
    p.add_argument("--stawka",      type=float, default=10.0, help="Stawka kupon A (PLN, domyslnie 10)")
    p.add_argument("--stawka-b",    type=float, default=5.0,  help="Stawka kupon B (PLN, domyslnie 5)")
    p.add_argument("--dni",         type=int,   default=3,    help="Horyzont w dniach (domyslnie 3)")
    p.add_argument("--tylko-kupon", action="store_true",      help="Pomiń formę SofaScore")
    p.add_argument("--waliduj",     action="store_true",      help="Uruchom walidację Groq kuponu A")
    p.add_argument("--cel-a",       type=float, default=None, help="Cel wygranej netto kupon A (PLN)")
    p.add_argument("--cel-b",       type=float, default=None, help="Cel wygranej netto kupon B (PLN)")
    p.add_argument("--faza",        choices=["draft", "final"], default=None,
                   help="Faza: draft (08:00, bez skladow) lub final (1h przed meczem, ze skladami)")
    p.add_argument("--date",        default=None,
                   help="Data YYYY-MM-DD (domyslnie: dzis) — etykieta logów i update_pending")
    p.add_argument("--dry-run",     action="store_true",
                   help="Tryb podgladu: nie zapisuje do DB, TXT, nie wysyla Telegram/Windows")
    p.add_argument("--system-paper", action="store_true",
                   help="Twórz single-leg kupony na koncie System (paper-trading, per-tip ROI)")
    p.add_argument("--bb",          action="store_true",
                   help="Pobierz realne kursy BetBuilder z Superbet API + sygnaly Strefy Inspiracji (wolno, ~3-5min)")
    return p


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    from dotenv import load_dotenv
    load_dotenv()

    args = _build_parser().parse_args()

    from footstats.config import AGENT_BANKROLL
    from footstats.core.bankroll import (
        get_current_bankroll, check_daily_stop_loss,
        get_stake_multiplier, check_weekly_alert, get_loss_streak,
        is_agent_paused, check_and_auto_pause, get_weekly_drawdown,
    )
    from footstats.utils.admin_user import resolve_admin_user_id

    admin_uid = resolve_admin_user_id()
    current_bankroll = get_current_bankroll(user_id=admin_uid)
    date_label = args.date or datetime.now().strftime("%Y-%m-%d")
    dry_tag    = "  [yellow]⚠ DRY-RUN[/yellow]" if args.dry_run else ""

    # 15.1: Pause check (weekly stop-loss)
    if not args.dry_run and is_agent_paused():
        console.print("[bold red]⛔ AGENT ZAPAUZOWANY (stop-loss 20% tygodniowy). Wznów przez dashboard.[/bold red]")
        try:
            from footstats.utils.telegram_notify import send_alert
            send_alert("FootStats PAUSED", "Agent zapauzowany (stop-loss). Wznów przez dashboard → Bankroll.")
        except (ImportError, OSError, RuntimeError):
            pass
        return

    # Daily stop-loss check
    if not args.dry_run and check_daily_stop_loss(user_id=admin_uid):
        console.print("[bold red]STOP-LOSS: dzienna strata >= 10% bankrolla — przerywam.[/bold red]")
        return

    # Streak detection
    streak = get_loss_streak(user_id=admin_uid)
    stake_mult = get_stake_multiplier(user_id=admin_uid)
    if streak >= 3:
        console.print(f"[yellow]STREAK: {streak} przegranych z rzędu → stawki x{stake_mult:.0%}[/yellow]")
        args.stawka = round(args.stawka * stake_mult, 1)
        args.stawka_b = round(args.stawka_b * stake_mult, 1)

    # 15.1: Weekly drawdown → auto-pause jeśli >= 20%
    if not args.dry_run and check_and_auto_pause(user_id=admin_uid):
        dd = get_weekly_drawdown(user_id=admin_uid)
        console.print(f"[bold red]⛔ STOP-LOSS: tygodniowy drawdown {dd:.1%} >= 20% — PAUZUJĘ agenta![/bold red]")
        try:
            from footstats.utils.telegram_notify import send_stop_loss_alert
            send_stop_loss_alert(dd, current_bankroll)
        except (ImportError, OSError, RuntimeError):
            pass
        return
    elif check_weekly_alert(user_id=admin_uid):
        console.print("[bold yellow]ALERT: tygodniowy drawdown przekroczył 20% bankrolla![/bold yellow]")

    # Rolling accuracy alert (ciche — nie blokuje agenta)
    try:
        from footstats.utils.telegram_notify import check_and_alert_accuracy
        check_and_alert_accuracy(threshold_pct=35.0, window=20)
    except (ImportError, OSError, RuntimeError):
        pass

    console.print()
    console.print(Panel(
        f"[bold]FootStats Daily Agent[/bold]  |  {date_label}{dry_tag}\n"
        f"Horyzont: {args.dni} dni  |  Stawka A: {args.stawka} PLN  |  Stawka B: {args.stawka_b} PLN  |  Bankroll: {current_bankroll} PLN",
        border_style="cyan",
    ))

    # Krok 0: Auto-update wynikow pending meczow (pomijamy w dry-run)
    _sep("KROK 0 — Auto-update wynikow")
    if args.dry_run:
        console.print("[yellow]DRY-RUN: pomijam update_pending[/yellow]")
    else:
        try:
            from footstats.scrapers.results_updater import update_pending
            stats_upd = update_pending(days_back=3, dry_run=False, verbose=True)
            if stats_upd["updated"] > 0:
                console.print(f"[green]Zaktualizowano {stats_upd['updated']} wynikow w backtest.db[/green]")
        except (OSError, RuntimeError) as e:
            console.print(f"[dim]Auto-update wynikow: {e}[/dim]")

        # Krok 0b: Analiza porażek AI (Pętla Feedbacku) — uruchamiana po update wyników
        try:
            from footstats.ai.post_match_analyzer import analizuj_porazki
            stats_fb = analizuj_porazki(days_back=14, dry_run=False)
            if stats_fb["analyzed"] > 0:
                console.print(
                    f"[dim]Pętla Feedbacku: przeanalizowano {stats_fb['analyzed']} porażek[/dim]"
                )
        except (OSError, RuntimeError) as e:
            console.print(f"[dim]Analiza porażek (feedback): {e}[/dim]")

        # Krok 0c: Rozliczenie ACTIVE kuponów (Settlement)
        try:
            from footstats.core.coupon_settlement import settle_active_coupons
            stats_settle = settle_active_coupons(days_back=7, dry_run=False, verbose=True)
            if stats_settle["settled"] > 0:
                console.print(
                    f"[green]Rozliczono {stats_settle['settled']} kuponów | "
                    f"Częściowych: {stats_settle['partial']} | Błędów: {stats_settle['errors']}[/green]"
                )
        except (OSError, RuntimeError) as e:
            console.print(f"[dim]Błąd settlement kuponów: {e}[/dim]")

    # Krok 0d: Aktualizacja statystyk sędziów z Zawodtyper (raz dziennie)
    try:
        from footstats.scrapers.zawodtyper_referees import fetch_referees_zawodtyper
        fetch_referees_zawodtyper()
        console.print("[green]✓ Sędziowie zaktualizowani z Zawodtyper[/green]")
    except (OSError, RuntimeError) as e:
        console.print(f"[dim]Referee update: {e}[/dim]")

    _sep("KROK 1 — Bzzoiro ML")
    wyniki, indeks = _pobierz_kandydatow(dni=args.dni)

    # Checkpoint: save predictions batch for recovery
    batch_id = f"daily_{datetime.now():%Y%m%d_%H%M}"
    save_predictions_batch(wyniki, batch_id=batch_id)
    log.info(f"Checkpoint saved: {batch_id} ({len(wyniki)} predictions)")

    # Krok 1a: Propozycje dnia konta 'System' (low/medium/high, shared) — raz dziennie (faza draft)
    if args.faza == "draft" and not args.dry_run:
        try:
            from footstats.scrapers.bzzoiro import BzzoiroClient, ENV_BZZOIRO
            from footstats.core.system_coupons import generate_system_coupons

            klucz_sys = os.getenv(ENV_BZZOIRO, "")
            if klucz_sys:
                c_sys = BzzoiroClient(klucz_sys)
                ok_sys, _ = c_sys.waliduj()
                if ok_sys:
                    nowe = generate_system_coupons(c_sys.predykcje_tygodnia())
                    if nowe:
                        console.print(f"[green]✓ Konto 'System': {len(nowe)} nowych propozycji dnia (shared)[/green]")
        except (OSError, RuntimeError, ValueError) as e:
            console.print(f"[dim]Propozycje dnia 'System': {e}[/dim]")

    # Krok 1b: Dociagnij Ekstraklase z API-Football jesli dostepny
    wyniki_ekstra = _pobierz_apifootball_ekstraklasa(args.dni)
    if wyniki_ekstra:
        console.print(f"[dim]API-Football Ekstraklasa: +{len(wyniki_ekstra)} kandydatow[/dim]")
        wyniki = wyniki + wyniki_ekstra
        for w in wyniki_ekstra:
            g = w.get("gospodarz", "")
            a = w.get("goscie", "")
            indeks[(_norm(g), _norm(a))] = {
                "odds": w.get("odds", {}), "gospodarz": g, "goscie": a, "liga": w.get("liga", "")
            }

    if not wyniki:
        _blad("Bzzoiro nie zwrocilo zadnych kandydatow.")

    # Ensemble: oblicz roznica_modeli (Poisson vs Bzzoiro) dla każdego kandydata
    _oblicz_roznica_modeli(wyniki)

    # xG prefetch z Understat (wypełnia cache przed pętlą Poissona)
    try:
        from footstats.scrapers.understat_xg import fetch_team_xg, _to_slug, _cache_get
        from datetime import datetime as _dt
        _season = _dt.now().year if _dt.now().month >= 7 else _dt.now().year - 1
        _teams = {w.get("gospodarz", "") for w in wyniki} | {w.get("goscie", "") for w in wyniki}
        _missing = [t for t in _teams if t and not _cache_get(_to_slug(t), _season)]
        if _missing:
            console.print(f"[dim]xG prefetch: {len(_missing)} drużyn z Understat...[/dim]")
            for _team in _missing:
                try:
                    fetch_team_xg(_team, _season)
                except (OSError, ValueError, RuntimeError):
                    pass
    except (ImportError, AttributeError):
        pass

    # -- Pre-filtr tokenów: odrzuca mecze bez pełnej nazwy drużyny lub ligi ──
    n_przed_token = len(wyniki)
    wyniki = _pre_filtruj_tokenow(wyniki)
    if len(wyniki) < n_przed_token:
        console.print(
            f"[dim]Pre-filtr tokenów (brak nazw/ligi): "
            f"{n_przed_token} → {len(wyniki)} kandydatów[/dim]"
        )

    # -- Pre-filtr kursów: oszczędza tokeny Groq (odrzuca <1.15 i >15.0) ───────
    n_przed_filter = len(wyniki)
    wyniki = _pre_filtruj_kursy(wyniki)
    if len(wyniki) < n_przed_filter:
        console.print(
            f"[dim]Pre-filtr kursów (1.15–15.0): "
            f"{n_przed_filter} → {len(wyniki)} kandydatów[/dim]"
        )

    # -- Pre-filtr lig (blacklist): odrzuca ligi z udowodnionym brakiem edge ──
    from footstats.config import LIGA_FILTER_ENABLED
    if LIGA_FILTER_ENABLED:
        n_przed_liga = len(wyniki)
        wyniki = _pre_filtruj_ligi(wyniki)
        if len(wyniki) < n_przed_liga:
            console.print(
                f"[dim]Pre-filtr lig (blacklist): "
                f"{n_przed_liga} → {len(wyniki)} kandydatów[/dim]"
            )

    # -- Pre-filtr value bet: EV > 3% i Kelly > 1% (tylko kandydaci z kursami) ──
    n_przed_ev = len(wyniki)
    wyniki = _pre_filtruj_value_bet(wyniki)
    if len(wyniki) < n_przed_ev:
        console.print(
            f"[dim]Pre-filtr value bet (EV/Kelly): "
            f"{n_przed_ev} → {len(wyniki)} kandydatów[/dim]"
        )

    # -- Faza draft/final: enrichment składów/sędziego (Decision Score → po Groq) ──
    if args.faza:
        _sep(f"FAZA {args.faza.upper()} — Składy + Sędzia (API-Football)")
        _enrichuj_finalna_faza(wyniki, os.getenv("APISPORTS_KEY", ""))
        console.print(f"[cyan]{args.faza.capitalize()}: {len(wyniki)} kandydatów po wzbogaceniu o składy/sędziego[/cyan]")

        # 11.5: Korekta BTTS/Over2.5 per sędzia (po enrichmencie)
        try:
            from footstats.scrapers.referee_db import referee_prob_adjustment
            for k in wyniki:
                sig = k.get("referee_signal")
                if sig:
                    d_over, d_btts = referee_prob_adjustment(sig)
                    if d_over or d_btts:
                        k["o25"] = max(0.0, min(100.0, (k.get("o25") or 0.0) + d_over))
                        k["bt"]  = max(0.0, min(100.0, (k.get("bt")  or 0.0) + d_btts))
        except ImportError:
            pass

        if args.faza == "draft":
            _zapisz_next_final_txt(wyniki)

    if not args.tylko_kupon:
        _sep("KROK 2 — Forma SofaScore")
        _wzbogac_forme_top(wyniki, top_n=12)
        _wzbogac_o_betbuilder(wyniki, pobierz_superbet=args.bb)
        if args.bb:
            _wzbogac_o_inspiracje(wyniki)
        _apply_injury_corrections(wyniki)

    # D6/D1b: fallback kursów SofaScore — uzupełnia mecze bez kursów Bzzoiro
    # (egzotyki, MŚ), żeby System paper-trading mógł je typować (wymaga kursu).
    if getattr(args, "system_paper", False) and not args.dry_run:
        _sep("KROK 2a — Fallback kursów SofaScore")
        try:
            _wzbogac_o_kursy_fallback(wyniki)
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            console.print(f"[yellow]Fallback kursów SofaScore pominięty: {e}[/yellow]")

    # FAZA 19: paper-trading bota — single-leg kupony System (per-tip ROI/win rate)
    if getattr(args, "system_paper", False) and not args.dry_run:
        _sep("KROK 2b — System paper-trading (single-leg)")
        try:
            from footstats.core.system_paper import build_single_leg_coupons
            n = build_single_leg_coupons(wyniki)
            console.print(f"[cyan]System: utworzono {n} single-leg kuponów na koncie System[/cyan]")
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            console.print(f"[yellow]System paper-trading pominięty: {e}[/yellow]")

    _sep("KROK 3 — Groq AI")
    dane = _analizuj_groq(wyniki, cel_wygrana_a=args.cel_a, cel_wygrana_b=args.cel_b, stawka=args.stawka)

    if args.faza == "final":
        _sep("KROK 3b — Odświeżenie kursów LIVE (faza final)")
        indeks = _odswiez_kursy_live(indeks, dni=args.dni)

    _sep("KROK 4 — Weryfikacja kursow (anty-halucynacja)")
    dane = _weryfikuj_kupony(dane, indeks)

    # Krok 4b: Dodaj Kelly do kazdej nogi
    _dodaj_kelly(dane, current_bankroll)

    # Krok 4c: Decision Score post-Groq — teraz pewnosc_pct i ev_netto są rzeczywiste
    if args.faza:
        _ocen_zdarzenia_decision_score(dane, phase=args.faza)

    _wyswietl(dane, args.stawka, args.stawka_b)

    if args.waliduj:
        _waliduj_kupon_groq(dane, args.stawka, "kupon_a")

    # -- Faza: zapisz kupon do SQLite DB (pomijamy w dry-run) ─────────────────
    cid = None
    draft_legs = []
    draft_odds = 1.0
    if args.faza and not args.dry_run:
        kupon_a_db = dane.get("kupon_a", {})
        zdarzenia_db = kupon_a_db.get("zdarzenia", [])
        kurs_db = kupon_a_db.get("kurs_laczny", 1.0) or 1.0
        if zdarzenia_db:
            # Sprawdzenie decision_score PRZED zapisem
            avg_score = int(sum(z.get("decision_score", 0) for z in zdarzenia_db) / max(len(zdarzenia_db), 1))
            from footstats.core.decision_score import PROG_FINAL, PROG_DRAFT, PROG_DRAFT_FALLBACK
            if args.faza == "final":
                threshold = PROG_FINAL
            elif len(zdarzenia_db) < 3:
                threshold = PROG_DRAFT_FALLBACK  # mało kandydatów → łagodniejszy próg
            else:
                threshold = PROG_DRAFT

            if avg_score < threshold:
                console.print(
                    f"[red]❌ ODRZUCONO: decision_score {avg_score}/{threshold} poniżej progu "
                    f"({args.faza.upper()})[/red]"
                )
                console.print(f"[dim]Kupon nie został zapisany do bazy danych[/dim]")
            else:
                # LLM Scout filter (tylko faza final — oszczędność tokenów)
                if args.faza == "final":
                    from footstats.ai.analyzer import oceń_kupon, _SCOUT_VETO_THRESHOLD
                    scout_legs = [
                        {
                            "home": z.get("gospodarz", z.get("home", "?")),
                            "away": z.get("goscie", z.get("away", "?")),
                            "tip": z.get("typ", z.get("tip", "?")),
                            "odds": z.get("kurs", z.get("odds", 1.0)),
                            "prob": z.get("pewnosc_pct", z.get("pw_cal")),
                            "ev_netto": z.get("ev_netto"),
                        }
                        for z in zdarzenia_db
                    ]
                    scout_reasoning, scout_score = oceń_kupon(scout_legs)
                    console.print(
                        f"\n[bold]LLM Scout:[/bold] score={scout_score}/100\n"
                        f"[dim]{scout_reasoning[:400]}[/dim]\n"
                    )
                    if scout_score < _SCOUT_VETO_THRESHOLD:
                        console.print(
                            f"[red]❌ LLM SCOUT VETO: score {scout_score} < {_SCOUT_VETO_THRESHOLD} "
                            f"— kupon nie zapisany[/red]"
                        )
                        zdarzenia_db = []  # blokuj zapis poniżej

                if zdarzenia_db:
                    cid = _zapisz_kupon_do_db(
                        zdarzenia_db,
                        phase=args.faza,
                        groq_resp=dane.get("_raw", ""),
                        stake=args.stawka,
                        total_odds=kurs_db,
                    )
                    if cid:
                        console.print(f"[green]✅ Kupon zapisany do DB — ID: {cid} | faza: {args.faza}[/green]")
                        draft_legs = zdarzenia_db
                        draft_odds = kurs_db
    elif args.dry_run and args.faza:
        console.print("[yellow]DRY-RUN: pominięto zapis kuponu do DB[/yellow]")

    # Zapisz do TXT (pomijamy w dry-run)
    if not args.dry_run:
        sciezka_txt = _zapisz_txt(dane, args.stawka, args.stawka_b)
    else:
        console.print("[yellow]DRY-RUN: pominięto zapis TXT[/yellow]")
        sciezka_txt = None

    # Powiadomienie Windows (pomijamy w dry-run)
    kupony_info = []
    for lbl, kkey in [("A", "kupon_a"), ("B", "kupon_b"), ("C", "kupon_c"), ("D", "kupon_d")]:
        kp = dane.get(kkey, {})
        if kp.get("zdarzenia"):
            kupony_info.append(f"{lbl}: @{kp.get('kurs_laczny', 0):.2f} ({kp.get('szansa_wygranej_pct', '?')}%)")
    if not args.dry_run and sciezka_txt:
        notif_tekst = (
            " | ".join(kupony_info) + f"\n{sciezka_txt.name}"
        )
        _powiadomienie_windows("FootStats - gotowy kupon", notif_tekst)

    # Telegram (pomijamy w dry-run)
    if not args.dry_run:
        try:
            from footstats.utils.telegram_notify import (
                send_kupon, send_draft_kupon, telegram_dostepny,
            )
            if telegram_dostepny():
                if args.faza == "draft" and cid and draft_legs:
                    ok = send_draft_kupon(cid, draft_legs, draft_odds)
                else:
                    ok = send_kupon(dane, stawka_a=args.stawka, stawka_b=args.stawka_b)
                console.print(f"[dim]Telegram: {'wyslano' if ok else 'blad wysylki'}[/dim]")
        except (OSError, RuntimeError) as e:
            console.print(f"[dim]Telegram niedostepny: {e}[/dim]")
    else:
        console.print("[yellow]DRY-RUN: pominięto Telegram[/yellow]")

    # Cleanup old checkpoints (>7 days)
    cleanup_old_checkpoints(days=7)

    console.print()
    console.print("[bold green]Gotowe.[/bold green] Powodzenia!\n")




if __name__ == "__main__":
    main()
