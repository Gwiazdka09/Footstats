"""Propozycje ryzyka (risk_low/medium/high) domyslnie WYLACZONE — decyzja 10.09.

Produkt to dziennik kuponow ludzi, nie nasze typy. Propozycje dnia byly
akumulatorami 4-6 nog po kursach ~3.5 / ~23 / ~90 — przy naszym ROI singla
-10.3% ich oczekiwana strata to ok. -40%, a prompt LLM ma wprost zakaz
akumulatorow ("Kazdy kupon = JEDEN mecz, JEDNA noga"). Pokazywanie ich ludziom
jako "Propozycje dnia" z przyciskiem "Skopiuj kupon" kloci sie tez z regula
`.claude/rules/wypuszczenie-pl.md` (zero zachet do gry).

Propozycje rodzily sie w TRZECH miejscach i kazde musi respektowac te sama flage:

    cloud_draft._zapisz_kupony_system   — kupony risk_* w bazie (draft 05:30)
    daily_agent (faza draft)            — to samo w lokalnym drafcie
    GET /coupons/daily-proposals        — Dashboard GUI i stary /preview

Paper trading singli (`build_single_leg_coupons`) zostaje — to pomiar modelu.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from footstats.core import system_coupons as sc


def _mecz(**nadpisz):
    m = {"gospodarz": "Arsenal", "goscie": "Chelsea", "data": "2026-09-10",
         "liga": "Premier League", "pw": 55.0, "pr": 25.0, "pp": 20.0,
         "o25": 52.0, "bt": 50.0, "odds": {"home": 1.8, "over_2_5": 1.9}}
    m.update(nadpisz)
    return m


@pytest.mark.parametrize("wartosc, oczekiwane", [
    (None, False), ("", False), ("0", False), ("false", False),
    ("1", True), ("true", True),
])
def test_flaga_domyslnie_wylaczona(monkeypatch, wartosc, oczekiwane):
    if wartosc is None:
        monkeypatch.delenv("SYSTEM_RISK_COUPONS", raising=False)
    else:
        monkeypatch.setenv("SYSTEM_RISK_COUPONS", wartosc)
    assert sc.propozycje_ryzyka_wlaczone() is oczekiwane


def test_cloud_draft_bez_flagi_nie_tworzy_risk(monkeypatch):
    import footstats.core.cloud_draft as cd
    import footstats.core.system_paper as sp

    monkeypatch.delenv("SYSTEM_RISK_COUPONS", raising=False)
    monkeypatch.setattr(sp, "build_single_leg_coupons", lambda w: 4)

    def _nie_wolno(*a, **k):
        raise AssertionError("generate_system_coupons wolane mimo wylaczonej flagi")

    monkeypatch.setattr(sc, "generate_system_coupons", _nie_wolno)

    created, risk = cd._zapisz_kupony_system([_mecz()])
    assert created == 4, "paper trading singli musi zostac"
    assert risk == 0


def test_daily_agent_respektuje_flage():
    """Lokalny draft woła `generate_system_coupons` — ta sama flaga, nie druga regula."""
    zrodlo = Path("src/footstats/daily_agent.py").read_text(encoding="utf-8")
    kod = "\n".join(l for l in zrodlo.splitlines() if not l.lstrip().startswith("#"))
    przed, _, _ = kod.partition("generate_system_coupons(")
    assert "propozycje_ryzyka_wlaczone()" in przed[-1500:], (
        "wywolanie generate_system_coupons w daily_agent nie stoi za flaga")


def test_endpoint_propozycji_bez_flagi_oddaje_puste_koszyki(monkeypatch):
    import footstats.api.routes.coupons as routes
    from footstats.core.response_cache import clear_response_cache

    monkeypatch.delenv("SYSTEM_RISK_COUPONS", raising=False)
    monkeypatch.setattr(routes, "_MATCHES_CACHE", [])
    monkeypatch.setattr(routes, "_fetch_predictions",
                        lambda: sc.na_ksztalt_pred_ml([_mecz()]))
    clear_response_cache()

    wynik = routes.get_daily_proposals(user_id=1)
    # `cached_response` oddaje JSONResponse (nagłówki cache), nie surowy dict.
    if hasattr(wynik, "body"):
        import json
        wynik = json.loads(wynik.body)

    assert set(wynik) == {"low", "medium", "high"}, "GUI oczekuje trzech koszykow"
    assert all(not wynik[t]["legs"] for t in wynik), "propozycje mimo wylaczonej flagi"
