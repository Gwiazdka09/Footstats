"""
test_match_analysis.py — rdzeń zakładki Analizy meczowe: agregacja karty meczu
(gole/mecz, kontuzje z goal_share, model, gospodarz) + prompt LLM + data-hash do
cache (regen tylko gdy dane się zmienią, nie na każdy request).
"""
from footstats.core.match_analysis import (
    build_match_card, analysis_prompt, card_data_hash,
    get_cached_analysis, set_cached_analysis,
)

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


def test_top_scorers_top3_wg_share():
    c = build_match_card(
        _MATCH, gs_home={"A": 0.5, "B": 0.3, "C": 0.1, "D": 0.05})
    ts = c["top_scorers_home"]
    assert [s["name"] for s in ts] == ["A", "B", "C"]     # top 3, sort malejąco
    assert ts[0]["goal_share"] == 0.5
    assert c["top_scorers_away"] == []                    # brak danych


def test_prompt_zawiera_top_scorers():
    c = build_match_card(_MATCH, gs_home={"Mbappé": 0.54})
    assert "Mbappé" in analysis_prompt(c)


def test_cache_persist(tmp_path):
    db = tmp_path / "t.db"
    assert get_cached_analysis("h1", db_path=db) is None   # miss
    set_cached_analysis("h1", "analiza X", db_path=db)
    assert get_cached_analysis("h1", db_path=db) == "analiza X"
    set_cached_analysis("h1", "analiza Y", db_path=db)      # upsert
    assert get_cached_analysis("h1", db_path=db) == "analiza Y"


def test_data_hash_stabilny_i_zmienny():
    c1 = build_match_card(_MATCH, ts_home=_TS_H)
    c2 = build_match_card(_MATCH, ts_home=_TS_H)
    assert card_data_hash(c1) == card_data_hash(c2)        # te same dane → ten sam hash
    c3 = build_match_card(_MATCH, ts_home=_TS_H, inj_home=[{"name": "X", "position": "F"}])
    assert card_data_hash(c3) != card_data_hash(c1)        # nowa kontuzja → inny hash (regen)


# ── Duplikaty strzelców (25.10): ta sama osoba pod dwiema pisowniami ──────────

def test_top_scorers_dedup_diakrytyki():
    from footstats.core.match_analysis import _top_scorers
    gs = {"Ferrán Torres": 0.14, "Ferran Torres": 0.14, "Lewandowski": 0.30}
    nazwy = [s["name"] for s in _top_scorers(gs)]
    assert len(nazwy) == 2 and "Lewandowski" in nazwy
    assert sum("Torres" in n for n in nazwy) == 1


def test_top_scorers_dedup_czlon_nazwiska_zostawia_wyzszy_udzial():
    from footstats.core.match_analysis import _top_scorers
    gs = {"Kylian Mbappe-Lottin": 0.23, "Kylian Mbappé": 0.25, "Rodrygo": 0.10}
    top = _top_scorers(gs)
    assert [s["name"] for s in top] == ["Kylian Mbappé", "Rodrygo"]


def test_top_scorers_dedup_nie_laczy_roznych_osob():
    from footstats.core.match_analysis import _top_scorers
    gs = {"Jose Silva": 0.2, "Joao Silva": 0.15, "Bernardo Silva": 0.1}
    assert len(_top_scorers(gs)) == 3


def test_top_scorers_dedup_przed_obcieciem_do_n():
    from footstats.core.match_analysis import _top_scorers
    gs = {"A Torres": 0.3, "A Torrés": 0.29, "B One": 0.2, "C Two": 0.1}
    assert [s["name"] for s in _top_scorers(gs, n=3)] == ["A Torres", "B One", "C Two"]


def test_top_scorers_dedup_zdrobnienie_imienia_ten_sam_udzial():
    from footstats.core.match_analysis import _top_scorers
    gs = {"Antonio Martínez": 0.25, "Toni Martínez": 0.25, "Oyarzabal": 0.10}
    nazwy = [s["name"] for s in _top_scorers(gs)]
    assert len(nazwy) == 2 and sum("Mart" in n for n in nazwy) == 1


def test_top_scorers_dedup_to_samo_nazwisko_inny_udzial_zostaje():
    from footstats.core.match_analysis import _top_scorers
    gs = {"Antonio Martinez": 0.25, "Toni Martinez": 0.10}
    assert len(_top_scorers(gs)) == 2
