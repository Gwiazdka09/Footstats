"""core/flip_advisor.py — pure werdykty flipu lewarów M1 (selekcja / gating lig).

Bezstanowe. Wejście: zagregowane wiersze settled (pasma pewności / per-liga).
Wyjście: rekomendacja czy flipnąć flagę (`SELECTION_MIN_CONF` / `LEAGUE_GATING`).
Cały IO (Neon, print) w `scripts/calibration_monitor.py` — tu zero efektów ubocznych.
"""
from __future__ import annotations

# Domyślne progi decyzyjne (spójne z lewarami w system_paper / config.LIGI_SLABE).
SELEKCJA_PROG_CONF = 65.0   # pasmo high-conf (offline 65%+ = 68%)
SELEKCJA_MIN_N = 10         # min settled w paśmie na werdykt
SELEKCJA_MIN_DELTA = 3.0    # high-conf musi bić ogół o >= tyle pp
SELEKCJA_MIN_ACC = 55.0     # i sam trzymać >= tyle (cel M1)

GATING_PROG_ACC = 50.0      # liga < tyle % → kandydat do gatingu
GATING_MIN_N = 8            # min settled w lidze na werdykt


def werdykt_selekcja(pasma: list, prog: float = SELEKCJA_PROG_CONF,
                     min_n: int = SELEKCJA_MIN_N) -> dict:
    """
    Czy flipnąć `SELECTION_MIN_CONF` (lever #1)? Porównuje trafność pasma high-conf
    (band >= prog) z ogółem. `pasma`: iterowalne (band, n, won, acc).
    Zwraca {status, ...}: status ∈ {brak, czekaj, gotowe}; gotowe → flip: bool.
    """
    pasma = list(pasma)
    n_all = sum(p[1] for p in pasma)
    won_all = sum(p[2] for p in pasma)
    if n_all == 0:
        return {"status": "brak", "msg": "brak settled"}

    acc_all = won_all / n_all * 100
    high = [p for p in pasma if p[0] >= prog]
    n_high = sum(p[1] for p in high)
    won_high = sum(p[2] for p in high)

    if n_high < min_n:
        return {"status": "czekaj", "n_high": n_high, "min_n": min_n,
                "acc_all": round(acc_all, 1),
                "msg": f"pasmo >={prog:.0f}% ma {n_high} settled (potrzeba {min_n})"}

    acc_high = won_high / n_high * 100
    delta = acc_high - acc_all
    flip = delta >= SELEKCJA_MIN_DELTA and acc_high >= SELEKCJA_MIN_ACC
    return {"status": "gotowe", "flip": flip, "n_high": n_high,
            "acc_high": round(acc_high, 1), "acc_all": round(acc_all, 1),
            "delta": round(delta, 1)}


def werdykt_gating(per_liga: list, prog: float = GATING_PROG_ACC,
                   min_n: int = GATING_MIN_N) -> dict:
    """
    Które ligi gatować (lever #2)? `per_liga`: iterowalne (league, n, won, acc).
    Zwraca {slabe, mocne}: listy (league, n, acc) z n>=min_n; słabe = acc < prog.
    """
    slabe, mocne = [], []
    for lg, n, _, acc in per_liga:
        if n < min_n:
            continue
        (slabe if acc < prog else mocne).append((lg, n, round(acc, 1)))
    slabe.sort(key=lambda x: x[2])      # najsłabsze pierwsze
    mocne.sort(key=lambda x: -x[2])     # najmocniejsze pierwsze
    return {"slabe": slabe, "mocne": mocne}
