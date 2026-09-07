"""CLV nie moze zalezec od `prediction_id`, ktorego noga NIGDY nie dostaje.

STAN ZASTANY (2026-09-07, dowod z produkcji). `predictions.clv_closing_odds`
bylo NULL dla wszystkich 295 wierszy, mimo ze `record_closing_odds` jest wolane
z `evening_agent`. Przyczyna: caly blok CLV stal pod bramka

    pred_id = leg.get("prediction_id")
    if pred_id:
        ...

a tego klucza nikt nie zapisuje. `grep prediction_id` po calym `src/` pokazuje
wylacznie ODCZYTY. Pomiar 60 rozliczonych kuponow: 0 z 82 nog ma ten klucz.

Nie da sie tego naprawic samym dopisaniem klucza, bo glowne zrodlo kuponow —
`system_paper.build_single_leg_coupons` — w ogole nie przechodzi przez tabele
`predictions`: bierze typ prosto z modelu (`najlepszy_typ`), bez LLM-a. To 429
z 439 rozliczonych kuponow. CLV oparte na `predictions` nie ma szans ich objac.

Dlatego CLV liczy sie NA NODZE: noga ma juz `tip`, `odds`, druzyny i date,
czyli komplet potrzebny do porownania z kursem zamkniecia.
"""
from __future__ import annotations

import pytest

import footstats.evening_agent as ea

KURSY_CSV = {"home": 1.85, "draw": 3.60, "away": 4.20,
             "over_2_5": 1.95, "under_2_5": 1.88, "zrodlo": "pinnacle-closing"}


@pytest.fixture
def bez_af(monkeypatch):
    """API-Football wylaczone — sprawdzamy darmowa sciezke football-data."""
    monkeypatch.setattr(ea, "_fetch_closing_odds", lambda *a, **k: None)


def _podstaw_csv(monkeypatch, kursy):
    # `kursy_zamkniecia` jest importowane LOKALNIE w funkcji, wiec seam jest
    # w module zrodlowym, nie w `evening_agent`.
    import footstats.scrapers.closing_odds as co
    monkeypatch.setattr(co, "kursy_zamkniecia", lambda *a, **k: kursy)


def test_noga_bez_prediction_id_dostaje_clv(monkeypatch, bez_af):
    """Rdzen regresji: brak `prediction_id` nie moze kasowac CLV."""
    _podstaw_csv(monkeypatch, KURSY_CSV)
    kurs = ea._kurs_zamkniecia_nogi("Over 2.5", "Arsenal", "Chelsea",
                                    "2026-09-01", api_key="", fixtures=[])
    assert kurs == 1.95


@pytest.mark.parametrize("typ, oczekiwany", [
    ("1", 1.85), ("2", 4.20), ("Over 2.5", 1.95), ("Under 2.5", 1.88),
])
def test_kazdy_typ_dostaje_swoja_cene(monkeypatch, bez_af, typ, oczekiwany):
    """Do tej poprawki KAZDY typ dostawal `kursy["home"]`."""
    _podstaw_csv(monkeypatch, KURSY_CSV)
    assert ea._kurs_zamkniecia_nogi(typ, "A", "B", "2026-09-01",
                                    api_key="", fixtures=[]) == oczekiwany


@pytest.mark.parametrize("typ", ["BTTS", "1X", "Over 1.5", "BB: 1 + Over 1.5"])
def test_typ_bez_odpowiednika_zostaje_bez_clv(monkeypatch, bez_af, typ):
    """24% nog to zdarzenia, ktorych CSV nie notuje — lepiej nic niz cudza cena."""
    _podstaw_csv(monkeypatch, KURSY_CSV)
    assert ea._kurs_zamkniecia_nogi(typ, "A", "B", "2026-09-01",
                                    api_key="", fixtures=[]) is None


def test_api_football_tylko_dla_gospodarza(monkeypatch):
    """`_fetch_closing_odds` zwraca WYLACZNIE strone gospodarza (bet=1, Home Win).

    Uzycie go dla `2` albo `Over 2.5` byloby dokladnie tym bledem, ktory ta
    poprawka usuwa — tyle ze w drugim zrodle.
    """
    _podstaw_csv(monkeypatch, None)          # CSV nie zna meczu
    monkeypatch.setattr(ea, "_find_fixture_id", lambda *a, **k: 42)
    monkeypatch.setattr(ea, "_fetch_closing_odds", lambda *a, **k: 6.34)

    assert ea._kurs_zamkniecia_nogi("1", "A", "B", "2026-09-01",
                                    api_key="k", fixtures=[{}]) == 6.34
    for typ in ("2", "X", "Over 2.5"):
        assert ea._kurs_zamkniecia_nogi(typ, "A", "B", "2026-09-01",
                                        api_key="k", fixtures=[{}]) is None


def test_csv_ma_pierwszenstwo_przed_api_football(monkeypatch):
    """CSV pokrywa wszystkie mapowalne typy, AF tylko jeden — i kosztuje zapytanie."""
    _podstaw_csv(monkeypatch, KURSY_CSV)
    monkeypatch.setattr(ea, "_find_fixture_id",
                        lambda *a, **k: pytest.fail("AF wolany mimo trafienia w CSV"))
    assert ea._kurs_zamkniecia_nogi("1", "A", "B", "2026-09-01",
                                    api_key="k", fixtures=[{}]) == 1.85


def test_brak_obu_zrodel_nie_wybucha(monkeypatch, bez_af):
    _podstaw_csv(monkeypatch, None)
    assert ea._kurs_zamkniecia_nogi("1", "A", "B", "2026-09-01",
                                    api_key="", fixtures=[]) is None


def test_blad_zrodla_nie_zabija_rozliczenia(monkeypatch, bez_af):
    """Rozliczenie kuponu jest wazniejsze niz telemetria CLV."""
    import footstats.scrapers.closing_odds as co

    def _wybuch(*a, **k):
        raise OSError("CSV niedostepny")

    monkeypatch.setattr(co, "kursy_zamkniecia", _wybuch)
    assert ea._kurs_zamkniecia_nogi("1", "A", "B", "2026-09-01",
                                    api_key="", fixtures=[]) is None


def test_blok_clv_nie_stoi_pod_bramka_prediction_id():
    """Straznik na ksztalt kodu, nie na wynik.

    Blad zyl przez cala historie projektu wlasnie dlatego, ze kazdy kawalek
    dzialal osobno: `record_closing_odds` ma testy, `kursy_zamkniecia` ma testy,
    a laczylo je `if pred_id:` nad wszystkim. Test na sam wynik nie odroznia
    "policzone" od "policzone dla nogi, ktora akurat miala id".
    """
    import inspect

    zrodlo = inspect.getsource(ea.run_evening_agent)
    linie = zrodlo.splitlines()
    # Tylko KOD. Bez tego filtra straznik lapal komentarz opisujacy naprawiony
    # blad ("Do 2026-09-07 caly ten blok stal pod `if pred_id:`") i przewracal
    # sie na wlasnym uzasadnieniu.
    kod = [l for l in linie if not l.lstrip().startswith("#")]
    idx_bramki = [i for i, l in enumerate(kod) if l.lstrip().startswith("if pred_id:")]
    idx_clv = [i for i, l in enumerate(kod) if "_kurs_zamkniecia_nogi(" in l]

    assert idx_clv, "run_evening_agent nie liczy juz kursu zamkniecia dla nogi"
    if idx_bramki:
        # Bramka moze zostac dla `update_result`, ale nie moze obejmowac CLV.
        bramka = idx_bramki[0]
        wciecie_bramki = len(kod[bramka]) - len(kod[bramka].lstrip())
        for i in idx_clv:
            assert i < bramka or (
                len(kod[i]) - len(kod[i].lstrip())) <= wciecie_bramki, (
                "liczenie CLV wrocilo pod `if pred_id:` — noga bez id znow je traci")
