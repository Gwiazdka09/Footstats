# ================================================================
#  MODUL 11 - TYPY BUKMACHERSKIE + VALUE BET FILTER (P7.6)
# ================================================================

# Minimum thresholds for a bet to be considered value
MIN_EV_PCT = 3.0    # Expected Value > 3%
MIN_KELLY_PCT = 1.0  # Kelly fraction > 1% of bankroll


def calculate_ev(prob: float, odds: float) -> float:
    """
    Expected Value (%) = prob * (odds - 1) * 100 - (1 - prob) * 100
                       = (prob * odds - 1) * 100
    """
    return (prob * odds - 1.0) * 100.0


def is_value_bet(prob: float, odds: float, min_ev_pct: float = MIN_EV_PCT) -> bool:
    """Return True if EV exceeds minimum threshold."""
    return calculate_ev(prob, odds) >= min_ev_pct


def kelly_fraction(prob: float, odds: float) -> float:
    """
    Full Kelly fraction: f* = (prob * (odds - 1) - (1 - prob)) / (odds - 1)
                             = (prob * odds - 1) / (odds - 1)
    """
    if odds <= 1.0:
        return 0.0
    return max(0.0, (prob * odds - 1.0) / (odds - 1.0))


def filter_value_bets(
    kandydaci: list[dict],
    min_ev_pct: float = MIN_EV_PCT,
    min_kelly_pct: float = MIN_KELLY_PCT,
) -> list[dict]:
    """
    Remove candidates where EV < min_ev_pct OR Kelly < min_kelly_pct.
    Candidates without odds data are kept (can't compute EV).
    """
    wynik = []
    for k in kandydaci:
        conf = k.get("pewnosc_kalibrowana") or (k.get("pewnosc_pct") or 50) / 100.0
        odds = _get_best_odds(k)
        if odds is None:
            wynik.append(k)  # no odds data — keep
            continue
        ev = calculate_ev(float(conf), float(odds))
        kf = kelly_fraction(float(conf), float(odds)) * 100.0  # as %
        k["ev_value_pct"] = round(ev, 2)
        k["kelly_fraction_pct"] = round(kf, 3)
        if ev >= min_ev_pct and kf >= min_kelly_pct:
            wynik.append(k)
    return wynik


def _get_best_odds(kandydat: dict) -> float | None:
    """Extract best odds from candidate (Bzzoiro odds dict or direct kurs field)."""
    odds_dict = kandydat.get("odds") or {}
    if isinstance(odds_dict, dict):
        vals = [v for v in odds_dict.values() if isinstance(v, (int, float)) and 1.0 < v < 50.0]
        if vals:
            return float(max(vals))
    kurs = kandydat.get("kurs")
    if kurs and isinstance(kurs, (int, float)) and kurs > 1.0:
        return float(kurs)
    return None

def typy_zaklady(w: dict) -> list:
    pw, pr, pp  = w["p_wygrana"], w["p_remis"], w["p_przegrana"]
    bt, o25, u25 = w["btts"], w["over25"], w["under25"]
    wyniki = []
    def dodaj(typ, val, pewny=70, dobry=55):
        if val >= pewny:   wyniki.append((typ, f"{val:.1f}%", "PEWNY"))
        elif val >= dobry: wyniki.append((typ, f"{val:.1f}%", "DOBRY"))
    dodaj("1  (Gospodarz wygrywa)", pw)
    if pr >= 32: wyniki.append(("X  (Remis)", f"{pr:.1f}%", "DOBRY"))
    dodaj("2  (Gosc wygrywa)", pp)
    dodaj("1X (Gosp. lub remis)",  pw + pr, 80, 72)
    dodaj("X2 (Remis lub gosc)",   pr + pp, 80, 72)
    dodaj("12 (Ktos wygrywa)",     pw + pp, 85, 75)
    dodaj("BTTS TAK", bt, 65, 55)
    if bt < 45: wyniki.append(("BTTS NIE", f"{100-bt:.1f}%", "DOBRY" if 100-bt>=60 else "SLABY"))
    dodaj("Over 2.5", o25, 70, 58)
    dodaj("Under 2.5", u25, 68, 58)
    return wyniki
