"""Pelne kadry z `/players`, bo `/players/topscorers` daje mianownik nie do uzycia.

STAN ZASTANY (2026-09-07). `goal_share` = gole gracza / suma goli graczy
ZAPISANYCH, wiec jest tak dobry jak kompletnosc tabeli. Jedyne zrodlo, ktore
dawalo pelne sklady (Understat), jest martwe — `GET understat.com/league/EPL/2026`
oddaje HTTP 200 i 4684 bajty bez `playersData`, to samo na 2025. Zostal
`/players/topscorers`, ktory oddaje **20 nazwisk na CALA lige**, czyli 1-4 na
druzyne. Zmierzone w `data/player_stats.json`:

    sezon  druzyn  min  p25  mediana  p75  max
     2024     212    1    1        2   13   29    topscorers + resztki
     2025      95    9   13       15   17   30    pelne sklady (Understat)
     2026      53    1    1        1    2    4    topscorers

Skutkiem byl `goal_share` 100% dla 62% druzyn z realnego ruchu (naprawione
progiem `MIN_SKLAD`), a po naprawie — brak wagi dla wiekszosci absencji:
log produkcji `udzialy absencji 3/24 dopasowane w player_db`.

`/players?league=&season=&page=` oddaje CALA lige stronami po 20. Zmierzone na
Premier League 2025: 34 strony, ~680 graczy. Przy 16 ligach to okolo 550 zapytan
wobec 7500/dzien na planie Pro — koszt jest do zaplacenia, w odroznieniu od
FotMoba, ktory wymagalby zapytania na KAZDEGO gracza.

DLACZEGO SEZON POPRZEDNI, NIE BIEZACY. `core/absencje.py` mowi to wprost:
"Premier League po dwoch kolejkach dala 5 goli na dwie kadry, wiec udzial
jednego strzelca wyszedlby 0,4". Sprawdzone tego dnia na FotMobie: kadra
Liverpoolu ma 29 osob i **6 goli lacznie**. Wagi biora sie z ostatniego pelnego
sezonu, a `team_goal_shares_recent` cofa sie tam sama.
"""
from __future__ import annotations

import pytest

from footstats.scrapers.player_stats import parse_players_page, fetch_league_squad


def _gracz(nazwa, druzyna, gole=3, asysty=1, minuty=900):
    return {
        "player": {"name": nazwa},
        "statistics": [{
            "team": {"name": druzyna},
            "goals": {"total": gole, "assists": asysty},
            "games": {"minutes": minuty},
        }],
    }


def _strona(gracze, current=1, total=1):
    return {"response": gracze, "paging": {"current": current, "total": total}}


# ── parse_players_page ──────────────────────────────────────────────────────

def test_parsuje_gracza():
    [w] = parse_players_page(_strona([_gracz("M. Salah", "Liverpool", 20, 8, 3000)]))
    assert w == {"name": "M. Salah", "team": "Liverpool",
                 "goals": 20, "assists": 8, "minutes": 3000}


def test_zero_goli_TEZ_wchodzi_do_kadry():
    """Rdzen roznicy wobec topscorers: mianownik ma byc pelny.

    Bramkarz z zerem goli nie zmienia sumy, ale jego obecnosc jest dowodem, ze
    tabela zawiera SKLAD, a nie czolowke strzelcow — i to na tym stoi prog
    `player_db.MIN_SKLAD`.
    """
    wiersze = parse_players_page(_strona([
        _gracz("Alisson", "Liverpool", 0, 0, 3000),
        _gracz("M. Salah", "Liverpool", 20, 8, 3000),
    ]))
    assert len(wiersze) == 2
    assert {w["name"] for w in wiersze} == {"Alisson", "M. Salah"}


@pytest.mark.parametrize("brak", [
    {"player": {"name": ""}, "statistics": [{"team": {"name": "X"}}]},
    {"player": {"name": "A"}, "statistics": []},
    {"player": {"name": "A"}, "statistics": [{"team": {"name": ""}}]},
])
def test_wpis_bez_nazwiska_albo_druzyny_odpada(brak):
    assert parse_players_page(_strona([brak])) == []


def test_None_i_braki_nie_wybuchaja():
    assert parse_players_page(None) == []
    assert parse_players_page({}) == []
    assert parse_players_page({"response": None}) == []
    [w] = parse_players_page(_strona([{
        "player": {"name": "A"},
        "statistics": [{"team": {"name": "T"}, "goals": None, "games": None}],
    }]))
    assert w["goals"] == 0 and w["minutes"] == 0


def test_gracz_po_transferze_ma_wiele_wpisow_statystyk():
    """API oddaje `statistics` per klub. Bierzemy KAZDY, bo `goal_share` jest
    liczony per druzyna — gole strzelone w innym klubie nie moga tam trafic."""
    wpis = {
        "player": {"name": "J. Doe"},
        "statistics": [
            {"team": {"name": "Klub A"}, "goals": {"total": 5, "assists": 1},
             "games": {"minutes": 900}},
            {"team": {"name": "Klub B"}, "goals": {"total": 2, "assists": 0},
             "games": {"minutes": 400}},
        ],
    }
    wiersze = parse_players_page(_strona([wpis]))
    assert {(w["team"], w["goals"]) for w in wiersze} == {("Klub A", 5), ("Klub B", 2)}


# ── fetch_league_squad (paginacja) ──────────────────────────────────────────

class _Klient:
    def __init__(self, strony):
        self.strony = strony
        self.zapytania = []

    def _get(self, sciezka, params=None):
        self.zapytania.append(dict(params or {}))
        nr = (params or {}).get("page", 1)
        return self.strony.get(nr)


def test_przechodzi_wszystkie_strony(monkeypatch):
    strony = {
        1: _strona([_gracz("A", "T")], 1, 3),
        2: _strona([_gracz("B", "T")], 2, 3),
        3: _strona([_gracz("C", "T")], 3, 3),
    }
    klient = _Klient(strony)
    wiersze = fetch_league_squad(39, 2025, "klucz", _klient=klient)

    assert {w["name"] for w in wiersze} == {"A", "B", "C"}
    assert [z["page"] for z in klient.zapytania] == [1, 2, 3]


def test_pusta_pierwsza_strona_konczy_bez_dalszych_zapytan():
    klient = _Klient({1: {"response": [], "paging": {"current": 1, "total": 7}}})
    assert fetch_league_squad(39, 2025, "klucz", _klient=klient) == []
    assert len(klient.zapytania) == 1


def test_dziura_w_srodku_nie_ucina_reszty():
    """Jedna strona bez odpowiedzi to nie koniec ligi — pomijamy ja i lecimy dalej.

    Przerwanie na pierwszej dziurze dawaloby CICHO obcieta kadre, czyli dokladnie
    ten zafalszowany mianownik, ktory ta zmiana usuwa.
    """
    klient = _Klient({
        1: _strona([_gracz("A", "T")], 1, 3),
        2: None,
        3: _strona([_gracz("C", "T")], 3, 3),
    })
    wiersze = fetch_league_squad(39, 2025, "klucz", _klient=klient)
    assert {w["name"] for w in wiersze} == {"A", "C"}


def test_limit_stron_chroni_przed_petla():
    """`paging.total` pochodzi z zewnatrz — absurdalna wartosc nie moze zjesc budzetu."""
    klient = _Klient({n: _strona([_gracz(f"G{n}", "T")], n, 10_000) for n in range(1, 200)})
    fetch_league_squad(39, 2025, "klucz", _klient=klient, max_stron=5)
    assert len(klient.zapytania) == 5


def test_bez_klucza_nie_wychodzi_do_sieci():
    assert fetch_league_squad(39, 2025, "") == []
