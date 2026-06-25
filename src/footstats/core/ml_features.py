"""
core/ml_features.py — inżynieria cech do modelu ML (LightGBM) 1X2.

Pojedyncze przejście chronologiczne po meczach: dla każdego meczu emituje wektor
cech ZE STANU SPRZED meczu, POTEM aktualizuje stan jego wynikiem → zero leakage
(out-of-sample by design, zgodnie z walk-forward).

Cechy (wszystkie as-of, pre-match):
  - pi-ratings (Constantinou & Fenton, dom/wyjazd osobno, opponent-adjusted) — top cecha SOTA
  - Elo (klasyczny, z przewagą własnego boiska)
  - rolling form ostatnie N: gole zdobyte/stracone, punkty, strzały/celne
  - pozycja + punkty w tabeli sezonu (z core/standings logiki, inkrementalnie)
  - rest-days (dni od ostatniego meczu drużyny)
  - devig kursów 1X2 (sygnał rynku; do A/B można wyłączyć)

Target: result H/D/A → 0/1/2 (multiclass).
"""
from __future__ import annotations

import math
from collections import defaultdict, deque

import pandas as pd

from footstats.core.standings import season_start_year

# ── Hiperparametry ratingów ────────────────────────────────────────────────────
_PI_LR = 0.10       # learning rate pi-rating
_PI_GAMMA = 0.50    # cross-update dom↔wyjazd
_PI_C = 2.0         # tłumienie błędu (log10)
_ELO_K = 20.0       # K-factor Elo
_ELO_HOME_ADV = 65.0
_ELO_START = 1500.0
_FORM_N = 5         # okno rolling form

_TARGET = {"H": 0, "D": 1, "A": 2}

FEATURE_COLS = [
    "pi_home", "pi_away", "pi_diff",
    "elo_diff",
    "h_gf5", "h_ga5", "a_gf5", "a_ga5",
    "h_pts5", "a_pts5",
    "h_shots5", "a_shots5", "h_sot5", "a_sot5",
    "h_pos", "a_pos", "pos_diff", "pts_diff",
    "h_rest", "a_rest",
    "mkt_ph", "mkt_pd", "mkt_pa",
]
# Cechy rynkowe (do wariantu BEZ kursów = szukanie edge).
MARKET_COLS = ["mkt_ph", "mkt_pd", "mkt_pa"]


def _pi_to_gd(r: float) -> float:
    """Rating → oczekiwana różnica bramek (linowo; rating trzymany w jednostkach gole)."""
    return r


def _devig(oh, od, oa) -> tuple[float, float, float]:
    """Devig 1X2 (proporcjonalny). (nan,nan,nan) gdy kursy niekompletne."""
    try:
        oh, od, oa = float(oh), float(od), float(oa)
    except (TypeError, ValueError):
        return (math.nan, math.nan, math.nan)
    if min(oh, od, oa) <= 1.0:
        return (math.nan, math.nan, math.nan)
    inv = [1 / oh, 1 / od, 1 / oa]
    s = sum(inv)
    return (inv[0] / s, inv[1] / s, inv[2] / s)


def _mean(dq: deque) -> float:
    return sum(dq) / len(dq) if dq else math.nan


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Buduje DataFrame cech + target z surowych meczów (chronologicznie, no-lookahead).

    Wejście: kolumny date, league, season, home, away, hg, ag, result (+opcj. hs/as_/hst/ast,
    odds_h/odds_d/odds_a). Wyjście: FEATURE_COLS + 'y' (0/1/2) + 'date'/'league' (do splitu WF).
    """
    df = df.sort_values("date").reset_index(drop=True)

    pi_home: dict[str, float] = defaultdict(float)
    pi_away: dict[str, float] = defaultdict(float)
    elo: dict[str, float] = defaultdict(lambda: _ELO_START)
    gf: dict[str, deque] = defaultdict(lambda: deque(maxlen=_FORM_N))
    ga: dict[str, deque] = defaultdict(lambda: deque(maxlen=_FORM_N))
    pts: dict[str, deque] = defaultdict(lambda: deque(maxlen=_FORM_N))
    shots: dict[str, deque] = defaultdict(lambda: deque(maxlen=_FORM_N))
    sot: dict[str, deque] = defaultdict(lambda: deque(maxlen=_FORM_N))
    last_date: dict[str, object] = {}
    # tabela sezonu: (league, season_start, team) → [pkt, gf, ga, m]
    tab: dict[tuple, list] = defaultdict(lambda: [0, 0, 0, 0])

    rows = []
    has_shots = "hs" in df.columns and "as_" in df.columns
    has_sot = "hst" in df.columns and "ast" in df.columns

    for r in df.itertuples(index=False):
        h, a = r.home, r.away
        if pd.isna(r.hg) or pd.isna(r.ag):
            continue
        hg, ag = int(r.hg), int(r.ag)
        syr = season_start_year(getattr(r, "season", None))
        lg = r.league
        kh, ka = (lg, syr, h), (lg, syr, a)

        # pozycja w tabeli (przed meczem)
        liga_sezon = [(t, v) for (l_, s_, t), v in tab.items() if l_ == lg and s_ == syr]
        liga_sezon.sort(key=lambda x: (x[1][0], x[1][1] - x[1][2], x[1][1]), reverse=True)
        poz = {t: i + 1 for i, (t, _) in enumerate(liga_sezon)}
        h_pos = poz.get(h, math.nan)
        a_pos = poz.get(a, math.nan)
        h_pts_tab = tab[kh][0]
        a_pts_tab = tab[ka][0]

        mph, mpd, mpa = _devig(getattr(r, "odds_h", None), getattr(r, "odds_d", None),
                               getattr(r, "odds_a", None))

        rows.append({
            "pi_home": pi_home[h], "pi_away": pi_away[a],
            "pi_diff": pi_home[h] - pi_away[a],
            "elo_diff": elo[h] + _ELO_HOME_ADV - elo[a],
            "h_gf5": _mean(gf[h]), "h_ga5": _mean(ga[h]),
            "a_gf5": _mean(gf[a]), "a_ga5": _mean(ga[a]),
            "h_pts5": _mean(pts[h]), "a_pts5": _mean(pts[a]),
            "h_shots5": _mean(shots[h]), "a_shots5": _mean(shots[a]),
            "h_sot5": _mean(sot[h]), "a_sot5": _mean(sot[a]),
            "h_pos": h_pos, "a_pos": a_pos,
            "pos_diff": (a_pos - h_pos) if not (math.isnan(h_pos) or math.isnan(a_pos)) else math.nan,
            "pts_diff": h_pts_tab - a_pts_tab,
            "h_rest": (r.date - last_date[h]).days if h in last_date else math.nan,
            "a_rest": (r.date - last_date[a]).days if a in last_date else math.nan,
            "mkt_ph": mph, "mkt_pd": mpd, "mkt_pa": mpa,
            "y": _TARGET.get(r.result, _TARGET["H"] if hg > ag else _TARGET["A"] if hg < ag else _TARGET["D"]),
            "date": r.date, "league": lg,
        })

        # ── AKTUALIZACJA STANU (po emisji cech) ──────────────────────────────
        obs_gd = max(-5, min(5, hg - ag))
        exp_gd = _pi_to_gd(pi_home[h]) - _pi_to_gd(pi_away[a])
        e = obs_gd - exp_gd
        psi = math.copysign(_PI_C * math.log10(1 + abs(e)), e)
        pi_home[h] += _PI_LR * psi
        pi_away[h] += _PI_LR * _PI_GAMMA * psi
        pi_away[a] -= _PI_LR * psi
        pi_home[a] -= _PI_LR * _PI_GAMMA * psi

        # Elo
        exp_h = 1 / (1 + 10 ** (-(elo[h] + _ELO_HOME_ADV - elo[a]) / 400))
        sc_h = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        elo[h] += _ELO_K * (sc_h - exp_h)
        elo[a] += _ELO_K * ((1 - sc_h) - (1 - exp_h))

        # form + tabela
        ph, pa = (3, 0) if hg > ag else (0, 3) if hg < ag else (1, 1)
        gf[h].append(hg); ga[h].append(ag); pts[h].append(ph)
        gf[a].append(ag); ga[a].append(hg); pts[a].append(pa)
        if has_shots:
            shots[h].append(getattr(r, "hs", math.nan)); shots[a].append(getattr(r, "as_", math.nan))
        if has_sot:
            sot[h].append(getattr(r, "hst", math.nan)); sot[a].append(getattr(r, "ast", math.nan))
        tab[kh][0] += ph; tab[kh][1] += hg; tab[kh][2] += ag; tab[kh][3] += 1
        tab[ka][0] += pa; tab[ka][1] += ag; tab[ka][2] += hg; tab[ka][3] += 1
        last_date[h] = r.date
        last_date[a] = r.date

    return pd.DataFrame(rows)
