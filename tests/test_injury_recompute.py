"""
test_injury_recompute.py — FAZA λ: kontuzje przeliczają prawdopodobieństwa kandydata.
Football logic: brak napastnika → mniej strzelamy; brak obrońcy → rywal strzela więcej.
"""
from footstats.daily_agent import _apply_injury_corrections

_BASE = {"gospodarz": "A", "goscie": "B", "pw": 45.0, "pr": 27.0, "pp": 28.0, "o25": 55.0, "bt": 52.0}


def test_gospodarz_traci_napastnikow_pw_spada():
    w = dict(_BASE, injuries_home=[{"position": "F"}, {"position": "F"}], injuries_away=[])
    _apply_injury_corrections([w])
    assert w["pw"] < _BASE["pw"]
    assert w["pp"] > _BASE["pp"]


def test_gosc_traci_obroncow_gospodarz_strzela_wiecej():
    w = dict(_BASE, injuries_home=[], injuries_away=[{"position": "D"}, {"position": "D"}])
    _apply_injury_corrections([w])
    assert w["pw"] > _BASE["pw"]
    assert w["o25"] > _BASE["o25"]


def test_brak_kontuzji_bez_zmian():
    w = dict(_BASE)
    _apply_injury_corrections([w])
    assert w["pw"] == _BASE["pw"]
    assert w["o25"] == _BASE["o25"]


def test_brak_pol_injuries_nie_wywala():
    # kandydat bez kluczy injuries_* — nie powinno rzucić
    w = dict(_BASE)
    w.pop("injuries_home", None)
    _apply_injury_corrections([w])
    assert w["pw"] == _BASE["pw"]


def test_prawdopodobienstwa_pozostaja_sensowne():
    w = dict(_BASE, injuries_home=[{"position": "F"}], injuries_away=[{"position": "D"}])
    _apply_injury_corrections([w])
    # 1X2 nadal sumuje ~100%
    assert abs((w["pw"] + w["pr"] + w["pp"]) - 100.0) < 1.0
    assert 0 <= w["o25"] <= 100
