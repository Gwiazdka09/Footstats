"""
FootStats Daily Agent — Decision Score
======================================
Scoring nóg/kandydatów przez `core.decision_score` (próg draft/final).
Wydzielone z `daily_agent.py` (dekompozycja god-modułu). Behavior-preserving —
`daily_agent` re-importuje te symbole, więc patch-targety i ścieżki działają.
"""

from footstats.daily_agent_output import console, _sep


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
