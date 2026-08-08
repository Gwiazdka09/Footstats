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


# Rynek w słowniku `odds` → pole z prawdopodobieństwem modelu (w procentach).
# `None` znaczy "dopełnienie Over 2.5" — kandydat nie niesie osobnego pola dla Under.
RYNKI_KANDYDATA: tuple[tuple[str, str | None], ...] = (
    ("home",       "pw"),
    ("draw",       "pr"),
    ("away",       "pp"),
    ("over_2_5",   "o25"),
    ("under_2_5",  None),
    ("btts",       "bt"),
)


def _prawdopodobienstwo_rynku(kandydat: dict, pole: str | None) -> float | None:
    """Szansa modelu na dany rynek, jako ułamek. `None` gdy kandydat jej nie niesie."""
    if pole is None:
        over = kandydat.get("o25")
        return None if over is None else (100.0 - float(over)) / 100.0
    wartosc = kandydat.get(pole)
    return None if wartosc is None else float(wartosc) / 100.0


def _najlepszy_rynek(kandydat: dict) -> tuple[str, float, float, float] | None:
    """Rynek o najwyższym EV: (nazwa, kurs, EV%, Kelly%).

    Każdy rynek liczony ze SWOJEJ pary (szansa modelu, kurs tego rynku).
    Wcześniej brany był maksymalny kurs ze słownika i mnożony przez jedną
    ogólną pewność kandydata — czyli szansa jednego wyniku szła z kursem
    zupełnie innego. Przy 60% na gospodarza i kursie 7.41 na gościa dawało to
    EV +344% i przepuszczało śmieci jako "value bet".
    """
    odds = kandydat.get("odds")
    if not isinstance(odds, dict):
        return None

    najlepszy = None
    for rynek, pole in RYNKI_KANDYDATA:
        kurs = odds.get(rynek)
        if not isinstance(kurs, (int, float)) or not 1.0 < kurs < 50.0:
            continue
        prob = _prawdopodobienstwo_rynku(kandydat, pole)
        if prob is None:
            continue
        ev = calculate_ev(prob, float(kurs))
        if najlepszy is None or ev > najlepszy[2]:
            najlepszy = (rynek, float(kurs), ev, kelly_fraction(prob, float(kurs)) * 100.0)
    return najlepszy


def _jedyny_kurs(kandydat: dict) -> float | None:
    """Kurs kandydata, gdy da się go sparować z jedną pewnością BEZ zgadywania.

    Warstwa AI podaje albo `kurs` wprost, albo `odds` kluczowane etykietą typu
    ("1"/"X"/"2") zamiast nazwą rynku. Jedna wartość = parowanie jednoznaczne.
    Kilka wartości i jedna pewność — nie wiadomo, którego wyniku dotyczy, więc
    zwracamy None; branie maksimum było właśnie tym błędem, który naprawiamy.
    """
    kurs = kandydat.get("kurs")
    if isinstance(kurs, (int, float)) and kurs > 1.0:
        return float(kurs)

    odds = kandydat.get("odds")
    if isinstance(odds, dict):
        wartosci = [v for v in odds.values()
                    if isinstance(v, (int, float)) and 1.0 < v < 50.0]
        if len(wartosci) == 1:
            return float(wartosci[0])
    return None


def _ocena_pojedynczego_kursu(
    kandydat: dict,
) -> tuple[str, float, float, float] | None:
    """Ścieżka warstwy AI: jedna pewność + jeden kurs, bez słownika rynków."""
    kurs = _jedyny_kurs(kandydat)
    if kurs is None:
        return None

    # Jawne sprawdzenie None: skalibrowane 0.0 (lub pct=0) to realna ocena,
    # NIE sygnał "brak" — `or` mylił kiedyś 0.0 z brakiem i fabrykował 50%.
    conf_kal = kandydat.get("pewnosc_kalibrowana")
    if conf_kal is not None:
        prob = float(conf_kal)
    else:
        pct = kandydat.get("pewnosc_pct")
        if pct is None:
            return None
        prob = float(pct) / 100.0

    return ("kurs", float(kurs), calculate_ev(prob, float(kurs)),
            kelly_fraction(prob, float(kurs)) * 100.0)


def filter_value_bets(
    kandydaci: list[dict],
    min_ev_pct: float = MIN_EV_PCT,
    min_kelly_pct: float = MIN_KELLY_PCT,
) -> list[dict]:
    """Zostawia kandydatów z realnym edge: EV ≥ progu ORAZ Kelly ≥ progu.

    Kandydat oceniany po SWOIM najlepszym rynku — para (szansa modelu, kurs
    tego samego rynku). Bez kursów zostaje (nie ma czego liczyć, a odrzucenie
    byłoby zgadywaniem).
    """
    wynik = []
    for k in kandydaci:
        ocena = _najlepszy_rynek(k) or _ocena_pojedynczego_kursu(k)
        if ocena is None:
            wynik.append(k)  # brak kursów — zostaw
            continue
        rynek, _kurs, ev, kf = ocena
        if ev >= min_ev_pct and kf >= min_kelly_pct:
            # Bez mutacji wejścia — nowy dict (brak side-effectu na
            # współdzielonych dict-ach predykcji, w tym odrzuconych kandydatach).
            wynik.append({**k, "ev_value_pct": round(ev, 2),
                          "kelly_fraction_pct": round(kf, 3),
                          "value_rynek": rynek})
    return wynik


def _get_best_odds(kandydat: dict) -> float | None:
    """Najwyższy kurs kandydata. NIE używać do liczenia EV — patrz `_najlepszy_rynek`.

    Zostaje dla wywołań spoza filtra (raporty, podgląd), gdzie chodzi
    wyłącznie o rząd wielkości kursu, a nie o parowanie z prawdopodobieństwem.
    """
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
