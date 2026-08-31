"""Sedzia to wzbogacenie, nie rdzen — nieosiagalna baza nie moze zabic przebiegu.

Zmierzone 31.08: pelna faza final odpalona bez `DATABASE_URL` przewrocila sie
na `get_referee` -> `init_referee_table()`. Traceback prowadzil w glab warstwy
bazy, a przyczyna byla plytka: kandydat mial nazwisko sedziego i chcielismy
do niego doczytac statystyki.

Skutek praktyczny: calego potoku nie dalo sie sprawdzic bez produkcji, wiec
kazda zmiana w fazie final byla weryfikowalna dopiero na zywym przebiegu
o 11:00 UTC.

Gdy baza padnie NAPRAWDE, przebieg i tak stanie — na zapisie `predictions`
i kuponu, czyli tam, gdzie brak bazy faktycznie ma znaczenie. Zatrzymywanie
go wczesniej, w odczycie statystyki sedziego, niczego nie ratuje.

DRUGA RZECZ, ktora ten plik utrwala: JEDEN odczyt na sedziego. `referee_signal`
wolalo `get_referee` po raz drugi dla tej samej nazwy — dwa round-tripy do bazy
tam, gdzie wystarczy jeden.
"""
from __future__ import annotations

import logging

import pytest

import footstats.core.daily_phases as dp
import footstats.core.lineup_strength as ls
import footstats.scrapers.flashscore_match as fm
import footstats.scrapers.lineup_scraper as lsc
import footstats.scrapers.referee_db as rdb

_SEDZIA = {"name": "Szymon Marciniak", "avg_yellow": 5.1, "avg_goals": 2.4,
           "n_matches": 40}


def _fixture(home: str, away: str, fid: int = 1, referee: str = "") -> dict:
    return {"fixture": {"id": fid, "referee": referee},
            "teams": {"home": {"name": home}, "away": {"name": away}}}


class _Odpowiedz:
    def __init__(self, fixtures):
        self._f = fixtures

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._f}


@pytest.fixture
def faza(monkeypatch):
    """Otoczenie fazy final. `referee_signal` NIE jest podstawiane — inaczej
    podwojny odczyt bazy zostalby ukryty przez atrape."""
    stan = {"fixtures": [], "odczyty": []}

    monkeypatch.setattr("requests.get", lambda url, **kw: _Odpowiedz(stan["fixtures"]))
    monkeypatch.setattr(lsc, "get_lineup", lambda fixture_id, api_key: None)
    monkeypatch.setattr(fm, "scrape_match_with_search",
                        lambda home, away: {"success": False})
    monkeypatch.setattr(ls, "lineup_confidence_penalty_v2", lambda *a: 0.1)
    monkeypatch.setattr(ls, "lineup_offensive_strength", lambda *a: 0.5)
    monkeypatch.setattr(dp, "_wzbogac_team_news", lambda k: None)
    monkeypatch.delenv("FOOTSTATS_REFRESH_PLAYERS", raising=False)

    def _licz_odczyty(nazwa):
        stan["odczyty"].append(nazwa)
        return dict(_SEDZIA)

    monkeypatch.setattr(rdb, "get_referee", _licz_odczyty)
    return stan


def _kandydat(gosp="Legia", gosc="Lech Poznan") -> dict:
    return {"gospodarz": gosp, "goscie": gosc}


# ── nieosiagalna baza ───────────────────────────────────────────────────────

def test_padnieta_baza_sedziow_nie_zabija_wzbogacania(faza, monkeypatch):
    def _wybuch(nazwa):
        raise RuntimeError("DATABASE_URL env var not set")

    monkeypatch.setattr(rdb, "get_referee", _wybuch)
    faza["fixtures"] = [_fixture("Legia", "Lech Poznan", referee="Marciniak")]
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert k["referee_name"] == "Marciniak", "nazwisko z fixture ma zostac"
    assert "referee_avg_y" not in k, "brak bazy = brak statystyki, nie zero"


@pytest.mark.parametrize("wyjatek", [
    RuntimeError("DATABASE_URL env var not set"),
    OSError("connection refused"),
])
def test_kazda_awaria_bazy_jest_przezywalna(faza, monkeypatch, wyjatek):
    def _wybuch(nazwa):
        raise wyjatek

    monkeypatch.setattr(rdb, "get_referee", _wybuch)
    faza["fixtures"] = [_fixture("Legia", "Lech Poznan", referee="Marciniak")]

    dp._enrichuj_finalna_faza([_kandydat()], "klucz")   # nie moze rzucic


def test_padnieta_baza_ostrzega_RAZ_a_nie_przy_kazdym_meczu(faza, monkeypatch, caplog):
    """46 kandydatow to bylby 46 identycznych ostrzezen. Szum zabija alarmy
    tak samo skutecznie jak cisza."""
    monkeypatch.setattr(rdb, "get_referee",
                        lambda n: (_ for _ in ()).throw(RuntimeError("brak DB")))
    faza["fixtures"] = [
        _fixture("Legia", "Lech Poznan", fid=1, referee="Marciniak"),
        _fixture("Wisla", "Cracovia", fid=2, referee="Kowalski"),
        _fixture("Pogon", "Rakow", fid=3, referee="Nowak"),
    ]
    kandydaci = [_kandydat("Legia", "Lech Poznan"), _kandydat("Wisla", "Cracovia"),
                 _kandydat("Pogon", "Rakow")]

    with caplog.at_level(logging.WARNING):
        dp._enrichuj_finalna_faza(kandydaci, "klucz")

    ostrzezenia = [r for r in caplog.records if r.levelno >= logging.WARNING
                   and "sedzi" in r.getMessage().lower()]
    assert len(ostrzezenia) == 1, f"oczekiwano 1 ostrzezenia, jest {len(ostrzezenia)}"


def test_padnieta_baza_NIE_jest_cicha(faza, monkeypatch, caplog):
    """Brak sedziego w bazie i nieosiagalna baza daja ten sam `None` —
    log jest jedyna rzecza, ktora je rozroznia."""
    monkeypatch.setattr(rdb, "get_referee",
                        lambda n: (_ for _ in ()).throw(RuntimeError("brak DB")))
    faza["fixtures"] = [_fixture("Legia", "Lech Poznan", referee="Marciniak")]

    with caplog.at_level(logging.WARNING):
        dp._enrichuj_finalna_faza([_kandydat()], "klucz")

    assert "sedzi" in caplog.text.lower()


# ── kontrola: dzialajaca baza ───────────────────────────────────────────────

def test_dzialajaca_baza_dalej_daje_statystyki(faza):
    faza["fixtures"] = [_fixture("Legia", "Lech Poznan", referee="Marciniak")]
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert k["referee_avg_y"] == 5.1
    assert k["referee_matches"] == 40
    assert k["referee_signal"] == "KARTKOWY", "avg_yellow 5.1 > prog 4.3"


def test_jeden_odczyt_bazy_na_sedziego_a_nie_dwa(faza):
    """`referee_signal` wolalo `get_referee` po raz drugi dla tej samej nazwy."""
    faza["fixtures"] = [_fixture("Legia", "Lech Poznan", referee="Marciniak")]

    dp._enrichuj_finalna_faza([_kandydat()], "klucz")

    assert faza["odczyty"] == ["Marciniak"], (
        f"oczekiwano 1 odczytu bazy, bylo {len(faza['odczyty'])}: {faza['odczyty']}"
    )


# ── czysta funkcja sygnalu ──────────────────────────────────────────────────

@pytest.mark.parametrize("stats,oczekiwany", [
    (None,                                    "NIEZNANY"),
    ({"avg_yellow": 5.1, "avg_goals": 2.4},   "KARTKOWY"),
    ({"avg_yellow": 3.0, "avg_goals": 3.4},   "BRAMKOWY"),
    ({"avg_yellow": 3.0, "avg_goals": 2.0},   "NEUTRALNY"),
    ({},                                      "NEUTRALNY"),
    ({"avg_yellow": None, "avg_goals": None}, "NEUTRALNY"),
])
def test_sygnal_liczony_z_gotowych_statystyk(stats, oczekiwany):
    """Rozdzielenie odczytu od klasyfikacji — zeby wolajacy, ktory ma juz
    wiersz sedziego, nie musial pytac bazy drugi raz o to samo."""
    assert rdb.signal_from_stats(stats) == oczekiwany


def test_referee_signal_dalej_dziala_tak_samo(monkeypatch):
    """Zgodnosc wstecz: publiczna funkcja nie zmienia zachowania."""
    monkeypatch.setattr(rdb, "get_referee", lambda n: dict(_SEDZIA))
    assert rdb.referee_signal("Marciniak") == "KARTKOWY"
