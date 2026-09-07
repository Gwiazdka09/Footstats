"""Team news pobierane dla DNI KANDYDATOW, nie tylko dla dzisiaj.

STAN ZASTANY (do 2026-09-07):

    dane = _pobierz_team_news(_date.today().isoformat(), pary)

Jedno zapytanie, zawsze o dzien biezacy. A `daily_agent` pracuje w oknie 72h —
log jobu z 06.09 mowi wprost „Bzzoiro: 28 kandydatow w oknie 72h". Kazdy mecz
grany jutro lub pojutrze byl wiec niewidoczny dla FotMoba, bo nie ma go na
liscie dnia dzisiejszego.

SKALA: 74% wierszy `model_log` to mecze grane tego samego dnia, wiec to nie byla
glowna strata — ale okolo jednej czwartej kandydatow nie mialo szans dostac ani
skladu, ani absencji, ani sedziego. Przy czym FotMob oddaje liste dnia jednym
zapytaniem, wiec koszt to dwa-trzy dodatkowe requesty na przebieg.

Data ma jeszcze drugie znaczenie: `fotmob.parsuj_mecz` dostaje ja jako date
meczu. Pobieranie wszystkiego pod dzisiejsza data stemplowalo mecze jutrzejsze
dniem dzisiejszym.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pytest

from footstats.core import daily_phases as dp


@pytest.fixture(autouse=True)
def flaga(monkeypatch):
    monkeypatch.setenv(dp.FLAGA_TEAM_NEWS, "1")


def _k(data: str | None, gosp: str = "Legia", gosc: str = "Lech") -> dict:
    k = {"gospodarz": gosp, "goscie": gosc, "pw": 45.0, "pr": 27.0,
         "pp": 28.0, "o25": 52.0}
    if data is not None:
        k["data"] = data
    return k


def test_pyta_o_kazdy_dzien_wystepujacy_wsrod_kandydatow(monkeypatch):
    pytane: list[str] = []
    monkeypatch.setattr(dp, "_pobierz_team_news",
                        lambda d, pary: pytane.append(d) or [])
    dzis = date.today()
    dp._wzbogac_team_news([
        _k(dzis.isoformat()),
        _k((dzis + timedelta(days=1)).isoformat(), "Wisla", "Pogon"),
        _k((dzis + timedelta(days=2)).isoformat(), "Radomiak", "Piast"),
    ])
    assert pytane == sorted({
        dzis.isoformat(),
        (dzis + timedelta(days=1)).isoformat(),
        (dzis + timedelta(days=2)).isoformat(),
    })


def test_ten_sam_dzien_pytany_raz(monkeypatch):
    """Dwa mecze tego samego dnia to nie dwa requesty."""
    pytane: list[str] = []
    monkeypatch.setattr(dp, "_pobierz_team_news",
                        lambda d, pary: pytane.append(d) or [])
    dzis = date.today().isoformat()
    dp._wzbogac_team_news([_k(dzis), _k(dzis, "Wisla", "Pogon")])
    assert pytane == [dzis]


def test_brak_daty_cofa_do_dzisiaj(monkeypatch):
    pytane: list[str] = []
    monkeypatch.setattr(dp, "_pobierz_team_news",
                        lambda d, pary: pytane.append(d) or [])
    dp._wzbogac_team_news([_k(None)])
    assert pytane == [date.today().isoformat()]


def test_smieciowa_data_nie_generuje_requestu(monkeypatch):
    """Zapytanie o `nie-data` kosztuje tyle samo, co o poprawna, i nic nie da."""
    pytane: list[str] = []
    monkeypatch.setattr(dp, "_pobierz_team_news",
                        lambda d, pary: pytane.append(d) or [])
    dzis = date.today().isoformat()
    dp._wzbogac_team_news([_k("nie-data"), _k(dzis, "Wisla", "Pogon")])
    assert pytane == [dzis]


def test_liczba_dni_jest_ograniczona(monkeypatch):
    """Zepsuty kandydat z data w 2031 nie moze wygenerowac setek requestow."""
    pytane: list[str] = []
    monkeypatch.setattr(dp, "_pobierz_team_news",
                        lambda d, pary: pytane.append(d) or [])
    dzis = date.today()
    dp._wzbogac_team_news([
        _k((dzis + timedelta(days=i)).isoformat(), f"A{i}", f"B{i}")
        for i in range(20)
    ])
    assert len(pytane) <= dp.MAX_DNI_TEAM_NEWS
    assert pytane == sorted(pytane), "dni maja isc od najblizszego"


def test_wyniki_ze_wszystkich_dni_sa_scalane(monkeypatch):
    class _TN:
        def __init__(self, h, a):
            self.home, self.away = h, a
            self.source, self.sklad_jest_prognoza = "fotmob", False
            self.xi_home = self.xi_away = ()
            self.absencje_home = self.absencje_away = ()
            self.sedzia, self.sedzia_stats = None, {}

    dzis = date.today()
    jutro = (dzis + timedelta(days=1)).isoformat()
    mapa = {dzis.isoformat(): [_TN("Legia", "Lech")],
            jutro: [_TN("Wisla", "Pogon")]}
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda d, pary: mapa.get(d, []))
    kandydaci = [_k(dzis.isoformat()), _k(jutro, "Wisla", "Pogon")]
    dp._wzbogac_team_news(kandydaci)
    assert all(k.get("team_news_source") == "fotmob" for k in kandydaci)


def test_pusto_ze_wszystkich_dni_dalej_alarmuje(caplog, monkeypatch):
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda d, pary: [])
    dzis = date.today().isoformat()
    with caplog.at_level(logging.WARNING):
        dp._wzbogac_team_news([_k(dzis)])
    assert "team-news" in caplog.text


def test_kandydaci_bez_czytelnej_daty_sa_zglaszane(caplog, monkeypatch):
    """Rozjechany format daty w zrodle to cicha utrata calego dnia kandydatow."""
    monkeypatch.setattr(dp, "_pobierz_team_news", lambda d, pary: [])
    dzis = date.today().isoformat()
    with caplog.at_level(logging.WARNING):
        dp._daty_kandydatow([_k(dzis), _k("nie-data"), _k(None)])
    assert "bez czytelnej daty" in caplog.text
    assert "2 z 3" in caplog.text


def test_komplet_dat_nie_generuje_ostrzezenia(caplog, monkeypatch):
    """Kontrola: normalny przebieg ma byc cichy."""
    dzis = date.today().isoformat()
    with caplog.at_level(logging.WARNING):
        dp._daty_kandydatow([_k(dzis), _k(dzis, "Wisla", "Pogon")])
    assert "bez czytelnej daty" not in caplog.text
