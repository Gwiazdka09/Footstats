"""
national_lambda.py — Poisson dla reprezentacji (kadr). Model bazowy nie ma historii
reprezentacji (dataset = ligi klubowe), więc mundialowe predykcje szły z Bzzoiro-ML.
Tu λ liczone z realnych statów turnieju (`team_stats.team_attack_defense`):
  λ_gosp = (atak_gosp + obrona_gość) / 2   (własny atak + ile rywal traci)
  λ_gość = (atak_gość + obrona_gosp) / 2
Boiska neutralne (WC) → brak home advantage. Macierz Dixona-Coles jak bet_builder.
"""
from __future__ import annotations

from footstats.core.bet_builder import probability_matrix

_LAMBDA_FLOOR = 0.2


def national_team_probs(
    atk_home: float, def_home: float, atk_away: float, def_away: float,
    home_boost: float = 1.0,
) -> dict:
    """
    Zwraca {pw, pr, pp, o25, bt (procenty), lambda_h, lambda_a} z Poissona kadr.
    atk_* = gole/mecz, def_* = tracone/mecz (z team_attack_defense).
    home_boost: mnożnik λ_gosp dla realnych gospodarzy WC (USA/Meksyk/Kanada);
    boiska neutralne → 1.0 (domyślnie).
    """
    lh = max((atk_home + def_away) / 2.0 * home_boost, _LAMBDA_FLOOR)
    la = max((atk_away + def_home) / 2.0, _LAMBDA_FLOOR)

    mat = probability_matrix(lh, la)
    n = len(mat)
    pw = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if h > a)
    pr = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if h == a)
    pp = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if a > h)
    o25 = sum(mat[h][a] for h in range(n) for a in range(len(mat[h])) if h + a > 2.5)
    bt = sum(mat[h][a] for h in range(1, n) for a in range(1, len(mat[h])))

    return {
        "pw": round(pw * 100, 1),
        "pr": round(pr * 100, 1),
        "pp": round(pp * 100, 1),
        "o25": round(o25 * 100, 1),
        "bt": round(bt * 100, 1),
        "lambda_h": round(lh, 3),
        "lambda_a": round(la, 3),
    }
