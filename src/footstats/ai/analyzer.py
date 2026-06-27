"""
ai_analyzer.py – Analizator AI dla FootStats
Łączy predykcje FootStats (Poisson+ML) z kursami bukmacherów → pyta AI → daje typy

Moduły:
  analizuj_mecz_ai()        – analiza pojedynczego meczu
  ai_analiza_pewniaczki()   – analiza listy pewniaczków + propozycja kuponów
  ai_sprawdz_kupon()        – sprawdzenie kuponu podanego przez użytkownika
"""

import json
import logging
import os
from pathlib import Path

from langfuse import Langfuse

logger = logging.getLogger(__name__)

# Importy z pakietu footstats
from footstats.ai.client import zapytaj_ai
from footstats.data.context_scraper import get_match_context

# ── Langfuse Initialization (lazy — unika kosztu/błędów przy każdym imporcie) ──
_langfuse: Langfuse | None = None
_langfuse_init_done = False


def _get_langfuse() -> Langfuse | None:
    """Zwraca singleton Langfuse, inicjalizowany przy pierwszym użyciu."""
    global _langfuse, _langfuse_init_done
    if not _langfuse_init_done:
        _langfuse_init_done = True
        try:
            _langfuse = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
        except Exception as e:  # noqa: broad-except
            logger.warning("Langfuse init error: %s", e)
            _langfuse = None
    return _langfuse


from footstats.ai.prompts import (
    SYSTEM_TYPER as _SYSTEM_TYPER,
    build_mecz_prompt,
    build_pewniaczki_prompt,
    build_kupon_prompt,
    build_scout_prompt,
)
from footstats.ai.scoring import kurs_do_prob as _kurs_do_prob, value_bet as _value_bet
from footstats.ai.output import wyswietl_analiza_ai


def _get_kalibracja_blok() -> str:
    """Wczytuje kalibrację z treningu historycznego (trainer.py). Cicha na błędy."""
    try:
        from footstats.ai.trainer import get_kalibracja_inject
        return get_kalibracja_inject()
    except (ImportError, AttributeError, KeyError):
        return ""


def _get_liga_statystyki_blok() -> str:
    """
    Buduje blok LIGA_STATYSTYKI z danych historycznych (pattern_analyzer).
    Informuje Groq które ligi mają statystyczne uzasadnienie dla typów Over/BTTS.
    Preferuj mecze z tych lig gdy budujesz kupon.
    """
    try:
        from footstats.ai.trainer import load_lessons
        lessons  = load_lessons()
        rbl      = lessons.get("pattern_summary", {}).get("results_by_league", {})
        if not rbl:
            return ""
        linie = ["== LIGA_STATYSTYKI (dane historyczne, preferuj te ligi) =="]
        for liga, s in sorted(rbl.items()):
            over  = s.get("over25_pct")
            btts  = s.get("btts_pct")
            avg   = s.get("avg_goals")
            hw    = s.get("home_win")
            n     = s.get("n", 0)
            if n < 100:
                continue
            linia = f"{liga}: HW={hw}% Over2.5={over}% BTTS={btts}% Avg={avg}G (n={n})"
            # Oznacz ligi z wyraźnymi marchewkami
            if over and over > 58:
                linia += " <- MARCHEWKA Over2.5"
            if hw and hw > 47:
                linia += " <- silna przewaga domu"
            linie.append(linia)
        linie.append("Priorytet kuponu: mecze z lig oznaczonych MARCHEWKA > pozostale.")
        return "\n".join(linie)
    except (ImportError, KeyError, AttributeError, TypeError):
        return ""


def _kontynuuj_uciety_json(client, messages: list, partial: str, max_tokens: int = 700) -> str:
    """Wysyła ucięty JSON jako assistant turn i prosi o dokończenie."""
    cont_messages = messages + [
        {"role": "assistant", "content": partial},
        {"role": "user", "content": "Kontynuuj JSON od miejsca ucięcia. Zwróć TYLKO brakującą część (bez wstępu)."},
    ]
    try:
        resp2 = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=cont_messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        return partial + resp2.choices[0].message.content
    except (AttributeError, IndexError):
        return partial


def _zapytaj_typera(prompt: str, max_tokens: int = 900) -> str:
    """Groq z systemowym promptem wyspecjalizowanego typera + kalibracja + liga statystyki."""
    klucz = os.getenv("GROQ_API_KEY", "").strip()
    if not klucz:
        raise RuntimeError("Brak GROQ_API_KEY w .env")

    kal_blok   = _get_kalibracja_blok()
    liga_blok  = _get_liga_statystyki_blok()
    system     = _SYSTEM_TYPER
    if kal_blok:
        system += f"\n\n== KALIBRACJA Z DANYCH HISTORYCZNYCH ==\n{kal_blok}\n"
    if liga_blok:
        system += f"\n\n{liga_blok}\n"

    try:
        import groq as groq_lib
        client = groq_lib.Groq(api_key=klucz)

        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ]
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.25,
        )

        result = resp.choices[0].message.content
        if resp.choices[0].finish_reason == "length":
            result = _kontynuuj_uciety_json(client, messages, result)

        return result
    except Exception:  # noqa: broad-except
        return zapytaj_ai(prompt, max_tokens)


def _pobierz_podobne_mecze(home: str, away: str, n: int = 3) -> str:
    """Fetch N similar historical matches from RAG ai_feedback table.

    Searches for lessons containing either team name, returns formatted string
    with up to N similar matches for context.

    Args:
        home: Home team name
        away: Away team name
        n: Max number of similar matches to return (default 3)

    Returns:
        Formatted string with similar matches, empty string if none found or on error
    """
    try:
        from footstats.ai.post_match_analyzer import pobierz_ostatnie_wnioski
        # Fetch last 5 lessons from RAG database
        lessons = pobierz_ostatnie_wnioski(5)

        similar = []
        for lesson in lessons:
            # Match if either team appears in lesson
            if home.lower() in lesson.lower() or away.lower() in lesson.lower():
                similar.append(lesson)
                if len(similar) >= n:
                    break

        if not similar:
            return ""

        # Format for injection into prompt
        header = "\nPODOBNE MECZE Z HISTORII (nauka z przeszłości):\n"
        for i, lesson in enumerate(similar, 1):
            # Truncate lesson to 100 chars for readability
            header += f"{i}. {lesson[:100]}…\n"
        return header
    except (ImportError, KeyError, AttributeError, TypeError):
        # Silently fail: RAG is optional, don't break prediction if it fails
        return ""


# ── Pomocnicze ───────────────────────────────────────────────────────

# kurs_do_prob i value_bet → footstats.ai.scoring
# _analizuj_forme i _wyciagnij_json → footstats.ai.analyzer_helpers


# ── Główna analiza ───────────────────────────────────────────────────

def analizuj_mecz_ai(
    gospodarz: str,
    goscie: str,
    p_wygrana: float,      # % prawdopodobieństwo wygranej gospodarza (FootStats)
    p_remis: float,        # % prawdopodobieństwo remisu
    p_przegrana: float,    # % prawdopodobieństwo wygranej gości
    btts: float = 0,       # % BTTS TAK
    over25: float = 0,     # % Over 2.5 gola
    forma_g: str = "-",    # np. "WWDWL"
    forma_a: str = "-",
    h2h_opis: str = "-",
    pewnosc_modelu: int = 0,
    komentarz_footstats: str = "",
    kursy: dict | None = None,   # {"k1": 2.10, "kX": 3.40, "k2": 3.50} – opcjonalne
) -> dict:
    """
    Główna funkcja analizy AI.
    Zwraca słownik z typem, pewnością i uzasadnieniem.
    """

    # Oblicz value bet jeśli mamy kursy
    value_info = ""
    if kursy:
        k1 = kursy.get("k1") or kursy.get("1")
        kx = kursy.get("kX") or kursy.get("X")
        k2 = kursy.get("k2") or kursy.get("2")

        prob_buk_1 = _kurs_do_prob(k1)
        prob_buk_x = _kurs_do_prob(kx)
        prob_buk_2 = _kurs_do_prob(k2)

        value_1 = _value_bet(p_wygrana,    k1)
        value_x = _value_bet(p_remis,      kx)
        value_2 = _value_bet(p_przegrana,  k2)

        kursy_tekst = (
            f"\nKURSY BUKMACHERSKIE:\n"
            f"  Kurs 1={k1}  (bukmacher daje {prob_buk_1}% vs model {p_wygrana:.1f}%)"
            f"{'  ← POTENCJALNY VALUE BET!' if value_1 else ''}\n"
            f"  Kurs X={kx}  (bukmacher daje {prob_buk_x}% vs model {p_remis:.1f}%)"
            f"{'  ← POTENCJALNY VALUE BET!' if value_x else ''}\n"
            f"  Kurs 2={k2}  (bukmacher daje {prob_buk_2}% vs model {p_przegrana:.1f}%)"
            f"{'  ← POTENCJALNY VALUE BET!' if value_2 else ''}\n"
        )
        value_info = kursy_tekst
    else:
        k1 = kx = k2 = None
        value_1 = value_2 = value_x = False
        kursy_tekst = "\nKURSY BUKMACHERSKIE: brak danych\n"

    rag_context = _pobierz_podobne_mecze(gospodarz, goscie)
    
    prompt = build_mecz_prompt(
        gospodarz=gospodarz, goscie=goscie,
        p_wygrana=p_wygrana, p_remis=p_remis, p_przegrana=p_przegrana,
        btts=btts, over25=over25, pewnosc_modelu=pewnosc_modelu,
        forma_g=forma_g, forma_a=forma_a, h2h_opis=h2h_opis,
        rag_context=rag_context, value_info=value_info,
        komentarz_footstats=komentarz_footstats,
    )

    print(f"\n[AI] Analizuję: {gospodarz} vs {goscie}...")
    
    surowa_odpowiedz = None
    lf = _get_langfuse()
    if lf:
        with lf.start_as_current_observation(name=f"Analiza: {gospodarz} vs {goscie}", as_type="span"):
            with lf.start_as_current_observation(name="Groq Inference", as_type="generation", model="llama-3.1-8b-instant", input=prompt) as gen:
                surowa_odpowiedz = zapytaj_ai(prompt, max_tokens=500)
                gen.update(output=surowa_odpowiedz)
    else:
        surowa_odpowiedz = zapytaj_ai(prompt, max_tokens=500)
        
    wynik = _wyciagnij_json(surowa_odpowiedz)

    # Dodaj metadane
    wynik["gospodarz"]  = gospodarz
    wynik["goscie"]     = goscie
    wynik["p_wygrana"]  = p_wygrana
    wynik["p_remis"]    = p_remis
    wynik["p_przegrana"]= p_przegrana
    wynik["k1"]         = k1
    wynik["kX"]         = kx
    wynik["k2"]         = k2
    wynik["value_1"]    = value_1
    wynik["value_x"]    = value_x
    wynik["value_2"]    = value_2

    return wynik


# wyswietl_analiza_ai → footstats.ai.output



# ── Tryb interaktywny (samodzielny) ──────────────────────────────────

def _tryb_interaktywny():
    print("\n" + "="*55)
    print("  FootStats AI Analyzer – tryb interaktywny")
    print("="*55)
    print("\nWprowadź dane meczu ręcznie:\n")

    g  = input("Gospodarz: ").strip()
    a  = input("Gość:      ").strip()
    pw = float(input("% wygranej gospodarza (np. 52.3): ") or 33)
    pr = float(input("% remisu (np. 25.0): ") or 33)
    pp = float(input("% wygranej gości (np. 22.7): ") or 34)

    print("\nKursy bukmacherskie (Enter = pomiń):")
    k1_txt = input("  Kurs na 1 (np. 1.85): ").strip()
    kx_txt = input("  Kurs na X (np. 3.40): ").strip()
    k2_txt = input("  Kurs na 2 (np. 4.20): ").strip()

    kursy = None
    if k1_txt and kx_txt and k2_txt:
        try:
            kursy = {
                "k1": float(k1_txt),
                "kX": float(kx_txt),
                "k2": float(k2_txt),
            }
        except ValueError:
            print("Niepoprawne kursy – pominięto.")

    wynik = analizuj_mecz_ai(
        gospodarz   = g,
        goscie      = a,
        p_wygrana   = pw,
        p_remis     = pr,
        p_przegrana = pp,
        kursy       = kursy,
    )
    wyswietl_analiza_ai(wynik)

    zapis = input("\nZapisać do pliku? (t/n): ").strip().lower()
    if zapis == "t":
        import re as _re
        _safe = lambda s: _re.sub(r'[^a-zA-Z0-9_\-]', '_', s)[:40]
        plik = Path(f"ai_analiza_{_safe(g)}_vs_{_safe(a)}.json")
        plik.write_text(json.dumps(wynik, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Zapisano: {plik.resolve()}")


# ════════════════════════════════════════════════════════════════════
#  AI + PEWNIACZKI – analiza listy typów i builder kuponów
# ════════════════════════════════════════════════════════════════════

def _buduj_opis_meczu(w: dict) -> str:
    """
    Buduje bogaty kontekst meczu dla Groq.

    Obsługuje dwa formaty wejściowe:
      - quick_picks: flat pw/pr/pp/bt/o25 + odds + scout
      - weekly_picks: nested pred (lambda, czynniki, pewnosc) + bzz_info
    """
    g      = w.get("gospodarz", "?")
    a      = w.get("goscie", "?")
    liga   = w.get("liga", "?")
    data   = w.get("data", "")
    godz   = w.get("godzina", "–")
    metoda = w.get("metoda", "ML")
    pred   = w.get("pred") or {}

    # Dane probabilistyczne — Poisson trzyma je w pred, ML na poziomie głównym
    if metoda == "POISSON" and pred:
        pw  = pred.get("p_wygrana",   0)
        pr  = pred.get("p_remis",     0)
        pp  = pred.get("p_przegrana", 0)
        bt  = pred.get("btts",        0)
        o25 = pred.get("over25",      0)
        lambda_g = pred.get("lambda_g")
        lambda_a = pred.get("lambda_a")
        pewnosc  = pred.get("pewnosc", 0)
    else:
        pw  = w.get("pw",  0) or pred.get("p_wygrana",   0)
        pr  = w.get("pr",  0) or pred.get("p_remis",     0)
        pp  = w.get("pp",  0) or pred.get("p_przegrana", 0)
        bt  = w.get("bt",  0) or pred.get("btts",        0)
        o25 = w.get("o25", 0) or pred.get("over25",      0)
        lambda_g = None
        lambda_a = None
        pewnosc  = pred.get("pewnosc", 55)

    linie = [f"• {g} vs {a} [{liga}] {data} {godz}  [metoda:{metoda}]"]

    # Lambdy Poissona + dominacja atakiem
    if lambda_g and lambda_a and lambda_a > 0:
        ratio = round(lambda_g / lambda_a, 2)
        if ratio >= 1.5:
            dom = f" → {g[:10]} dominuje ({ratio}x)"
        elif ratio <= 0.67:
            dom = f" → {a[:10]} dominuje ({round(1/ratio, 2)}x)"
        else:
            dom = " → wyrównane"
        linie.append(f"  POISSON: λg={lambda_g} λa={lambda_a}{dom}")

    # Prawdopodobieństwa ML
    linie.append(
        f"  ML: 1={pw:.0f}% X={pr:.0f}% 2={pp:.0f}%"
        f" | BTTS={bt:.0f}% | Over2.5={o25:.0f}%"
    )

    # Cross-walidacja Poisson vs Bzzoiro (tylko tygodniowe)
    bzz_info = w.get("bzz_info") or {}
    cross    = bzz_info.get("cross") or {}
    if cross and metoda == "POISSON":
        ml_1 = cross.get("ml_1", 0)
        if ml_1:
            diff = round(pw - ml_1, 1)
            kierunek = "Poisson wyżej" if diff > 0 else "ML wyżej"
            alert = " ⚠️ROZBIEŻNOŚĆ" if cross.get("alert") else ""
            linie.append(
                f"  PORÓWNANIE: Poisson={pw:.0f}% vs Bzz={ml_1:.0f}%"
                f" ({diff:+.0f}% {kierunek}){alert}"
            )

    # Czynniki analityczne — tylko predykcje Poissona
    if metoda == "POISSON" and pred:
        h2h_g      = pred.get("h2h_g",      {}) or {}
        heur_g     = pred.get("heur_g",     {}) or {}
        heur_a     = pred.get("heur_a",     {}) or {}
        fortress_g = pred.get("fortress_g", {}) or {}
        imp_g      = pred.get("imp_g",      {}) or {}
        imp_a      = pred.get("imp_a",      {}) or {}

        czynniki = []
        n_h2h = h2h_g.get("n_h2h", 0)
        if h2h_g.get("patent"):
            czynniki.append(f"PATENT({g[:8]} {n_h2h}/{n_h2h} H2H)")
        if h2h_g.get("zemsta"):
            czynniki.append(f"ZEMSTA({g[:8]})")
        if fortress_g.get("fortress"):
            czynniki.append(f"TWIERDZA({g[:8]} {fortress_g.get('seria', 5)}m dom)")
        if heur_g.get("rotacja"):
            czynniki.append(f"ROTACJA({g[:8]})")
        if heur_g.get("zmeczenie"):
            czynniki.append(f"ZMECZENIE({g[:8]})")
        if heur_a.get("rotacja"):
            czynniki.append(f"ROTACJA({a[:8]})")
        if heur_a.get("zmeczenie"):
            czynniki.append(f"ZMECZENIE({a[:8]})")
        if czynniki:
            linie.append(f"  CZYNNIKI: {' | '.join(czynniki)}")

        # Importance Index (pomijamy NORMAL — to szum)
        sg = imp_g.get("status", "NORMAL")
        sa = imp_a.get("status", "NORMAL")
        if sg != "NORMAL" or sa != "NORMAL":
            def _skroc_kom(kom: str) -> str:
                # Bierz część po " – " jeśli istnieje, max 45 znaków
                return (kom.split("–")[-1].strip() if "–" in kom else kom)[:45]
            opis_g = f"{g[:8]}={sg}"
            if sg != "NORMAL":
                opis_g += f"({_skroc_kom(imp_g.get('komentarz', ''))})"
            opis_a = f"{a[:8]}={sa}"
            if sa != "NORMAL":
                opis_a += f"({_skroc_kom(imp_a.get('komentarz', ''))})"
            linie.append(f"  WAŻNOŚĆ: {opis_g} | {opis_a}")

        # Forma — pkt/mecz jako sygnał trendu
        fg = pred.get("forma_g", 0)
        fa = pred.get("forma_a", 0)
        if fg or fa:
            linie.append(f"  FORMA(pkt/m): {g[:8]}={fg:.2f}  {a[:8]}={fa:.2f}")

        linie.append(f"  PEWNOŚĆ: {pewnosc}% (n_h2h={n_h2h})")

    # Forma z SofaScore — W/D/L + gole + kontuzje (wzbogacona przez _wzbogac_forme)
    sofa_g = w.get("sofa_forma_g")
    sofa_a = w.get("sofa_forma_a")
    if sofa_g or sofa_a:
        linie.append(
            f"  FORMA_SOFA: {g[:8]}={sofa_g or '?'}  {a[:8]}={sofa_a or '?'}"
        )
    
    # Rich Context: xG, Table, Absences
    ctx = w.get("match_context") or {}
    if ctx:
        xg_h = ctx.get("home_xg_last3", [])
        xg_a = ctx.get("away_xg_last3", [])
        if xg_h or xg_a:
            linie.append(f"  xG_LAST3: {g[:8]}={xg_h}  {a[:8]}={xg_a}")
        
        pos_h = ctx.get("home_table_pos")
        pos_a = ctx.get("away_table_pos")
        if pos_h or pos_a:
            linie.append(f"  TABELA: {g[:8]}=#{pos_h or '?'}  {a[:8]}=#{pos_a or '?'}")
            
        abs_h = ctx.get("home_absences", [])
        abs_a = ctx.get("away_absences", [])
        if abs_h or abs_a:
            linie.append(f"  KONTEKST_ABSENCJE: {g[:8]}:{abs_h} | {a[:8]}:{abs_a}")

    inj_g = w.get("sofa_kontuzje_g")
    inj_a = w.get("sofa_kontuzje_a")
    if inj_g or inj_a:
        czesci = []
        if inj_g:
            czesci.append(f"{g[:8]}: {inj_g}")
        if inj_a:
            czesci.append(f"{a[:8]}: {inj_a}")
        linie.append(f"  KONTUZJE: {' | '.join(czesci)}")

    # Absencje Flashscore (Fallback/Dodatkowe)
    fs_abs_g = w.get("fs_absencje_g")
    fs_abs_a = w.get("fs_absencje_a")
    if fs_abs_g or fs_abs_a:
        czesci_fs = []
        if fs_abs_g: czesci_fs.append(f"{g[:8]}: {fs_abs_g}")
        if fs_abs_a: czesci_fs.append(f"{a[:8]}: {fs_abs_a}")
        linie.append(f"  ABSENCJE_FS: {' | '.join(czesci_fs)}")

    # Sędzia i dyscyplina
    ref_name = w.get("referee_name")
    stadium = w.get("stadium")
    if ref_name or stadium:
        info_s = []
        if ref_name:
            avg_y = w.get("referee_avg_y", 0)
            sig   = w.get("referee_signal", "NEUTRALNY")
            info_s.append(f"SĘDZIA: {ref_name} (avg: {avg_y}) [{sig}]")
        if stadium:
            info_s.append(f"STADION: {stadium}")
        linie.append(f"  SĘDZIA/MIEJSCE: {' | '.join(info_s)}")

    # Kursy bukmacherskie
    odds = (
        w.get("odds")
        or (bzz_info.get("odds") if bzz_info else None)
        or pred.get("odds")
        or {}
    )
    if isinstance(odds, dict):
        k1 = odds.get("home"); kx = odds.get("draw"); k2 = odds.get("away")
        if k1 or kx or k2:
            linie.append(f"  KURSY: 1={k1 or '–'} X={kx or '–'} 2={k2 or '–'}")
            # EV brutto (bez podatku) — AI uwzględni 12% we własnej analizie
            ev_parts = []
            for label, p_val, kurs_raw in [
                ("1",    pw  / 100, k1),
                ("X",    pr  / 100, kx),
                ("2",    pp  / 100, k2),
                ("BTTS", bt  / 100, odds.get("btts")),
                ("O2.5", o25 / 100, odds.get("over_2_5")),
            ]:
                try:
                    k = float(str(kurs_raw).replace(",", "."))
                    ev = p_val * k - 1.0
                    if ev > 0.0:
                        ev_parts.append(f"{label}={ev * 100:+.0f}%")
                except (ValueError, TypeError):
                    pass
            if ev_parts:
                linie.append(f"  EV(brutto): {' '.join(ev_parts)}")

    # Bet Builder Sugestie ze skorelowanej macierzy matematycznej
    bb = w.get("bet_builder")
    if bb and isinstance(bb, list):
        b_str = ", ".join(bb)
        linie.append(f"  [bet_builder_sugestie]: {b_str}")

    # BetBuilder z kurs_fair (1/p_Poisson) — preferowany format dla AI
    bb_k = w.get("bet_builder_kombinacje")
    if bb_k and isinstance(bb_k, list):
        linie.append(f"  [bb_z_kursem]: {', '.join(bb_k[:6])}")

    # Scout Bot EV — format quick_picks
    scout = w.get("scout") or {}
    if scout:
        wartosciowe = sorted(
            [oc for oc in scout.get("oceny", []) if oc.get("ev") and oc["ev"] > 0.03],
            key=lambda x: -x["ev"],
        )
        if wartosciowe:
            ev_str = " | ".join(
                f"{oc['typ'][:14]}={oc['ev'] * 100:+.0f}%"
                for oc in wartosciowe[:3]
            )
            linie.append(f"  SCOUT_EV: {ev_str}")

    # Etap 7: RAG — historyczne wzorce dla tych czynników
    try:
        from footstats.ai.rag import pobierz_rag_kontekst
        rag = pobierz_rag_kontekst(w)
        if rag:
            linie.append(f"  HISTORIA: {rag}")
    except (ImportError, KeyError, AttributeError):
        pass

    return "\n".join(linie)



from footstats.ai.analyzer_helpers import (
    _wzbogac_forme, _sygnaly_summary, _auto_zapisz_backtest, _buduj_cel_kuponow,
    _wyciagnij_json, _deduplikuj_kupony, _wymusz_40pct, _nadpisz_pewnosc_modelem,
)
# Re-eksport wsteczny (importowany z tego modułu przez testy/inne moduły):
from footstats.ai.analyzer_helpers import _analizuj_forme  # noqa: F401

def ai_analiza_pewniaczki(
    wyniki: list,
    pobierz_forme: bool = True,
    cel_wygrana_a: float | None = None,
    cel_wygrana_b: float | None = None,
    stawka: float = 10.0,
) -> dict:
    """
    Groq analizuje listę pewniaczków (quick_picks lub weekly_picks).

    Wejście: lista z szybkie_pewniaczki_2dni() lub pewniaczki_tygodnia()
    pobierz_forme: czy próbować pobrać formę z SofaScore dla TOP 5 meczów
    cel_wygrana_a/b: opcjonalny cel wygranej netto PLN (np. 50, 100) — zmienia instrukcję kursu
    stawka: stawka PLN, używana do obliczenia celu kursu
    Wyjście: słownik JSON z kluczami top3, kupon_a, kupon_b, ostrzezenia.
      Jeśli parsowanie JSON się nie powiodło, zawiera klucz _raw z surowym tekstem.
    """
    if not wyniki:
        return {"_raw": "Brak pewniaczków do analizy."}

    # Etap 4: Wzbogać TOP 10 meczów o formę SofaScore i stats context
    if pobierz_forme:
        _wzbogac_forme(wyniki, top_n=10)
        # Dodatkowy kontekst xG/Table dla TOP5
        for w in wyniki[:5]:
            try:
                w["match_context"] = get_match_context(w.get("gospodarz",""), w.get("goscie",""), w.get("liga",""))
            except (OSError, RuntimeError):
                pass

    # Etap 3: Dynamiczne podsumowanie sygnałów
    sygnaly = _sygnaly_summary(wyniki)

    # Etap 6: Kalibracja historyczna z backtest DB
    kalibracja_str = ""
    try:
        from footstats.core.backtest import pobierz_kalibracje_backtest
        k = pobierz_kalibracje_backtest()
        if k:
            kalibracja_str = f"KALIBRACJA HISTORYCZNA (backtest ~90 dni):\n{k}\n"
    except (ImportError, OSError, RuntimeError):
        pass

    feedback_str = ""
    try:
        from footstats.ai.post_match_analyzer import pobierz_ostatnie_wnioski
        from footstats.ai.rag import retrieve_relevant_lessons

        # Build query context from coupon: leagues, teams, market types
        leagues = list(set(w.get("liga", "") for w in wyniki[:10] if w.get("liga")))
        markets = [w.get("typ_kuponu", "") for w in wyniki[:5] if w.get("typ_kuponu")]
        query_context = f"Liga: {', '.join(leagues[:3])} | Markety: {', '.join(set(markets))}"

        # Try semantic retrieval first; fall back to chronological
        lessons_data = retrieve_relevant_lessons(query_context, k=3, min_score=0.3) if query_context.strip() else []
        wnioski = [lesson["reason_for_failure"] for lesson in lessons_data] if lessons_data else pobierz_ostatnie_wnioski(3)

        if wnioski:
            feedback_str = (
                "WNIOSKI Z OSTATNICH PORAŻEK (Pętla Feedbacku — ucz się błędów):\n"
                + "\n".join(f"  • {w}" for w in wnioski)
                + "\n"
            )
    except (ImportError, OSError, RuntimeError):
        pass

    mecze_opisy = [_buduj_opis_meczu(w) for w in wyniki[:5]]

    prompt = build_pewniaczki_prompt(
        n_mecze=len(wyniki[:5]),
        sygnaly=sygnaly,
        kalibracja_str=kalibracja_str,
        feedback_str=feedback_str,
        mecze_opisy_text=chr(10).join(mecze_opisy),
        cel_kuponow_text=_buduj_cel_kuponow(cel_wygrana_a, cel_wygrana_b, stawka),
    )

    # Inject RAG similar matches for historical context (learning from past)
    if wyniki:
        home = wyniki[0].get("gospodarz", "")
        away = wyniki[0].get("goscie", "")
        rag_similar = _pobierz_podobne_mecze(home, away, n=3)
        prompt = f"{prompt}{rag_similar}"

    # Langfuse observability is handled globally
    tekst = _zapytaj_typera(prompt, max_tokens=1500)
    dane = _wyciagnij_json(tekst)
    if "top3" not in dane:
        dane["_raw"] = tekst
    else:
        # Cel B: pewnosc_pct nóg = prob modelu (fallback Groq) PRZED bramkami,
        # żeby dedup/40%/kotwice działały na modelu, nie na self-reported Groq.
        _nadpisz_pewnosc_modelem(dane, wyniki)
        # Singiel — deduplikacja nieistotna, ale wywołaj dla spójności
        _deduplikuj_kupony(dane, min_wspolna_pewnosc=75)
        # Walidacja minimalnej szansy: niski próg gdy podany cel kursu
        if cel_wygrana_a is not None or cel_wygrana_b is not None:
            _wymusz_40pct(dane, min_szansa=5.0)

        else:
            _wymusz_40pct(dane, min_szansa=40.0)
        _auto_zapisz_backtest(dane, wyniki)

    return dane


# _deduplikuj_kupony i _wymusz_40pct → footstats.ai.analyzer_helpers


def ai_sprawdz_kupon(picks_text: str, stawka: float = 5.0, wzorzec_ml: list = None) -> str:
    """
    Groq ocenia kupon bukmacherski podany przez użytkownika.

    picks_text – tekst z typami np:
        "PSG 1X @1.31, Bayern wygrana @1.55, Leverkusen 1 @1.88"
    stawka     – stawka na kupon (PLN)
    wzorzec_ml – opcjonalnie lista pewniaczków z Bzzoiro (dla cross-walidacji)

    Zwraca: tekstowa ocena kuponu z EV, ryzykami i rekomendacją.
    """
    # Kontekst ML jeśli dostępny
    ml_kontekst = ""
    if wzorzec_ml:
        mecze_ml = []
        for w in wzorzec_ml[:15]:
            g, a = w.get("gospodarz", ""), w.get("goscie", "")
            pw, pr, pp = w.get("pw", 0), w.get("pr", 0), w.get("pp", 0)
            bt, o25 = w.get("bt", 0), w.get("o25", 0)
            odds = w.get("odds") or {}
            mecze_ml.append(
                f"  {g} vs {a}: 1={pw:.0f}% X={pr:.0f}% 2={pp:.0f}% "
                f"BTTS={bt:.0f}% O2.5={o25:.0f}% | "
                f"kurs: 1={odds.get('home','–')} X={odds.get('draw','–')} 2={odds.get('away','–')}"
            )
        ml_kontekst = "\nDANE ML (Bzzoiro CatBoost) dla zbliżonych meczów:\n" + "\n".join(mecze_ml)

    prompt = build_kupon_prompt(stawka=stawka, picks_text=picks_text, ml_kontekst=ml_kontekst)

    return _zapytaj_typera(prompt, max_tokens=800)


_SCOUT_VETO_THRESHOLD = 50  # score < 50 → veto kuponu


def oceń_kupon(legs: list[dict], kontekst: str = "") -> tuple[str, int]:
    """
    LLM Scout filter — ocenia listę nóg kuponu i zwraca (reasoning, score 0-100).
    Score < _SCOUT_VETO_THRESHOLD → kupon powinien być odrzucony.

    legs: lista dict z kluczami home, away, tip, odds (i opcjonalnie prob, ev_netto)
    kontekst: dodatkowy tekst (np. forma drużyn, kontuzje)
    """
    if not legs:
        return ("Brak nóg kuponu.", 0)

    legs_text = "\n".join(
        f"  {i+1}. {lg.get('home','?')} vs {lg.get('away','?')} | "
        f"Typ: {lg.get('tip','?')} @ {lg.get('odds', lg.get('kurs','?'))} | "
        f"P(win)={lg.get('prob', lg.get('pw_cal', '?'))} "
        f"EV={lg.get('ev_netto','?')}"
        for i, lg in enumerate(legs)
    )

    prompt = build_scout_prompt(legs_text=legs_text, kontekst=kontekst)

    try:
        reasoning = _zapytaj_typera(prompt, max_tokens=600)
    except Exception:  # noqa: broad-except — LLM fallback, nie blokuj pipeline
        return ("LLM niedostępny — pominięto scout filter.", _SCOUT_VETO_THRESHOLD)

    score = _SCOUT_VETO_THRESHOLD
    for line in reversed(reasoning.splitlines()):
        line = line.strip()
        if line.upper().startswith("SCORE:"):
            try:
                score = max(0, min(100, int(line.split(":", 1)[1].strip())))
            except ValueError:
                pass
            break

    return (reasoning, score)


def ai_groq_dostepny() -> bool:
    """Sprawdza czy Groq API jest dostępne (klucz w .env)."""
    return bool(os.getenv("GROQ_API_KEY", "").strip())


if __name__ == "__main__":
    _tryb_interaktywny()
