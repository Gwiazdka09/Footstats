"""Filtr strzelców po aktualnym składzie FotMob (mock HTTP, zero sieci)."""
import logging

import pytest
import requests

from footstats.scrapers.teamnews import sklad


def _szukaj(nazwa="FC Barcelona", tid="8634"):
    return [{"title": {"key": "teams"},
             "suggestions": [{"type": "team", "id": tid, "name": nazwa}]}]


def _skladowy(*imiona):
    return {"squad": {"squad": [
        {"title": "attackers", "members": [{"name": n} for n in imiona]}]}}


@pytest.fixture(autouse=True)
def _czysty_cache():
    sklad._cache.clear()
    yield
    sklad._cache.clear()


def _podmien(monkeypatch, odpowiedzi):
    wywolania = []

    def fake(sciezka, **params):
        wywolania.append(sciezka)
        w = odpowiedzi[sciezka]
        if isinstance(w, Exception):
            raise w
        return w

    monkeypatch.setattr(sklad.fotmob, "_pobierz", fake)
    return wywolania


BARCA = {"search/suggest": _szukaj(),
         "teams": _skladowy("Lamine Yamal", "Raphinha", "Pedri")}


def test_lewandowski_znika_yamal_zostaje(monkeypatch):
    _podmien(monkeypatch, BARCA)
    gs = {"R. Lewandowski": 0.12, "L. Yamal": 0.2}
    assert sklad.strzelcy_w_skladzie(gs, "FC Barcelona") == {"L. Yamal": 0.2}


@pytest.mark.parametrize("baza,pelne", [
    ("Ł. Sekulski", "Łukasz Sekulski"),
    ("Mbappé", "Kylian Mbappé"),
    ("Kylian Mbappe", "Kylian Mbappé"),
    ("Pedri", "Pedri"),
    ("V. van Dijk", "Virgil van Dijk"),
])
def test_dopasowanie_inicjal_i_pelne_imie(baza, pelne):
    assert sklad._ten_gracz(baza, sklad.klucz_gracza(pelne))


def test_rozne_osoby_o_tym_samym_inicjale_nie_pasuja():
    assert not sklad._ten_gracz("R. Lewandowski", "robert zielinski")
    assert not sklad._ten_gracz("A. Silva", "bernardo silva")


def test_brak_skladu_none_bez_filtra(monkeypatch):
    _podmien(monkeypatch, {"search/suggest": [], "teams": {}})
    gs = {"R. Lewandowski": 0.12}
    assert sklad.aktualny_sklad("FC Barcelona") is None
    assert sklad.strzelcy_w_skladzie(gs, "FC Barcelona") == gs


def test_blad_sieci_none_i_warning(monkeypatch, caplog):
    _podmien(monkeypatch, {"search/suggest": requests.ConnectionError("x")})
    with caplog.at_level(logging.WARNING):
        assert sklad.aktualny_sklad("FC Barcelona") is None
    assert "ConnectionError" in caplog.text


def test_cache_drugie_wywolanie_bez_sieci(monkeypatch):
    w = _podmien(monkeypatch, BARCA)
    sklad.aktualny_sklad("FC Barcelona")
    sklad.aktualny_sklad("FC Barcelona")
    assert w == ["search/suggest", "teams"]


def test_zero_trafien_nie_czysci_karty(monkeypatch, caplog):
    _podmien(monkeypatch, BARCA)
    gs = {"Jan Kowalski": 0.3}
    with caplog.at_level(logging.WARNING):
        assert sklad.strzelcy_w_skladzie(gs, "FC Barcelona") == gs
    assert "zaden strzelec" in caplog.text


def test_wybiera_druzyne_a_nie_rezerwy(monkeypatch):
    szukaj = [{"suggestions": [
        {"type": "team", "id": "1", "name": "Legia Warszawa II"},
        {"type": "team", "id": "2", "name": "Legia Warszawa"}]}]
    _podmien(monkeypatch, {"search/suggest": szukaj})
    assert sklad._znajdz_id("Legia Warszawa") == 2
