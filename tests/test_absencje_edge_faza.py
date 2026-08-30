"""Absencje z FotMoba -> skorygowana lambda i P(Over) w fazie enrichmentu.

DECYZJA, ktora ten plik utrwala: liczymy i ZAPISUJEMY OBOK, nie nadpisujemy
pw/pr/pp/o25/bt. Powod jest zmierzony, nie ostrozniosciowy — 14.08 na n=15460
zaden z 52 podzbiorow nie przezyl holdoutu, a historii kontuzji nie ma ani
u nas, ani u FotMoba, wiec tej korekty NIE DA SIE zwalidowac walk-forwardem.
Nadpisanie typow produkcyjnych niezwalidowana poprawka byloby powtorzeniem
bledu, ktory ten projekt juz raz zmierzyl.

Zapis obok daje liczbe, ktora za kilkadziesiat mieczow pozwoli porownac.
"""
from __future__ import annotations

import logging

import pytest

from footstats.core import daily_phases as dp
from footstats.scrapers.teamnews.base import Absencja, TeamNews

_UDZIALY = {"Cole Palmer": 0.175, "Enzo Fernández": 0.175, "João Pedro": 0.263}


def _tn(pewne_home=("Cole Palmer",), pewne_away=()):
    return TeamNews(
        source="fotmob", home="Chelsea", away="Brighton", date="2026-08-30",
        typ_skladu="predicted",
        xi_home=tuple(f"G{i}" for i in range(11)),
        xi_away=tuple(f"A{i}" for i in range(11)),
        absencje_home=tuple(Absencja(n, "injury", "Mid September 2026", True)
                            for n in pewne_home),
        absencje_away=tuple(Absencja(n, "injury", "Mid September 2026", True)
                            for n in pewne_away),
        sedzia="Michael Oliver", sedzia_stats={"n_matches": 54},
    )


@pytest.fixture
def kandydat():
    return {"gospodarz": "Chelsea", "goscie": "Brighton",
            "lambda_h": 1.6, "lambda_a": 1.2,
            "pw": 45.0, "pr": 27.0, "pp": 28.0, "o25": 52.0, "bt": 51.0}


@pytest.fixture(autouse=True)
def _wlacz_flage_i_udzialy(monkeypatch):
    monkeypatch.setenv(dp.FLAGA_TEAM_NEWS, "1")
    monkeypatch.setattr(dp, "_goal_shares_for", lambda team, side=None: dict(_UDZIALY))


def test_absencja_topowego_strzelca_obniza_lambde(monkeypatch, kandydat):
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [_tn()])

    dp._wzbogac_team_news([kandydat])

    assert kandydat["lambda_h_abs"] < kandydat["lambda_h"], (
        "brak strzelca z udzialem 0.175 musi obnizyc lambde gospodarza"
    )
    assert kandydat["lambda_a_abs"] == kandydat["lambda_a"], (
        "gosc nie ma absencji — jego lambda ma zostac nietknieta"
    )


def test_MODEL_produkcyjny_zostaje_nietkniety(monkeypatch, kandydat):
    """Sedno decyzji: korekta jest niezwalidowana, wiec nie wchodzi do typow."""
    przed = {k: kandydat[k] for k in ("pw", "pr", "pp", "o25", "bt",
                                      "lambda_h", "lambda_a")}
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [_tn()])

    dp._wzbogac_team_news([kandydat])

    for k, v in przed.items():
        assert kandydat[k] == v, f"pole {k} zostalo nadpisane niezwalidowana korekta"


def test_brak_pewnych_absencji_nie_liczy_nic(monkeypatch, kandydat):
    """Same watpliwe ("Doubtful") nie moga ruszac lambdy."""
    tn = TeamNews(
        source="fotmob", home="Chelsea", away="Brighton", date="2026-08-30",
        typ_skladu="predicted",
        absencje_home=(Absencja("Cole Palmer", "injury", "Doubtful", False),),
    )
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [tn])

    dp._wzbogac_team_news([kandydat])
    assert "lambda_h_abs" not in kandydat


def test_nieznany_gracz_nie_udaje_zerowej_straty(monkeypatch, caplog, kandydat):
    """Gracz spoza player_db to "nie wiem", nie "nie strzela". Musi byc widoczny
    w liczniku, bo to miara zdrowia polaczenia dwoch zrodel."""
    monkeypatch.setattr(dp, "_pobierz_team_news",
                        lambda data, pary: [_tn(pewne_home=("Ktos Nieznany",))])

    with caplog.at_level(logging.INFO):
        dp._wzbogac_team_news([kandydat])

    assert kandydat.get("absencje_bez_udzialu") == 1
    assert "lambda_h_abs" not in kandydat, "brak znanego udzialu = brak korekty"


def test_licznik_dopasowan_trafia_do_logu(monkeypatch, caplog, kandydat):
    monkeypatch.setattr(
        dp, "_pobierz_team_news",
        lambda data, pary: [_tn(pewne_home=("Cole Palmer", "Ktos Nieznany"))])

    with caplog.at_level(logging.INFO):
        dp._wzbogac_team_news([kandydat])

    assert "udzialy absencji" in caplog.text
    assert "1/2" in caplog.text


def test_edge_liczony_gdy_jest_kurs_rynku(monkeypatch, kandydat):
    kandydat["market_p_over"] = 0.55
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [_tn()])

    dp._wzbogac_team_news([kandydat])

    assert kandydat["p_over_abs"] < 0.55
    assert kandydat["edge_absencje"] == pytest.approx(
        kandydat["p_over_abs"] - 0.55, abs=1e-4)


def test_bez_kursu_rynku_edge_jest_None_a_nie_zero(monkeypatch, kandydat):
    """Zero to twierdzenie "brak przewagi". Brak kursu to brak pomiaru."""
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [_tn()])

    dp._wzbogac_team_news([kandydat])

    assert kandydat["p_over_abs"] is not None
    assert kandydat["edge_absencje"] is None


def test_brak_lambdy_w_kandydacie_jest_estymowana(monkeypatch):
    """Kandydaci Bzzoiro nie zawsze niosa lambda_h/a — tak samo jak w
    _apply_injury_corrections, estymujemy z pw/pp/o25."""
    k = {"gospodarz": "Chelsea", "goscie": "Brighton",
         "pw": 45.0, "pp": 28.0, "o25": 52.0}
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [_tn()])

    dp._wzbogac_team_news([k])
    assert k.get("lambda_h_abs") is not None


def test_pole_robocze_nie_zostaje_w_kandydacie(monkeypatch, kandydat):
    """Nazwiska sa wejsciem jednego przebiegu. Zostawione, pojechalyby dalej
    potokiem i mogly wyladowac w serializacji kuponu."""
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [_tn()])

    dp._wzbogac_team_news([kandydat])

    assert not [k for k in kandydat if k.startswith("_absencje")]


# ── pozycje odblokowuja DWUSTRONNA korekte ──────────────────────────────────

def test_absencje_z_pozycja_traja_do_injuries(monkeypatch, kandydat):
    """`_apply_injury_corrections` czyta `injuries_home`/`injuries_away` i
    klasyfikuje po pozycji. Bez tego wpiecia pozycje z FotMoba leza w DTO,
    ktorego nikt nie czyta — czyli kolejny cichy no-op."""
    tn = TeamNews(
        source="fotmob", home="Chelsea", away="Brighton", date="2026-08-30",
        typ_skladu="predicted",
        absencje_home=(Absencja("Cole Palmer", "injury", "Mid September 2026",
                                True, pozycja="F"),),
        absencje_away=(Absencja("Obronca Jeden", "injury", "Mid September 2026",
                                True, pozycja="D"),),
    )
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [tn])

    dp._wzbogac_team_news([kandydat])

    assert kandydat["injuries_home"] == [{"name": "Cole Palmer", "position": "F"}]
    assert kandydat["injuries_away"] == [{"name": "Obronca Jeden", "position": "D"}]


def test_absencja_bez_pozycji_nie_wchodzi_do_injuries(monkeypatch, kandydat):
    """Bez pozycji `injury_lambda_factors` i tak zwroci (1.0, 1.0). Wpisanie jej
    tylko zaszumiloby liste i udawalo, ze cos policzylismy."""
    tn = TeamNews(
        source="fotmob", home="Chelsea", away="Brighton", date="2026-08-30",
        absencje_home=(Absencja("Ktos", "injury", "Mid September 2026", True),),
    )
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [tn])

    dp._wzbogac_team_news([kandydat])
    assert not kandydat.get("injuries_home")


def test_watpliwa_absencja_nie_wchodzi_do_injuries(monkeypatch, kandydat):
    tn = TeamNews(
        source="fotmob", home="Chelsea", away="Brighton", date="2026-08-30",
        absencje_home=(Absencja("Cole Palmer", "injury", "Doubtful", False,
                                pozycja="F"),),
    )
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [tn])

    dp._wzbogac_team_news([kandydat])
    assert not kandydat.get("injuries_home")


def test_istniejace_injuries_maja_pierwszenstwo(monkeypatch, kandydat):
    """Gdyby SofaScore kiedys wrocil, jego dane sa pelniejsze — nie nadpisujemy."""
    kandydat["injuries_home"] = [{"name": "Z SofaScore", "position": "M"}]
    tn = TeamNews(
        source="fotmob", home="Chelsea", away="Brighton", date="2026-08-30",
        absencje_home=(Absencja("Cole Palmer", "injury", "Mid September 2026",
                                True, pozycja="F"),),
    )
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda data, pary: [tn])

    dp._wzbogac_team_news([kandydat])
    assert kandydat["injuries_home"] == [{"name": "Z SofaScore", "position": "M"}]
