"""
test_match_analysis.py — rdzeń zakładki Analizy meczowe: agregacja karty meczu
(gole/mecz, kontuzje z goal_share, model, gospodarz) + prompt LLM + data-hash do
cache (regen tylko gdy dane się zmienią, nie na każdy request).
"""
from footstats.core.match_analysis import build_match_card, analysis_prompt, card_data_hash

_MATCH = {"gospodarz": "France", "goscie": "Egypt", "liga": "World Cup 2026",
          "data": "2026-07-08", "pw": 56.0, "pr": 24.0, "pp": 20.0, "o25": 54.0, "bt": 54.0}
_TS_H = {"matches": 3, "goals_for": 10, "goals_against": 2, "avg_rating": 7.16, "clean_sheets": 3}
_TS_A = {"matches": 3, "goals_for": 5, "goals_against": 6, "avg_rating": 6.9, "clean_sheets": 0}


def test_card_structure():
    c = build_match_card(_MATCH, ts_home=_TS_H, ts_away=_TS_A)
    assert c["home"] == "France" and c["away"] == "Egypt"
    assert c["host"] == "France"                    # gospodarz = host
    assert c["liga"] == "World Cup 2026"
    assert c["model"]["pw"] == 56.0
    assert abs(c["home_stats"]["gf_pg"] - 10 / 3) < 0.01   # gole/mecz (round 2)
    assert abs(c["home_stats"]["ga_pg"] - 2 / 3) < 0.01
    assert c["home_stats"]["rating"] == 7.16


def test_injuries_z_goal_share():
    c = build_match_card(
        _MATCH, ts_home=_TS_H, ts_away=_TS_A,
        gs_home={"Mbappé": 0.54}, inj_home=[{"name": "Mbappé", "position": "F"}],
    )
    inj = c["injuries_home"][0]
    assert inj["name"] == "Mbappé"
    assert abs(inj["goal_share"] - 0.54) < 1e-6
    assert inj["position"] == "F"


def test_brak_danych_none_nie_wywala():
    c = build_match_card(_MATCH)          # bez team_stats/kontuzji
    assert c["home_stats"]["gf_pg"] is None
    assert c["injuries_home"] == []


def test_prompt_zawiera_dane():
    c = build_match_card(_MATCH, ts_home=_TS_H, ts_away=_TS_A)
    p = analysis_prompt(c)
    assert "France" in p and "Egypt" in p
    assert "NIE wybierasz" in p or "nie wybieraj" in p.lower()  # rola: analiza nie pick


def test_data_hash_stabilny_i_zmienny():
    c1 = build_match_card(_MATCH, ts_home=_TS_H)
    c2 = build_match_card(_MATCH, ts_home=_TS_H)
    assert card_data_hash(c1) == card_data_hash(c2)        # te same dane → ten sam hash
    c3 = build_match_card(_MATCH, ts_home=_TS_H, inj_home=[{"name": "X", "position": "F"}])
    assert card_data_hash(c3) != card_data_hash(c1)        # nowa kontuzja → inny hash (regen)
