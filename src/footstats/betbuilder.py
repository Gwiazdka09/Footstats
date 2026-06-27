"""
BetBuilder kombinacje z EV filtrowaniem.

Obsługuje dwa formaty nazw:
  - Superbet API: "Mecz: 1", "Liczba goli: powyżej 2.5"
  - Poisson (legacy): "1", "Over 2.5", "BTTS_TAK"

Użycie (Superbet API data):
    typy = [Typ("Mecz: 1", 1.76), Typ("Liczba goli: powyżej 2.5", 1.88)]
    combos = generuj_kombinacje(typy, kurs_rynkowy=3.20)

Użycie (Poisson → AI context):
    formatted = fmt_bb_sugestie(w["bet_builder"])
"""

import re
from dataclasses import dataclass
from itertools import combinations
from math import prod

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Typ:
    nazwa: str
    kurs: float


@dataclass(frozen=True)
class Kombinacja:
    typy: tuple["Typ", ...]
    kurs_laczny: float        # iloczyn kursów — zakłada NIEZALEŻNOŚĆ nóg (patrz niżej)
    ev: float | None          # NAIWNE EV (niezależność); zawyżone dla skorelowanych
                              # nóg. None gdy brak kurs_rynkowy.


# ── Conflict detection ────────────────────────────────────────────────────────

def _sel(nazwa: str) -> str:
    """'Mecz: 1' → '1',  'Liczba goli: powyżej 2.5' → 'powyżej 2.5'"""
    return nazwa.split(": ", 1)[-1].strip() if ": " in nazwa else nazwa


def _market(nazwa: str) -> str:
    """'Mecz: 1' → 'Mecz',  'Over 2.5' → ''"""
    return nazwa.split(": ", 1)[0].strip() if ": " in nazwa else ""


_WYNIKI_1X2 = {"1", "x", "2"}
_TAK_NIE    = {"tak", "nie"}
_OU_RE      = re.compile(r'(powyżej|poniżej|over|under)\s+(\d+\.?\d*)', re.IGNORECASE)
_OVER_WDS   = {"powyżej", "over"}
_UNDER_WDS  = {"poniżej", "under"}


def _parse_ou(s: str) -> tuple[str, float] | None:
    """'powyżej 2.5' → ('over', 2.5),  'poniżej 1.5' → ('under', 1.5)"""
    m = _OU_RE.match(s.strip())
    if not m:
        return None
    direction = "over" if m.group(1).lower() in _OVER_WDS else "under"
    return direction, float(m.group(2))


# Legacy pairs (Poisson short-name format) - normalized to lowercase
_LEGACY_PARY: list[frozenset] = [
    frozenset({"1", "2"}),
    frozenset({"1", "x"}),
    frozenset({"x", "2"}),
    frozenset({"over", "under"}),
    frozenset({"btts_tak", "btts_nie"}),
    frozenset({"over 2.5", "under 2.5"}),
    frozenset({"over 1.5", "under 1.5"}),
]

# Outcome mapping for result-based markets (1=Home, X=Draw, 2=Away)
_RESULT_MARKETS = {"mecz", "draw no bet", "podwójna szansa", "wynik końcowy"}
_SELECTION_OUTCOMES = {
    "1": {"1"},
    "x": {"x"},
    "2": {"2"},
    "1x": {"1", "x"},
    "x2": {"x", "2"},
    "12": {"1", "2"},
    "1 lub x": {"1", "x"},
    "x lub 2": {"x", "2"},
    "1 lub 2": {"1", "2"},
    "home": {"1"},
    "away": {"2"},
    "draw": {"x"},
}


def _para_sprzeczna(a: str, b: str) -> bool:
    """
    True jeśli dwa typy są wzajemnie wykluczające się.

    Reguły:
    1. Legacy exact-name pairs (backward compat z Poisson)
    2. Ten sam market → 1/X/2 wynik (dowolne dwa konfliktują)
    3. Ten sam market → Tak/Nie (binarne)
    4. Ten sam market → Over X + Under Y gdzie Y <= X
    5. Ten sam compound market (zawiera '/') → dowolne dwa wyniki konfliktują
    """
    ma, mb = _market(a), _market(b)
    sa = _sel(a).lower()
    sb = _sel(b).lower()

    # 1. Legacy pairs (must be two DIFFERENT selections forming a conflict)
    for para in _LEGACY_PARY:
        if sa != sb and (frozenset({a, b}) == para or frozenset({sa, sb}) == para):
            return True

    # 1b. Cross-market result conflicts (e.g., Mecz: 1 vs Draw No Bet: 2)
    if (ma.lower() in _RESULT_MARKETS or not ma) and (mb.lower() in _RESULT_MARKETS or not mb):
        outcomes_a = _SELECTION_OUTCOMES.get(sa)
        outcomes_b = _SELECTION_OUTCOMES.get(sb)
        if outcomes_a and outcomes_b:
            # Conflict if they share no possible outcomes (mutually exclusive)
            # Exception: if identical selection in different market, it's NOT a conflict
            if not (outcomes_a & outcomes_b):
                return True

    # Wszystkie dalsze reguły wymagają tego samego marketu
    if not ma or ma != mb:
        return False

    # 2. Wynik meczu: 1/X/2 (redundant with 1b if market is 'mecz', but kept for clarity)
    if sa != sb and {sa, sb} <= _WYNIKI_1X2:
        return True

    # 3. Tak / Nie
    if sa != sb and {sa, sb} == _TAK_NIE:
        return True

    # 4. Over/Under w tym samym markecie
    ou_a = _parse_ou(sa)
    ou_b = _parse_ou(sb)
    if ou_a and ou_b:
        dir_a, val_a = ou_a
        dir_b, val_b = ou_b
        # over X + under Y → niemożliwe jeśli Y <= X
        if dir_a == "over" and dir_b == "under" and val_b <= val_a:
            return True
        if dir_b == "over" and dir_a == "under" and val_a <= val_b:
            return True

    # 5. Compound half/full-time markets ("1.Połowa/Mecz: 1/1" vs "1.Połowa/Mecz: X/X")
    if "/" in ma and sa != sb:
        return True

    # 6. Same market, same direction Over/Under — redundant, nie wartościowa kombinacja
    #    (powyżej 3.5 + powyżej 4.5 = wystarczy postawić samo powyżej 4.5)
    ou_a2 = _parse_ou(sa)
    ou_b2 = _parse_ou(sb)
    if ou_a2 and ou_b2 and ou_a2[0] == ou_b2[0]:
        return True

    return False


def _sprzeczne(typy: tuple["Typ", ...]) -> bool:
    """True jeśli jakakolwiek para typów w kombinacji jest sprzeczna."""
    for i in range(len(typy)):
        for j in range(i + 1, len(typy)):
            if _para_sprzeczna(typy[i].nazwa, typy[j].nazwa):
                return True
    return False


# ── Combination generator ─────────────────────────────────────────────────────

def generuj_kombinacje(
    typy: list["Typ"],
    kurs_rynkowy: float | None = None,
    min_typy: int = 2,
    max_typy: int = 4,
    min_kurs: float = 1.60,
    min_ev: float = 0.10,
) -> list["Kombinacja"]:
    """
    Generuje niesprzeczne kombinacje z filtrami kurs i EV.

    UWAGA (korelacja): kurs_laczny = iloczyn kursów standalone, co zakłada
    NIEZALEŻNOŚĆ nóg. Dla skorelowanych typów (np. "Mecz: 1" + "Liczba goli:
    powyżej 2.5", albo "1" + "BTTS") wspólne prawdopodobieństwo jest WYŻSZE niż
    iloczyn → realny fair-kurs combo jest NIŻSZY → naiwne EV (kurs_laczny/
    kurs_rynkowy) jest ZAWYŻONE i może przepuścić przegrywające combo.
    Do decyzji o wartości używaj skorelowanego silnika
    `core/betbuilder_rules.szansa_combo(wybrane, macierz_poissona)` (joint-prob
    z macierzy), nie EV z tej funkcji. Tu EV traktuj jako górne ograniczenie.
    Produkcyjnie (daily_phases) wołane bez kurs_rynkowy → kurs_laczny służy
    tylko jako orientacyjny kurs combo do wyświetlenia.

    Args:
        typy:          Lista Typ do kombinowania.
        kurs_rynkowy:  Benchmark (np. exchange); jeśli None, EV nie jest liczony.
        min_typy:      Minimalna liczba nóg w kombinacji.
        max_typy:      Maksymalna liczba nóg (cap zapobiega wykładniczemu hangowi).
        min_kurs:      Minimalny kurs łączny.
        min_ev:        Minimalny NAIWNY EV (ignorowany jeśli kurs_rynkowy=None).
    """
    if not typy:
        return []
    wyniki: list[Kombinacja] = []
    limit = min(max_typy, len(typy))
    for r in range(min_typy, limit + 1):
        for combo in combinations(typy, r):
            if _sprzeczne(combo):
                continue
            kurs_l = round(prod(t.kurs for t in combo), 3)
            if kurs_l < min_kurs:
                continue
            ev = round(kurs_l / kurs_rynkowy - 1, 4) if kurs_rynkowy else None
            if kurs_rynkowy and (ev is None or ev < min_ev):
                continue
            wyniki.append(Kombinacja(typy=combo, kurs_laczny=kurs_l, ev=ev))
    return sorted(wyniki, key=lambda k: k.ev if k.ev is not None else k.kurs_laczny, reverse=True)


# ── Poisson formatter (legacy AI context) ─────────────────────────────────────

def _parsuj_prob(s: str) -> float | None:
    """'Szansa: 45%' → 0.45"""
    m = re.search(r'Szansa:\s*(\d+)%', s)
    return int(m.group(1)) / 100.0 if m else None


def fmt_bb_sugestie(
    sugestie: list[str],
    kurs_rynkowy: float | None = None,
    max_items: int = 8,
) -> list[str]:
    """
    Konwertuje Poisson sugestie do formatu z kurs_fair dla kontekstu AI.
    Wejście: ["1 & Over 1.5 (Szansa: 45%)", ...]
    Wyjście: ["1 & Over 1.5 @2.22 (p=45%)", ...]
    """
    wyniki: list[str] = []
    for s in sugestie[:max_items]:
        prob  = _parsuj_prob(s)
        nazwa = re.sub(r'\s*\(Szansa:.*?\)', '', s).strip()
        if prob and prob > 0:
            kurs_f = round(1.0 / prob, 2)
            ev_str = ""
            if kurs_rynkowy and kurs_rynkowy > 1.0:
                ev     = kurs_f / kurs_rynkowy - 1.0
                ev_str = f" EV={ev * 100:+.0f}%"
            wyniki.append(f"{nazwa} @{kurs_f}{ev_str} (p={int(prob * 100)}%)")
        else:
            wyniki.append(nazwa)
    return wyniki
