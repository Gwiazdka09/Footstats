"""
analyzer_helpers.py – Pomocnicze funkcje wydzielone z analyzer.py.
Etapy: wzbogacanie formy, sygnały, zapis backtest, cel kuponów,
analiza formy, parsowanie JSON, walidacja kuponów (czyste funkcje).
"""

import json
import logging
import math
import re
from datetime import datetime

logger = logging.getLogger(__name__)


# Mapowanie typ tipa → klucz prawdopodobieństwa w pred Poissona (wartości w %).
_TYP_DO_PROB_KEY: dict[str, str] = {
    "1": "p_wygrana", "1x": "p_wygrana",
    "x": "p_remis",
    "2": "p_przegrana", "x2": "p_przegrana",
    "btts": "btts",
}


def pewnosc_z_modelu(typ: str, pred: dict, fallback_pct: float | None = None) -> int:
    """
    FAZA 17.1/17.6: jedyne źródło pewności zapisywanej do predictions.
    Pewność = prawdopodobieństwo modelu (%) dla danego typu, NIE z EV.
    Deterministyczne dla (typ, pred) — ten sam mecz+tip daje tę samą pewność
    niezależnie od kupon_type (eliminuje niestabilność z 17.6).
    Fallback: LLM pewnosc_pct; ostatecznie 50.
    """
    p_mod = prob_modelu(typ, pred)
    if p_mod is not None:
        return int(round(max(1, min(99, p_mod))))
    return int(fallback_pct or 50)


def prob_modelu(typ: str, pred: dict) -> float | None:
    """Prawdopodobieństwo modelu (%) dla typu tipa. None jeśli brak danych."""
    if not pred:
        return None
    t = typ.strip().lower()
    key = _TYP_DO_PROB_KEY.get(t)
    if key:
        return pred.get(key)
    if t.startswith("over"):
        return pred.get("over25")
    if t.startswith("under"):
        return pred.get("under25")
    return None


def _wzbogac_forme(wyniki: list, top_n: int = 12) -> None:
    """
    Etap 4: Próbuje wzbogacić TOP N meczów o formę z SofaScore (Playwright).
    Modyfikuje wyniki in-place, dodając klucze sofa_forma_g/a i sofa_kontuzje_g/a.
    Bezpieczna — gdy Playwright niedostępny lub SofaScore błąd, po prostu pomija.
    """
    try:
        from footstats.scrapers.form_scraper import pobierz_forme_meczu, PLAYWRIGHT_OK
        if not PLAYWRIGHT_OK:
            return
    except ImportError:
        return

    posortowane = sorted(
        range(min(len(wyniki), 20)),
        key=lambda i: (
            0 if wyniki[i].get("metoda") == "POISSON" else 1,
            -(wyniki[i].get("pred", {}) or {}).get("pewnosc", 0),
            -(max((v for _, v in wyniki[i].get("typy", [(None, 0)])), default=0)),
        ),
    )[:top_n]

    for idx in posortowane:
        w = wyniki[idx]
        g = w.get("gospodarz", "")
        a = w.get("goscie", "")
        if not g or not a:
            continue
        try:
            forma = pobierz_forme_meczu(g, a)
            fh = forma.get("home", {})
            fa_d = forma.get("away", {})

            if fh.get("form"):
                gs = fh.get("goals_scored", 0)
                gc = fh.get("goals_conceded", 0)
                wyniki[idx]["sofa_forma_g"] = f"{''.join(fh['form'])}({gs}:{gc})"
            if fa_d.get("form"):
                gs = fa_d.get("goals_scored", 0)
                gc = fa_d.get("goals_conceded", 0)
                wyniki[idx]["sofa_forma_a"] = f"{''.join(fa_d['form'])}({gs}:{gc})"

            inj_g = [i["name"] for i in fh.get("injuries", [])[:3]]
            inj_a = [i["name"] for i in fa_d.get("injuries", [])[:3]]
            if inj_g:
                wyniki[idx]["sofa_kontuzje_g"] = ", ".join(inj_g)
            if inj_a:
                wyniki[idx]["sofa_kontuzje_a"] = ", ".join(inj_a)
        except (KeyError, TypeError, ValueError, OSError):
            pass


def _sygnaly_summary(wyniki: list) -> str:
    """
    Etap 3: Buduje dynamiczne podsumowanie sygnałów dla Groq.
    Zwraca kilka linii kontekstu — co jest mocne, czego unikać w AKO.
    """
    n_pois = sum(1 for w in wyniki if w.get("metoda") == "POISSON")
    mocne: list[str] = []
    uwagi: list[str] = []

    _STRONG = {"HIGH_STAKES_TOP", "FINAL_TOP", "HIGH_STAKES_BOTTOM", "FINAL_RELEGATION"}

    for w in wyniki[:20]:
        g = w.get("gospodarz", "?")[:8]
        a = w.get("goscie", "?")[:8]
        pred = w.get("pred") or {}

        if w.get("metoda") != "POISSON":
            continue

        h2h_g      = pred.get("h2h_g",      {}) or {}
        heur_g     = pred.get("heur_g",     {}) or {}
        heur_a     = pred.get("heur_a",     {}) or {}
        fortress_g = pred.get("fortress_g", {}) or {}
        imp_g      = pred.get("imp_g",      {}) or {}
        cross      = (w.get("bzz_info") or {}).get("cross") or {}

        plus, minus = [], []
        if h2h_g.get("patent"):          plus.append("PATENT")
        if fortress_g.get("fortress"):   plus.append("TWIERDZA")
        if imp_g.get("status") in _STRONG: plus.append(imp_g["status"].replace("HIGH_STAKES_", ""))

        if heur_g.get("rotacja") or heur_a.get("rotacja"): minus.append("ROTACJA")
        if heur_g.get("zmeczenie") or heur_a.get("zmeczenie"): minus.append("ZMĘCZENIE")
        if cross.get("alert"): minus.append("ROZBIEŻNOŚĆ")

        label = f"{g}-{a}"
        if len(plus) >= 2:
            mocne.append(f"{label}({'+'.join(plus)})")
        if minus:
            uwagi.append(f"{label}({','.join(minus)})")

    linie = [f"PODZIAŁ: {n_pois} Poisson / {len(wyniki) - n_pois} ML"]
    if mocne:
        linie.append(f"MOCNE SYGNAŁY: {' | '.join(mocne[:5])}")
    if uwagi:
        linie.append(f"UNIKAJ W AKO:  {' | '.join(uwagi[:5])}")

    sofa_n = sum(1 for w in wyniki if w.get("sofa_forma_g"))
    if sofa_n:
        linie.append(f"FORMA SOFA: pobrana dla {sofa_n} meczów (patrz FORMA_SOFA i KONTUZJE w danych)")

    return "\n".join(linie)


def koryguj_tip_wg_modelu(tip: str, pw, pr, pp, prog_min: float = 15.0) -> "tuple[str, bool]":
    """D3 / Cel B bug 2 — guard selekcji Groq.

    Groq systematycznie wybierał wyjazdy/remisy (tip 2/X) przeciw faworytom-gospodarzom
    → 12.5% trafność tip=2. Gdy Groq wybrał wynik 1X2 którego model daje prob < prog_min
    (skrajny rozjazd) → override na argmax modelu (najbardziej prawdopodobny 1X2).
    KONSERWATYWNY: tylko 1X2, tylko skrajne (<15%). Brak prob modelu → nie rusza.
    Zwraca (tip, czy_override). Walidacja na danych po ~20 świeżych settled (prob teraz zapisywane).
    """
    if tip not in ("1", "X", "2"):
        return tip, False
    prob = {"1": pw, "X": pr, "2": pp}
    if any(prob[k] is None for k in prob):
        return tip, False  # brak prob modelu (np. mecz spoza coverage) → nie ruszaj
    if prob[tip] >= prog_min:
        return tip, False  # akceptowalna zgodność z modelem
    argmax = max(("1", "X", "2"), key=lambda k: prob[k])
    if argmax == tip:
        return tip, False
    logger.info("D3 guard: Groq tip=%s (prob modelu %.1f%% < %.0f) → override argmax=%s",
                tip, prob[tip], prog_min, argmax)
    return argmax, True


def _auto_zapisz_backtest(dane: dict, wyniki: list) -> None:
    """
    Zapisuje typy AI (top3 + kupony) do bazy backtest po każdej analizie.
    Bezpieczna — wyjątek nie blokuje głównej ścieżki.
    """
    try:
        from footstats.core.backtest import save_prediction
    except ImportError:
        return

    today = datetime.now().strftime("%Y-%m-%d")

    def _znajdz_mecz(mecz_str: str) -> dict:
        ms = mecz_str.lower()
        for w in wyniki:
            g = w.get("gospodarz", "").lower()
            a = w.get("goscie", "").lower()
            if g and g in ms:
                return w
            if a and a in ms:
                return w
        return {}

    _TYP_NORM = {"Over": "Over 2.5", "Under": "Under 2.5",
                 "OVER": "Over 2.5", "UNDER": "Under 2.5"}

    def _zapisz(typy: list, kupon_type: str) -> None:
        for t in typy:
            mecz_str = t.get("mecz", "")
            w = _znajdz_mecz(mecz_str)
            czesci = mecz_str.split(" vs ", 1)
            home = w.get("gospodarz") or (czesci[0].strip() if czesci else mecz_str)
            away = w.get("goscie") or (czesci[1].strip() if len(czesci) > 1 else "")
            tip = _TYP_NORM.get(t.get("typ", ""), t.get("typ", ""))
            # FAZA 17.1/17.6: pewność z prob modelu (deterministyczna per mecz+tip).
            conf = pewnosc_z_modelu(t.get("typ", ""), w.get("pred") or {}, t.get("pewnosc_pct"))
            try:
                from footstats.ai.rag import wyciagnij_faktory
                faktory = wyciagnij_faktory(w.get("pred") or {})
            except (ImportError, KeyError, AttributeError):
                faktory = []
            # D3: prob modelu 1X2 (do zapisu + guard selekcji). quick_picks daje pw/pr/pp top-level.
            pw = w.get("pw"); pr = w.get("pr"); pp = w.get("pp")
            tip, _override = koryguj_tip_wg_modelu(tip, pw, pr, pp)
            try:
                save_prediction(
                    match_date=w.get("data", today),
                    team_home=home,
                    team_away=away,
                    ai_tip=tip,
                    ai_confidence=conf,
                    league=w.get("liga", ""),
                    odds=t.get("kurs"),
                    kupon_type=kupon_type,
                    prompt_version="v5_json",
                    factors=faktory,
                    prob_home=pw, prob_draw=pr, prob_away=pp,
                )
            except Exception:  # noqa: broad-except — optional telemetry, never block pipeline
                pass

    if dane.get("top3"):
        _zapisz(dane["top3"], "top3")
    for kkey in ("kupon_a", "kupon_b", "kupon_c", "kupon_d"):
        if (dane.get(kkey) or {}).get("zdarzenia"):
            _zapisz(dane[kkey]["zdarzenia"], kkey)


def _buduj_cel_kuponow(cel_a: float | None, cel_b: float | None, stawka: float) -> str:
    """Generuje sekcję FILOZOFIA KUPONÓW — standardową lub z celem wygranej."""
    if cel_a is None and cel_b is None:
        return """Oba kupony muszą mieć szansa_wygranej_pct >= 40%.
Liczba nóg: 2-6, ale TYLKO tyle ile pozwala utrzymać >=40% szansy.
Matematyka: szansa_kuponu = p1 × p2 × ... × pN (iloczyn pewności każdej nogi).

Progi pewności minimalnej per noga (żeby utrzymać 40% przy N nogach):
  2 nogi: każda noga >= 63%
  3 nogi: każda noga >= 74%
  4 nogi: każda noga >= 80%
  5 nogi: każda noga >= 83%
  6 nogi: każda noga >= 86%

ZASADA: dodaj nogę TYLKO jeśli jej pewność jest wystarczająco wysoka żeby produkt >= 40%.
Zacznij od najsilniejszych typów i dodawaj kolejne tylko gdy spełniają próg.
Jeśli nie ma 6 typów z >=86% — zrób mniej nóg.
KUPON A: zbuduj z 2-6 nóg z max pewnością, kurs łączny dobierz naturalnie.
KUPON B: alternatywna kombinacja, inne mecze lub inne rynki, też >=40% szansy."""

    def _opis_kuponu(label: str, cel: float | None, default_cel: float, default_kurs: str, min_szansa: int) -> str:
        if cel is None:
            return f"{label}: kurs ~{default_kurs}, szansa min {min_szansa}%."
        kurs_docelowy = round(cel / (stawka * 0.88), 1)
        return (
            f"{label}: CEL wygrana netto ~{cel:.0f} PLN od stawki {stawka:.0f} PLN.\n"
            f"  Wymagany kurs_laczny ~{kurs_docelowy:.1f}x.\n"
            f"  Szansa min {min_szansa}% (akceptuj mniej nóg jeśli trzeba — cel kursu ważniejszy).\n"
            f"  Dobieraj nogi o najwyższym EV_netto w tej samej lidze, unikaj >2 nóg z tej samej ligi."
        )

    opis_a = _opis_kuponu("KUPON A", cel_a, 50.0, "11-14x", 25)
    opis_b = _opis_kuponu("KUPON B", cel_b, 100.0, "22-28x", 15)

    return f"""Zbuduj 2 kupony AKO z podanymi celami. Kurs łączny jest PRIORYTETEM nad min szansą.
Zasada singla: pojedyncza noga tylko gdy kurs >= 1.80. Kurs 1.35-1.80 tylko jako noga AKO.
Min 3 nogi, max 6 nóg na kupon. Max 2 nogi z tej samej ligi. Nie łącz typów z jednego meczu.
WAŻNE: aby osiągnąć wysoki kurs, musisz zebrać 4-6 nóg — nie buduj singla ani 2-nożnego kuponu!

ZASADA WSPÓLNYCH NÓG (kotwice):
- Noga z pewnosc_pct >= 75% to KOTWICA — może pojawić się w obu kuponach (to dobra dywersyfikacja).
- Noga z pewnosc_pct < 75% musi być UNIKALNA — wchodzi tylko do jednego kuponu.
- Kupon B musi różnić się od A przynajmniej w 2 nogach poniżej 75% pewności (inne mecze / inne typy).

{opis_a}
{opis_b}"""


def _analizuj_forme(mecze: list) -> dict:
    """Analyze last 5 matches: wins, losses, goals for/against, trend.

    Args:
        mecze: List of match dicts with keys: result (1/0/X), scored, conceded

    Returns:
        Dict with: wins, losses, draws, gf_avg, ga_avg, trend
    """
    if not mecze:
        return {
            "wins": 0, "losses": 0, "draws": 0,
            "gf_avg": 0.0, "ga_avg": 0.0,
            "trend": "unknown"
        }

    wins = sum(1 for m in mecze if m.get("result") == "1")
    losses = sum(1 for m in mecze if m.get("result") == "0")
    draws = sum(1 for m in mecze if m.get("result") == "X")

    gf_sum = sum(m.get("scored", 0) for m in mecze)
    ga_sum = sum(m.get("conceded", 0) for m in mecze)
    gf_avg = round(gf_sum / len(mecze), 2)
    ga_avg = round(ga_sum / len(mecze), 2)

    # Trend: compare first 2 matches vs last 2 matches
    if len(mecze) >= 2:
        early_wins = sum(1 for m in mecze[:2] if m.get("result") == "1")
        recent_wins = sum(1 for m in mecze[-2:] if m.get("result") == "1")
        if recent_wins > early_wins:
            trend = "strong_up" if recent_wins == 2 else "up"
        elif recent_wins < early_wins:
            trend = "strong_down" if recent_wins == 0 else "down"
        else:
            trend = "stable"
    else:
        trend = "unknown"

    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "gf_avg": gf_avg,
        "ga_avg": ga_avg,
        "trend": trend
    }


def _wyciagnij_json(tekst: str) -> dict:
    """Wyciąga JSON z odpowiedzi AI (nawet jeśli AI doda tekst dookoła)."""
    # Szukaj bloku JSON
    match = re.search(r"\{[\s\S]*\}", tekst)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Fallback – spróbuj cały tekst
    try:
        return json.loads(tekst)
    except json.JSONDecodeError:
        return {"typ": "brak", "pewnosc": 0, "uzasadnienie": tekst[:300], "value_bet": False}


def _deduplikuj_kupony(dane: dict, min_wspolna_pewnosc: int = 75) -> None:
    """
    Usuwa z kupon_b nogi współdzielone z kupon_a gdy pewnosc_pct < min_wspolna_pewnosc.
    Nogi o wysokiej pewności (kotwice >=75%) mogą być w obu kuponach — to legalna dywersyfikacja.
    Przelicza kurs_laczny i szansa_wygranej_pct kupon_b po przycinaniu.
    """
    a_zdarzenia = (dane.get("kupon_a") or {}).get("zdarzenia", [])
    b_zdarzenia = (dane.get("kupon_b") or {}).get("zdarzenia", [])
    if not a_zdarzenia or not b_zdarzenia:
        return

    # Klucz identyfikujący nogę: mecz + typ (lowercase, stripped)
    a_klucze_slabe = {
        (z.get("mecz", "").lower().strip(), z.get("typ", "").lower().strip())
        for z in a_zdarzenia
        if z.get("pewnosc_pct", 0) < min_wspolna_pewnosc
    }

    nowe_b = [
        z for z in b_zdarzenia
        if (z.get("mecz", "").lower().strip(), z.get("typ", "").lower().strip())
        not in a_klucze_slabe
    ]

    if len(nowe_b) == len(b_zdarzenia):
        return  # nic nie usunięto

    kupon_b = dane["kupon_b"]
    kupon_b["zdarzenia"] = nowe_b
    if nowe_b:
        kurs_l = math.prod(float(z.get("kurs", 1.0)) for z in nowe_b)
        szansa = math.prod(z.get("pewnosc_pct", 50) / 100.0 for z in nowe_b) * 100
    else:
        kurs_l, szansa = 1.0, 0.0
    kupon_b["kurs_laczny"] = round(kurs_l, 2)
    kupon_b["szansa_wygranej_pct"] = round(szansa, 1)
    kupon_b["_deduped"] = True


def _wymusz_40pct(dane: dict, min_szansa: float = 40.0) -> None:
    """
    Walidacja po stronie Python: jeśli kupon ma szansa_wygranej_pct < 40,
    usuwa nogi od najniższej pewności dopóki iloczyn >= 40% lub zostanie 1 noga.
    Aktualizuje kurs_laczny, szansa_wygranej_pct, wygrana_netto w miejscu.
    """
    for kupon_key in ("kupon_a", "kupon_b"):
        kupon = dane.get(kupon_key, {})
        zdarzenia = kupon.get("zdarzenia", [])
        if not zdarzenia:
            continue

        def _szansa(legs):
            probs = [z.get("pewnosc_pct", 50) / 100.0 for z in legs]
            return math.prod(probs) * 100

        # Przycinaj od najsłabszej nogi dopóki szansa < min_szansa i len > 1
        while len(zdarzenia) > 1 and _szansa(zdarzenia) < min_szansa:
            # usuń nogę z najniższą pewnością
            zdarzenia.sort(key=lambda z: z.get("pewnosc_pct", 50))
            zdarzenia.pop(0)

        # Przelicz kurs i szansę
        kurs_l = 1.0
        for z in zdarzenia:
            kurs_l *= z.get("kurs", 1.0)

        szansa = _szansa(zdarzenia)
        kupon["zdarzenia"]           = zdarzenia
        kupon["kurs_laczny"]         = round(kurs_l, 2)
        kupon["szansa_wygranej_pct"] = round(szansa, 1)
        # wygrana_netto liczona ze stawki 10 PLN domyślnie (zaktualizuje się przy wyświetlaniu)
        kupon["_trimmed"] = True
