"""test_elo_signal_draft.py — ClubElo jako sygnał porównawczy obok draftu.

ClubElo jest estymatorem ORTOGONALNYM: liczy siłę drużyn (Elo), podczas gdy nasze
λ liczy historię goli. Rozjazd między nimi to powód, żeby przyjrzeć się meczowi.

Kluczowe: ten sygnał NIE MOŻE wpływać na selekcję ani na λ — zmiana modelu jest
model-critical i wymaga walk-forward. Testy pilnują, że to zostaje sygnałem obok.
"""
from __future__ import annotations

from unittest.mock import patch

import footstats.core.cloud_draft as cd

_FIXTURES_ELO = [
    {"data": "2026-08-21", "liga": "ENG", "gospodarz": "Arsenal", "goscie": "Chelsea",
     "prob": {"pw": 55.0, "pr": 25.0, "pp": 20.0, "bt": 48.0, "o25": 61.0}},
]


def _nogi():
    return [
        {"mecz": "Arsenal vs Chelsea", "tip": "1", "kurs": 1.8, "prob": 58.0},
        {"mecz": "Nieznany FC vs Inny FC", "tip": "1", "kurs": 2.0, "prob": 51.0},
    ]


def test_dopisuje_prognoze_elo_do_znanego_meczu():
    nogi = _nogi()
    with patch("footstats.scrapers.clubelo.pobierz_fixtures", return_value=_FIXTURES_ELO):
        trafien = cd._dolacz_sygnal_elo(nogi)

    assert trafien == 1
    assert nogi[0]["elo"]["pw"] == 55.0
    assert nogi[0]["elo_zgoda"] is True   # 55% >= próg 33% dla 1X2


def test_mecz_nieznany_elo_zostaje_bez_pola():
    """Brak pokrycia to nie błąd — ClubElo zna głównie kluby europejskie."""
    nogi = _nogi()
    with patch("footstats.scrapers.clubelo.pobierz_fixtures", return_value=_FIXTURES_ELO):
        cd._dolacz_sygnal_elo(nogi)
    assert "elo" not in nogi[1]


def test_rozjazd_oznaczony_brakiem_zgody():
    """Typ '2' przy 20% od ClubElo → elo_zgoda False, czyli sygnał ostrzegawczy."""
    nogi = [{"mecz": "Arsenal vs Chelsea", "tip": "2", "kurs": 4.0, "prob": 52.0}]
    with patch("footstats.scrapers.clubelo.pobierz_fixtures", return_value=_FIXTURES_ELO):
        cd._dolacz_sygnal_elo(nogi)
    assert nogi[0]["elo_zgoda"] is False


def test_nie_zmienia_typu_ani_prob():
    """SEDNO: sygnał jest OBOK modelu. Nie wolno mu dotknąć tip/prob/kurs."""
    nogi = _nogi()
    przed = [(n["tip"], n["prob"], n["kurs"]) for n in nogi]
    with patch("footstats.scrapers.clubelo.pobierz_fixtures", return_value=_FIXTURES_ELO):
        cd._dolacz_sygnal_elo(nogi)
    assert [(n["tip"], n["prob"], n["kurs"]) for n in nogi] == przed


def test_awaria_clubelo_nie_wywala_draftu():
    nogi = _nogi()
    with patch("footstats.scrapers.clubelo.pobierz_fixtures", side_effect=OSError("timeout")):
        assert cd._dolacz_sygnal_elo(nogi) == 0
    assert "elo" not in nogi[0]


def test_pusta_lista_nog_nie_pyta_api():
    with patch("footstats.scrapers.clubelo.pobierz_fixtures") as mock:
        assert cd._dolacz_sygnal_elo([]) == 0
    mock.assert_not_called()


def test_brak_danych_z_elo_jest_graceful():
    nogi = _nogi()
    with patch("footstats.scrapers.clubelo.pobierz_fixtures", return_value=[]):
        assert cd._dolacz_sygnal_elo(nogi) == 0
