"""Predykcja nierozliczona ma WRACAC do kolejki, a nie znikac po trzech dniach.

PO CO: `update_pending` filtrowal `cutoff <= match_date < dzis`, czyli oknem
domknietym z OBU stron. Okno przesuwa sie z data, wiec predykcja, ktorej wynik
nie wpadl w swoje trzy dni, wypadala z zasiegu BEZPOWROTNIE — nie bylo retry,
kolejki ani nadrabiania.

Zmierzone na produkcji 2026-08-14: 95 predykcji bez wyniku, mecze od 7 maja do
11 sierpnia, WSZYSTKIE z `coupon_id IS NULL` (wiec `cron_settle`, ktory rozlicza
kupony, tez ich nie widzial). Przebieg na sucho z oknem 120 dni odzyskal 13,
pozostale 82 przepadly — kazda chwilowa usterka (padniety job, brak meczu
w zrodle, zawieszone API-Football) zamieniala sie w TRWALA strate danych.

Druga strona medalu: samo poszerzenie okna kazaloby skanowac te 82 martwe
rekordy przy KAZDYM przebiegu. Stad licznik prob i twardy limit paczki.
"""
from __future__ import annotations

from datetime import date

import pytest

from footstats.scrapers import results_updater as ru


def _pred(id_: int, data: str, proby: int = 0) -> dict:
    return {
        "id": id_,
        "match_date": data,
        "team_home": f"Dom{id_}",
        "team_away": f"Wyjazd{id_}",
        "league": "Testowa",
        "settle_attempts": proby,
    }


DZIS = date(2026, 8, 14)


# ── Sedno regresji ──────────────────────────────────────────────────────────

def test_stara_predykcja_wraca_do_kolejki():
    """Rekord sprzed trzech miesiecy MUSI trafic do nadrabiania.

    Dokladnie ten przypadek gubil sie na produkcji przez cale lato.
    """
    stare = _pred(1, "2026-05-07")

    swieze, nadrabiane = ru._wybierz_do_rozliczenia([stare], DZIS, days_back=3)

    assert swieze == []
    assert [p["id"] for p in nadrabiane] == [1], "stara predykcja znow przepadla"


def test_swieze_okno_przetwarzane_w_calosci():
    """Limit dotyczy WYLACZNIE nadrabiania — biezacych rozliczen nie wolno dlawic."""
    swieze_wejscie = [_pred(i, "2026-08-12") for i in range(30)]

    swieze, nadrabiane = ru._wybierz_do_rozliczenia(
        swieze_wejscie, DZIS, days_back=3, limit_nadrabiania=5
    )

    assert len(swieze) == 30
    assert nadrabiane == []


def test_nadrabianie_ma_twardy_limit():
    """Bez limitu kazdy przebieg skanowalby cala zalegla kolejke."""
    zalegle = [_pred(i, "2026-06-01") for i in range(50)]

    _, nadrabiane = ru._wybierz_do_rozliczenia(
        zalegle, DZIS, days_back=3, limit_nadrabiania=15
    )

    assert len(nadrabiane) == 15


def test_po_wyczerpaniu_prob_rekord_odpada():
    """Inaczej 82 nieodzyskiwalne rekordy krecilyby sie w kolejce w nieskonczonosc."""
    beznadziejny = _pred(1, "2026-05-07", proby=5)
    swiezszy = _pred(2, "2026-06-01", proby=0)

    _, nadrabiane = ru._wybierz_do_rozliczenia(
        [beznadziejny, swiezszy], DZIS, days_back=3, max_prob=5
    )

    assert [p["id"] for p in nadrabiane] == [2]


def test_brak_licznika_traktowany_jak_zero():
    """Wiersze sprzed migracji nie maja kolumny — nie moga przez to wypasc."""
    bez_licznika = {
        "id": 7, "match_date": "2026-05-07",
        "team_home": "A", "team_away": "B", "league": "L",
    }

    _, nadrabiane = ru._wybierz_do_rozliczenia([bez_licznika], DZIS, days_back=3)

    assert [p["id"] for p in nadrabiane] == [7]


# ── Granice okna ────────────────────────────────────────────────────────────

def test_mecz_jeszcze_nierozegrany_pomijany():
    """Nie ma czego rozliczac — i nie wolno mu palic proby."""
    przyszly = _pred(1, "2026-08-20")

    swieze, nadrabiane = ru._wybierz_do_rozliczenia([przyszly], DZIS, days_back=3)

    assert swieze == [] and nadrabiane == []


def test_mecz_z_dzis_jeszcze_nie_rozliczamy():
    """Granica `< dzis` zostaje — mecz moze trwac."""
    dzisiejszy = _pred(1, "2026-08-14")

    swieze, nadrabiane = ru._wybierz_do_rozliczenia([dzisiejszy], DZIS, days_back=3)

    assert swieze == [] and nadrabiane == []


def test_dokladna_granica_okna_liczy_sie_jako_swieza():
    """dzis-3 nalezy do okna swiezego, nie do nadrabiania (brak dziury i dublu)."""
    graniczny = _pred(1, "2026-08-11")

    swieze, nadrabiane = ru._wybierz_do_rozliczenia([graniczny], DZIS, days_back=3)

    assert [p["id"] for p in swieze] == [1]
    assert nadrabiane == []


def test_rekord_nie_trafia_do_obu_grup():
    """Podwojne przetworzenie = podwojne zapytania i podwojny licznik prob."""
    wejscie = [_pred(1, "2026-08-12"), _pred(2, "2026-05-07")]

    swieze, nadrabiane = ru._wybierz_do_rozliczenia(wejscie, DZIS, days_back=3)

    wspolne = {p["id"] for p in swieze} & {p["id"] for p in nadrabiane}
    assert not wspolne


def test_nadrabianie_bierze_najnowsze_najpierw():
    """Swiezsze mecze zrodla jeszcze pamietaja — to maksymalizuje zysk z limitu."""
    wejscie = [_pred(1, "2026-05-07"), _pred(2, "2026-07-30"), _pred(3, "2026-06-15")]

    _, nadrabiane = ru._wybierz_do_rozliczenia(
        wejscie, DZIS, days_back=3, limit_nadrabiania=2
    )

    assert [p["id"] for p in nadrabiane] == [2, 3]


# ── Odpornosc na smieciowe dane ─────────────────────────────────────────────

@pytest.mark.parametrize("zla_data", ["", None, "nie-data", "2026-13-45"])
def test_niepoprawna_data_nie_wywala_wyboru(zla_data):
    """Jeden zepsuty wiersz nie moze zatrzymac rozliczania calej reszty."""
    wejscie = [
        {"id": 1, "match_date": zla_data, "team_home": "A", "team_away": "B"},
        _pred(2, "2026-08-12"),
    ]

    swieze, nadrabiane = ru._wybierz_do_rozliczenia(wejscie, DZIS, days_back=3)

    assert [p["id"] for p in swieze] == [2]
    assert nadrabiane == []


# ── Okablowanie: licznik prob musi realnie rosnac ───────────────────────────

@pytest.fixture
def _pipeline_bez_sieci(monkeypatch):
    """update_pending bez API, bez scrapera, bez DB. Zwraca zebrane wywolania."""
    zebrane: dict = {"podbite": [], "zapisane": []}

    monkeypatch.setattr(ru, "_get_api_key", lambda: None)

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "init_db", lambda *a, **k: None)
    monkeypatch.setattr(bt, "update_result", lambda *a, **k: {"tip_correct": 1})
    monkeypatch.setattr(bt, "zwieksz_probe_rozliczenia",
                        lambda ids: zebrane["podbite"].extend(ids) or len(ids))

    # Zaden mecz sie nie znajdzie — interesuje nas sciezka NOT FOUND.
    import footstats.scrapers.flashscore_results as fs
    monkeypatch.setattr(fs, "get_match_result", lambda *a, **k: None)

    return zebrane


def test_nieudana_proba_podbija_licznik(monkeypatch, _pipeline_bez_sieci):
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "get_pending_results",
                        lambda: [_pred(41, "2026-05-07"), _pred(42, "2026-05-08")])
    monkeypatch.setattr(ru, "datetime", _ZamrozonyCzas)

    ru.update_pending(days_back=3, dry_run=False, verbose=False)

    assert sorted(_pipeline_bez_sieci["podbite"]) == [41, 42], (
        "licznik nie rosnie — nadrabianie krecilo by sie w kolko po tych samych rekordach"
    )


def test_dry_run_nie_dotyka_licznika(monkeypatch, _pipeline_bez_sieci):
    """Sonda diagnostyczna nie moze zmieniac stanu produkcji."""
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "get_pending_results", lambda: [_pred(41, "2026-05-07")])
    monkeypatch.setattr(ru, "datetime", _ZamrozonyCzas)

    ru.update_pending(days_back=3, dry_run=True, verbose=False)

    assert _pipeline_bez_sieci["podbite"] == []


def test_stara_predykcja_realnie_wchodzi_do_update_pending(monkeypatch, _pipeline_bez_sieci):
    """Test end-to-end regresji: przed fixem ten mecz nie byl nawet sprawdzany."""
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "get_pending_results", lambda: [_pred(99, "2026-05-07")])
    monkeypatch.setattr(ru, "datetime", _ZamrozonyCzas)

    stats = ru.update_pending(days_back=3, dry_run=False, verbose=False)

    assert stats["not_found"] == 1, "stary mecz w ogole nie trafil do sprawdzenia"


class _ZamrozonyCzas:
    """Zamraza `datetime.now()` — inaczej testy gnija wraz z uplywem czasu."""

    @staticmethod
    def now():
        from datetime import datetime as _dt
        return _dt(2026, 8, 14, 12, 0, 0)

    @staticmethod
    def fromisoformat(s):
        from datetime import datetime as _dt
        return _dt.fromisoformat(s)


# ── Migracja ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_migracja_12_dodaje_licznik_w_obu_dialektach(dialekt):
    """Kolumny brakujacej na prod nie da sie nadrobic kodem — patrz CLV (migracja 11)."""
    from footstats.db.migrations import _get_migrations_for_dialect

    wersje = {nr: (opis, sql) for nr, opis, sql in _get_migrations_for_dialect(dialekt)}

    assert 12 in wersje, f"brak migracji 12 dla {dialekt}"
    opis, sql = wersje[12]
    assert "settle_attempts" in opis
    assert any("settle_attempts" in s for s in sql)


def test_pending_niesie_licznik_prob():
    """Bez tej kolumny w SELECT wybor traktowalby wszystko jak 0 prob."""
    import inspect

    from footstats.core import backtest

    zrodlo = inspect.getsource(backtest.get_pending_results)
    assert "settle_attempts" in zrodlo
