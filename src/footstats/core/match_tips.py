"""Wspólne helpery do budowania typów (tips) z predykcji ML + kursów.

Wydzielone z api/routes/coupons.py::analyze_matches, żeby reużyć
w core/risk_proposals.py (propozycje dnia low/medium/high).
"""
from __future__ import annotations


def to_pct(v, default: float = 33.0) -> float:
    if v is None:
        return default
    f = float(v)
    return round(f * 100 if 0 < f < 1.0 else f, 1)


def fair_odds(prob_pct: float) -> float:
    return round(100.0 / prob_pct, 2) if prob_pct > 0 else 0.0


def dc_odds(o_a, o_b, o_other):
    """Kurs double-chance (1X / X2) z DEVIG.

    Kursy bukmacherskie mają marżę (Σ 1/kurs > 1). Naiwne 1/(1/a+1/b) sumuje
    zawyżone prawdopodobieństwa → dla faworyta wynik < 1.0 (kurs niemożliwy).
    Devig: zdejmij marżę z całej trójki 1X2, policz prawdziwe łączne prob dwóch
    wyników, dopiero z niego kurs. Zawsze > 1.0 (prob dwóch wyników < 1)."""
    if not o_a or not o_b or not o_other:
        return None
    inv_a, inv_b, inv_o = 1.0 / o_a, 1.0 / o_b, 1.0 / o_other
    over = inv_a + inv_b + inv_o
    p_dc = (inv_a + inv_b) / over if over > 0 else 0.0
    return round(1.0 / p_dc, 2) if p_dc > 0 else None


def build_tips(m: dict) -> dict:
    """Zbuduj listę typów (1, 1X, X, X2, 2, BTTS, Over...) z meczu predykcji."""
    ml = m.get("pred_ml") or {}
    odds = m.get("odds") or {}
    ph = to_pct(ml.get("prob_home_win"), 40.0)
    pr = to_pct(ml.get("prob_draw"), 25.0)
    pp = to_pct(ml.get("prob_away_win"), 35.0)
    po = to_pct(ml.get("prob_over_25"), 55.0)
    pbt = to_pct(ml.get("prob_btts_yes"), 45.0)
    s12 = ph + pr + pp or 100.0
    ph = round(ph / s12 * 100, 1)
    pr = round(pr / s12 * 100, 1)
    pp = round(100.0 - ph - pr, 1)

    o1 = odds.get("home") or fair_odds(ph)
    ox = odds.get("draw") or fair_odds(pr)
    o2 = odds.get("away") or fair_odds(pp)
    o1x = dc_odds(o1, ox, o2) or fair_odds(round(ph + pr, 1))
    ox2 = dc_odds(ox, o2, o1) or fair_odds(round(pr + pp, 1))

    pbtts_no = round(100.0 - pbt, 1)
    o_btts_y = odds.get("btts") or fair_odds(pbt)
    o_btts_n = odds.get("btts_no") or fair_odds(pbtts_no)

    po15 = min(round(po + 15.0, 1), 95.0)
    o_o15 = odds.get("over_1_5") or fair_odds(po15)
    o_o25 = odds.get("over_2_5") or fair_odds(po)

    tips = [
        {"tip": "1",        "label": "1 – Gosp.",  "odds": o1,       "prob": ph,              "color": "indigo"},
        {"tip": "1X",       "label": "1X",          "odds": o1x,      "prob": round(ph + pr, 1), "color": "blue"},
        {"tip": "X",        "label": "X – Remis",  "odds": ox,       "prob": pr,              "color": "slate"},
        {"tip": "X2",       "label": "X2",          "odds": ox2,      "prob": round(pr + pp, 1), "color": "purple"},
        {"tip": "2",        "label": "2 – Gość",   "odds": o2,       "prob": pp,              "color": "violet"},
        {"tip": "BTTS",     "label": "Obie str.",  "odds": o_btts_y, "prob": pbt,             "color": "amber"},
        {"tip": "BTTS nie", "label": "Nie obie",   "odds": o_btts_n, "prob": pbtts_no,        "color": "orange"},
        {"tip": "Over 1.5", "label": "Over 1.5",   "odds": o_o15,    "prob": po15,            "color": "teal"},
        {"tip": "Over 2.5", "label": "Over 2.5",   "odds": o_o25,    "prob": po,              "color": "emerald"},
    ]
    # Sugerowany typ = najbardziej prawdopodobny wynik 1X2 (argmax), NIE zawsze "1".
    # Wcześniej GUI brało tips[0] (stała kolejność listy) → zawsze "1".
    suggested_tip = max(
        ({"tip": "1", "odds": o1, "prob": ph},
         {"tip": "X", "odds": ox, "prob": pr},
         {"tip": "2", "odds": o2, "prob": pp}),
        key=lambda t: t["prob"],
    )

    return {
        "id": m["id"], "home": m["gosp"], "away": m["gosc"],
        "liga": m.get("liga", ""), "data": m.get("data", ""), "godzina": m.get("godzina", ""),
        "prob_home": ph, "prob_draw": pr, "prob_away": pp,
        "prob_over": po, "prob_btts": pbt, "tips": tips,
        "suggested_tip": suggested_tip,
    }
