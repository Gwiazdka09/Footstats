"""
test_core_pure_modules2.py — testy bet_builder (Poisson/Dixon-Coles), injury_correction,
ImportanceIndex (TD-31, dokończenie pokrycia modułów core).
"""
import math

import numpy as np
import pandas as pd

from footstats.core.bet_builder import (
    _poisson_prob, _dixon_coles_tau, probability_matrix,
    get_card_suggestions, get_corner_suggestions, get_betbuilder_suggestions,
    get_all_market_suggestions,
)
from footstats.core.lambda_optimizer import injury_correction
from footstats.core.importance import ImportanceIndex


# ── bet_builder._poisson_prob ─────────────────────────────────────────────

def test_poisson_prob_zgodny_ze_wzorem():
    # P(X=0; λ=2) = e^-2 ≈ 0.1353
    assert _poisson_prob(0, 2.0) == math.exp(-2.0)
    # P(X=2; λ=2) = 2^2 e^-2 / 2! = 2 e^-2
    assert abs(_poisson_prob(2, 2.0) - 2 * math.exp(-2.0)) < 1e-9


def test_poisson_prob_ujemna_lambda_zero():
    assert _poisson_prob(1, -1.0) == 0.0


def test_poisson_prob_sumuje_sie_do_1():
    # Suma P(X=k) dla k=0..20 przy λ=1.5 ≈ 1.0
    s = sum(_poisson_prob(k, 1.5) for k in range(21))
    assert abs(s - 1.0) < 1e-6


# ── bet_builder._dixon_coles_tau ──────────────────────────────────────────

def test_dixon_coles_tau_korekta_00():
    # rho<0 → tau dla 0:0 powyżej 1 (boost niskobramkowych)
    assert _dixon_coles_tau(0, 0, 1.5, 1.2, -0.05) > 1.0


def test_dixon_coles_tau_neutralny_dla_wysokich():
    assert _dixon_coles_tau(3, 2, 1.5, 1.2, -0.05) == 1.0


# ── bet_builder.probability_matrix ────────────────────────────────────────

def test_probability_matrix_normalizowana():
    mat = probability_matrix(1.4, 1.1)
    assert abs(mat.sum() - 1.0) < 1e-9
    assert (mat >= 0).all()


def test_probability_matrix_ksztalt():
    mat = probability_matrix(1.0, 1.0, max_goals=7)
    assert mat.shape == (8, 8)


def test_probability_matrix_silny_gospodarz_wygrywa_czesciej():
    mat = probability_matrix(2.5, 0.7)
    p_home = np.tril(mat, -1).sum()   # h > a
    p_away = np.triu(mat, 1).sum()    # a > h
    assert p_home > p_away


# ── bet_builder.get_card_suggestions ──────────────────────────────────────

def test_card_suggestions_brak_danych():
    assert get_card_suggestions(None) == []
    assert get_card_suggestions(0) == []


def test_card_suggestions_rygorystyczny_sedzia():
    s = get_card_suggestions(6.0)
    assert any("3.5" in x for x in s)
    assert any("4.5" in x for x in s)


def test_card_suggestions_lagodny_sedzia():
    s = get_card_suggestions(2.5)
    assert any("Poniżej" in x for x in s)


# ── bet_builder.get_corner_suggestions ────────────────────────────────────

def test_corner_suggestions_duzo_goli_duzo_roznych():
    s = get_corner_suggestions(2.0, 1.8)  # total 3.8 * 3.5 = 13.3 est corners
    assert any("Over 10.5" in x for x in s)


def test_corner_suggestions_dominacja_gospodarza():
    s = get_corner_suggestions(2.5, 1.0)  # lh > la*1.5
    assert any("Gospodarz rożne" in x for x in s)


# ── bet_builder.get_betbuilder_suggestions ────────────────────────────────

def test_betbuilder_zerowe_lambdy_pusta_lista():
    assert get_betbuilder_suggestions(0, 1.0) == []
    assert get_betbuilder_suggestions(1.0, 0) == []


def test_betbuilder_zwraca_sugestie_dla_realnych_lambd():
    s = get_betbuilder_suggestions(1.8, 1.3)
    assert isinstance(s, list)
    assert len(s) > 0
    assert all(isinstance(x, str) for x in s)


def test_betbuilder_dolacza_kartki_gdy_sedzia():
    s = get_betbuilder_suggestions(1.8, 1.3, ref_avg_yellow=6.0)
    assert any("kartek" in x for x in s)


# ── bet_builder.get_all_market_suggestions ────────────────────────────────

def test_all_markets_grupuje_kategorie():
    out = get_all_market_suggestions(2.0, 1.7, ref_avg_yellow=6.0)
    assert "BetBuilder" in out
    assert "Kartki" in out
    assert isinstance(out, dict)


# ── lambda_optimizer.injury_correction ────────────────────────────────────

def test_injury_brak_kontuzji_bez_zmian():
    assert injury_correction(1.5, [], is_home=True) == 1.5


def test_injury_obniza_lambde():
    inj = [{"position": "M"}, {"position": "D"}]
    skor = injury_correction(1.5, inj, is_home=False)
    assert skor < 1.5


def test_injury_gospodarz_mniejsza_kara():
    inj = [{"position": "M"}, {"position": "D"}, {"position": "G"}]
    dom = injury_correction(1.5, inj, is_home=True)
    gosc = injury_correction(1.5, inj, is_home=False)
    assert dom > gosc, "gospodarz traci mniej na kontuzjach"


def test_injury_floor_minus_20_procent():
    # Bardzo dużo kontuzji → kara ograniczona do -20%
    inj = [{"position": "M"}] * 20
    skor = injury_correction(2.0, inj, is_home=False)
    assert skor >= 2.0 * 0.8


def test_injury_napastnik_liczony():
    # FIX: napastnik ('F') obniża własne λ (wcześniej ignorowany — bug)
    inj = [{"position": "F"}]
    assert injury_correction(1.5, inj, is_home=False) < 1.5


# ── lambda_optimizer.injury_lambda_factors (model dwustronny) ─────────────

def test_factors_brak_kontuzji():
    from footstats.core.lambda_optimizer import injury_lambda_factors
    assert injury_lambda_factors([]) == (1.0, 1.0)


def test_factors_napastnik_obniza_atak():
    from footstats.core.lambda_optimizer import injury_lambda_factors
    atak, leak = injury_lambda_factors([{"position": "F"}, {"position": "M"}])
    assert atak < 1.0       # własny atak spada
    assert leak == 1.0      # obrona bez zmian


def test_factors_obronca_zwieksza_leak():
    from footstats.core.lambda_optimizer import injury_lambda_factors
    atak, leak = injury_lambda_factors([{"position": "D"}, {"position": "G"}])
    assert atak == 1.0      # atak bez zmian
    assert leak > 1.0       # rywal strzeli więcej


def test_factors_cap_20_procent():
    from footstats.core.lambda_optimizer import injury_lambda_factors
    atak, leak = injury_lambda_factors([{"position": "F"}] * 20 + [{"position": "D"}] * 20)
    assert atak == 0.80     # cap -20%
    assert leak == 1.20     # cap +20%


# ── ImportanceIndex.analiza ───────────────────────────────────────────────

def _tabela(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_importance_pusta_tabela_normal():
    out = ImportanceIndex(pd.DataFrame()).analiza("X")
    assert out["status"] == "NORMAL"


def test_importance_lider_tryb_finalny():
    # 36 rozegranych z 38 → 2 kolejki do końca, poz 1 → FINAL_TOP
    df = _tabela([{"Druzyna": "Lider", "Poz.": 1, "M": 36}])
    out = ImportanceIndex(df, n_druzyn=20).analiza("Lider")
    assert out["status"] == "FINAL_TOP"
    assert out["bonus_atak"] > 1.0


def test_importance_spadek_tryb_finalny():
    df = _tabela([{"Druzyna": "Slaby", "Poz.": 19, "M": 36}])
    out = ImportanceIndex(df, n_druzyn=20).analiza("Slaby")
    assert out["status"] == "FINAL_RELEGATION"


def test_importance_srodek_tabeli_wakacje_w_finalnym():
    df = _tabela([{"Druzyna": "Sredni", "Poz.": 10, "M": 36}])
    out = ImportanceIndex(df, n_druzyn=20).analiza("Sredni")
    assert out["status"] == "VACATION"


def test_importance_brak_druzyny_normal():
    df = _tabela([{"Druzyna": "Inny", "Poz.": 5, "M": 20}])
    out = ImportanceIndex(df, n_druzyn=20).analiza("NieMa")
    assert out["status"] == "NORMAL"
