"""Caly lancuch team-news od kandydata do UPDATE-u w model_log.

Kazda z czterech blokad z 07.09.2026 przechodzila testy jednostkowe swojego
kawalka i mimo to kanal byl martwy end-to-end:

  1. `zapisz_partie` bieglo PRZED policzeniem pol (kolumny byly w INSERT-cie
     i pilnowal ich osobny plik testow);
  2. `player_stats` nie istnialo w kontenerze (`no such table`), wiec
     `_policz_edge_absencji` wychodzil na `continue`;
  3. `rynek_p_over` stalo POD tym `continue`;
  4. FotMob pytany byl tylko o dzisiaj, przy oknie kandydatow 72h.

Ten test idzie ta sama sciezka co `daily_agent.main()` i sprawdza SKUTEK:
czy do bazy realnie trafiaja liczby. Wariant `bez_bazy` odtwarza kontener —
`player_db._connect` pada, wiec jedynym zrodlem goli jest zrzut z obrazu.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from footstats.core import daily_phases as dp
from footstats.core import kalibracja_log as kl
from footstats.core import player_db as pdb
from footstats.scrapers.teamnews.base import Absencja, TeamNews
from tests.test_model_log_absencje import _Conn  # noqa: F401

# Druzyna obecna w `data/player_stats.json` — bez niej udzialy golowe wyjda
# puste i lancuch urwie sie na bramce, dokladnie jak w kontenerze przed naprawa.
DRUZYNA = "Juventus"
STRZELEC = "Kenan Yildiz"


@pytest.fixture
def baza(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)
    return conn


def _kandydat() -> dict:
    return {
        "gospodarz": DRUZYNA, "goscie": "Napoli", "data": date.today().isoformat(),
        "liga": "ITA-Serie A",
        "pw": 45.0, "pr": 27.0, "pp": 28.0, "o25": 52.0, "bt": 51.0,
        "lambda_h": 1.55, "lambda_a": 1.20,
        "market_p_over": 0.503,
    }


def _team_news() -> TeamNews:
    return TeamNews(
        source="fotmob", home=DRUZYNA, away="Napoli",
        date=date.today().isoformat(), typ_skladu="predicted",
        absencje_home=(Absencja(nazwisko=STRZELEC, typ="injury",
                                powrot="Mid September 2026", pewna=True,
                                pozycja="F"),),
        absencje_away=(),
    )


def _wartosci_updatu(conn) -> dict:
    aktualizacje = [z for z in conn.zapytania if z[0].upper().startswith("UPDATE")]
    assert aktualizacje, "nie bylo UPDATE-u — pola team-news nie doszly do bazy"
    sql, params = aktualizacje[0]
    kolumny = [c.split("=")[0].strip() for c in
               sql.split("SET", 1)[1].split("WHERE", 1)[0].split(",")]
    return dict(zip(kolumny, params))


@pytest.mark.parametrize("bez_bazy", [False, True], ids=["z_baza", "bez_bazy"])
def test_lancuch_konczy_sie_liczbami_w_bazie(baza, monkeypatch, bez_bazy):
    monkeypatch.setenv(dp.FLAGA_TEAM_NEWS, "1")
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda d, pary: [_team_news()])
    pdb._zrzut_goli.cache_clear()

    if bez_bazy:
        # Kontener: `data/footstats_backtest.db` nie istnieje, sqlite3 tworzy
        # pusty plik, pierwszy odczyt konczy sie `no such table: player_stats`.
        def _pada(*a, **kw):
            raise sqlite3.OperationalError("no such table: player_stats")
        monkeypatch.setattr(pdb, "_connect", _pada)

    kandydaci = [_kandydat()]

    # DOKLADNIE ta kolejnosc co `daily_agent.main()`.
    kl.zapisz_partie(kandydaci, zrodlo="final")
    dp._wzbogac_team_news(kandydaci)
    assert kl.uzupelnij_team_news(kandydaci) == 1

    wartosci = _wartosci_updatu(baza)
    for kolumna in ("p_over_abs", "edge_absencje", "rynek_p_over",
                    "absencje_pewne_home"):
        assert kolumna in wartosci, f"{kolumna} nie doszlo do UPDATE-u"
        assert wartosci[kolumna] is not None, f"{kolumna} jest NULL-em"

    assert wartosci["absencje_pewne_home"] == 1
    assert wartosci["rynek_p_over"] == pytest.approx(0.503)
    # Brak strzelca musi OBNIZYC oczekiwane gole, wiec Over 2.5 po korekcie
    # jest nizsze niz przed nia.
    assert 0.0 < wartosci["p_over_abs"] < 0.52
    pdb._zrzut_goli.cache_clear()


def test_bez_zrzutu_i_bez_bazy_zostaje_sama_cena(baza, monkeypatch, tmp_path):
    """Degradacja ma byc stopniowa: przewagi nie policzymy, ale cene zapiszemy.

    To jest wartosc naprawy #3 — cena z tamtej chwili nie zalezy od udzialow
    golowych, a bez niej nie da sie pozniej orzec, kto mial racje.
    """
    monkeypatch.setenv(dp.FLAGA_TEAM_NEWS, "1")
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda d, pary: [_team_news()])

    def _pada(*a, **kw):
        raise sqlite3.OperationalError("no such table: player_stats")
    monkeypatch.setattr(pdb, "_connect", _pada)
    monkeypatch.setattr(pdb, "SCIEZKA_ZRZUTU", tmp_path / "nie_ma.json")
    pdb._zrzut_goli.cache_clear()

    kandydaci = [_kandydat()]
    kl.zapisz_partie(kandydaci, zrodlo="final")
    dp._wzbogac_team_news(kandydaci)
    assert kl.uzupelnij_team_news(kandydaci) == 1

    wartosci = _wartosci_updatu(baza)
    assert wartosci["rynek_p_over"] == pytest.approx(0.503)
    assert wartosci["absencje_pewne_home"] == 1
    assert "p_over_abs" not in wartosci, "bez udzialow przewagi liczyc NIE WOLNO"
    pdb._zrzut_goli.cache_clear()


def test_kolejnosc_odwrotna_daje_puste_kolumny(baza, monkeypatch):
    """Regresja na blokade #1 — dowod, ze kolejnosc jest tu wszystkim.

    Gdy `zapisz_partie` idzie PO wzbogaceniu, INSERT ma komplet i UPDATE nie ma
    czego robic. Gdy idzie PRZED (jak w produkcji) — bez `uzupelnij_team_news`
    kolumny zostaja NULL-em. To byl stan produkcji do 07.09.2026.
    """
    monkeypatch.setenv(dp.FLAGA_TEAM_NEWS, "1")
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda d, pary: [_team_news()])
    pdb._zrzut_goli.cache_clear()

    kandydaci = [_kandydat()]
    kl.zapisz_partie(kandydaci, zrodlo="final")
    dp._wzbogac_team_news(kandydaci)
    # ... i NIE wolamy `uzupelnij_team_news`.

    sql, params = baza.insert()
    kolumny = [k.strip() for k in sql.split("(", 1)[1].split(")", 1)[0].split(",")]
    wartosci = dict(zip(kolumny, params))
    assert wartosci["p_over_abs"] is None
    assert wartosci["rynek_p_over"] is None
    pdb._zrzut_goli.cache_clear()
