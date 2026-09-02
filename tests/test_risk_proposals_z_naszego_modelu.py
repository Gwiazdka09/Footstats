"""Propozycje `risk_*` musza brac liczby z NASZEGO modelu albo nie powstac wcale.

STAN ZASTANY (zmierzony 01.09): `kupon_type LIKE 'risk_%'` = 0 wierszy w calej
historii, `shared=TRUE` = 0 na 339 kuponow. `generate_system_coupons` jest wolane
wylacznie z `daily_agent.py:952`, czyli z lokalnego draftu wylaczonego przy
migracji do Cloud Run. Zastapil go `cloud_draft.py`, ktory tej funkcji nie wola.

DLACZEGO NIE WYSTARCZY JEJ PODPIAC. `build_daily_proposals` -> `build_tips(m)`
czyta `m["pred_ml"]` w ksztalcie Bzzoiro (`prob_home_win`, `prob_draw`,
`prob_away_win`, `prob_over_25`, `prob_btts_yes`), a nasze `wyniki` z quick_picks
maja `pw/pr/pp/bt/o25`. Przy braku klucza `build_tips` NIE pada — podstawia
domyslne 40/25/35/55/45:

    ph = to_pct(ml.get("prob_home_win"), 40.0)

Naiwne podpiecie produkowaloby wiec kupony ze ZMYSLONYCH STALYCH, nie do
odroznienia od prawdziwych, i wystawialo je na publiczny leaderboard
(`shared=TRUE`). Stad adapter + twardy filtr zamiast jednej linijki.
"""
from __future__ import annotations

import pytest

from footstats.core.system_coupons import na_ksztalt_pred_ml


def _mecz(**nad):
    m = {"gospodarz": "Arsenal", "goscie": "Chelsea", "liga": "Premier League",
         "data": "2026-09-01", "pw": 55.0, "pr": 25.0, "pp": 20.0,
         "bt": 52.0, "o25": 58.0,
         "odds": {"home": 1.85, "draw": 3.4, "away": 4.2}}
    m.update(nad)
    return m


def test_adapter_przenosi_prawdziwe_liczby():
    wynik = na_ksztalt_pred_ml([_mecz()])

    assert len(wynik) == 1
    ml = wynik[0]["pred_ml"]
    assert ml["prob_home_win"] == 55.0
    assert ml["prob_draw"] == 25.0
    assert ml["prob_away_win"] == 20.0
    assert ml["prob_over_25"] == 58.0
    assert ml["prob_btts_yes"] == 52.0


def test_mecz_bez_prawdopodobienstw_WYPADA(): 
    """Sedno: brak liczb ma znaczyc BRAK KUPONU, nie kupon z domyslnych 40/25/35."""
    wynik = na_ksztalt_pred_ml([_mecz(pw=None, pr=None, pp=None)])

    assert wynik == [], (
        "mecz bez prob modelu przeszedl dalej — `build_tips` podstawi 40/25/35 "
        "i powstanie kupon ze zmyslonych liczb, na publicznym leaderboardzie"
    )


@pytest.mark.parametrize("brak", ["pw", "pr", "pp"])
def test_brak_pojedynczej_nogi_1x2_tez_wypada(brak):
    wynik = na_ksztalt_pred_ml([_mecz(**{brak: None})])

    assert wynik == []


def test_zera_to_tez_brak_danych():
    """quick_picks oddaje 0.0 dla meczu spoza pokrycia — to nie jest 'remis 0%'."""
    assert na_ksztalt_pred_ml([_mecz(pw=0.0, pr=0.0, pp=0.0)]) == []


def test_kursy_i_opis_meczu_przechodza():
    """Kontrola negatywna: adapter ma DOKLADAC ksztalt, nie gubic reszty."""
    wynik = na_ksztalt_pred_ml([_mecz()])

    assert wynik[0]["odds"]["home"] == 1.85
    assert wynik[0]["liga"] == "Premier League"
    assert wynik[0]["gospodarz"] == "Arsenal"


def test_brak_btts_i_over_nie_blokuje_meczu():
    """1X2 wystarczy — rynki totali sa opcjonalne i `build_tips` je pominie."""
    wynik = na_ksztalt_pred_ml([_mecz(bt=None, o25=None)])

    assert len(wynik) == 1
    assert "prob_over_25" not in wynik[0]["pred_ml"]
    assert "prob_btts_yes" not in wynik[0]["pred_ml"]


# ── podpiecie do cloud_draft ────────────────────────────────────────────────
#
# `generate_system_coupons` zylo tylko w LOKALNYM drafcie, wylaczonym przy
# migracji do Cloud Run — stad zero wierszy `risk_*` w calej historii.

def test_cloud_draft_tworzy_propozycje_ryzyka(monkeypatch):
    import footstats.core.cloud_draft as cd
    import footstats.core.system_coupons as sc
    import footstats.core.system_paper as sp

    widziane = {}
    monkeypatch.setattr(sp, "build_single_leg_coupons", lambda w: 1)
    monkeypatch.setattr(sc, "generate_system_coupons",
                        lambda pred, date_str=None: widziane.setdefault("pred", pred) or [7])
    monkeypatch.setattr(cd, "_swiezosc_danych_system", lambda: {})
    monkeypatch.setattr(cd, "_wykryj_model_source", lambda: "poisson-dc")

    cd._zapisz_kupony_system([_mecz()])

    assert "pred" in widziane, "cloud_draft nie wola generate_system_coupons"
    assert widziane["pred"][0]["pred_ml"]["prob_home_win"] == 55.0, (
        "propozycje karmione surowym wynikiem zamiast przetlumaczonym — "
        "`build_tips` podstawi domyslne 40/25/35"
    )


def test_awaria_propozycji_nie_zabija_paper_tradingu(monkeypatch):
    """Kontrola negatywna: `risk_*` to dodatek. Paper singles sa GLOWNYM produktem
    i zbieraja dane walidacyjne — ich zapis nie moze zalezec od tej sciezki."""
    import footstats.core.cloud_draft as cd
    import footstats.core.system_coupons as sc
    import footstats.core.system_paper as sp

    monkeypatch.setattr(sp, "build_single_leg_coupons", lambda w: 3)

    def _wybuch(*a, **k):
        raise RuntimeError("konto System niedostepne")

    monkeypatch.setattr(sc, "generate_system_coupons", _wybuch)
    monkeypatch.setattr(cd, "_swiezosc_danych_system", lambda: {})

    created, risk = cd._zapisz_kupony_system([_mecz()])

    assert created == 3
    assert risk == 0


# ── INTEGRACJA: caly przeplyw, zero atrap ───────────────────────────────────
#
# ZMIERZONE NA PRODUKCJI 02.09, pierwszy draft po podpieciu:
#
#     Propozycje ryzyka (risk_*) nie powstaly (KeyError: 'id')
#     cron_draft: {'candidates': 48, 'created': 31, 'risk_created': 0}
#
# Adapter tlumaczyl `pred_ml`, ale `build_tips` czyta TAKZE `m["id"]`, `m["gosp"]`
# i `m["gosc"]` — nazwy z API Bzzoiro, ktorych `quick_picks` nie ma (`gospodarz`,
# `goscie`, brak id). Testy adaptera sprawdzaly KSZTALT jego wyjscia, a test
# podpiecia zaslepial konsumenta — wiec zaden nie przepuscil danych przez
# `build_daily_proposals`. Ten to robi.

def test_caly_przeplyw_produkuje_propozycje():
    from footstats.core.risk_proposals import build_daily_proposals

    gotowe = na_ksztalt_pred_ml([_mecz(), _mecz(gospodarz="Liverpool", goscie="Everton")])
    propozycje = build_daily_proposals(gotowe)

    assert any(p["legs"] for p in propozycje.values()), (
        f"zaden koszyk nie dostal nogi: { {k: len(v['legs']) for k, v in propozycje.items()} }"
    )


def test_przeplyw_nie_gubi_nazw_druzyn():
    """`build_tips` czyta `gosp`/`gosc`, nie `gospodarz`/`goscie`."""
    from footstats.core.risk_proposals import build_daily_proposals

    propozycje = build_daily_proposals(na_ksztalt_pred_ml([_mecz()]))
    nogi = [l for p in propozycje.values() for l in p["legs"]]

    assert nogi, "brak nog"
    assert nogi[0]["home"] == "Arsenal"
    assert nogi[0]["away"] == "Chelsea"


def test_kazdy_mecz_ma_wlasne_id():
    """`match_id` trafia do nogi — dwa mecze nie moga dzielic identyfikatora."""
    gotowe = na_ksztalt_pred_ml([
        _mecz(),
        _mecz(gospodarz="Liverpool", goscie="Everton"),
    ])

    assert gotowe[0]["id"] != gotowe[1]["id"]


def test_id_jest_deterministyczne():
    """Ten sam mecz tego samego dnia = ten sam id (idempotencja zapisu)."""
    a = na_ksztalt_pred_ml([_mecz()])[0]["id"]
    b = na_ksztalt_pred_ml([_mecz()])[0]["id"]

    assert a == b
