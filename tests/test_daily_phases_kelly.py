"""test_daily_phases_kelly.py — dodawanie stawek Kelly'ego i roznica modeli.

PO CO: `_dodaj_kelly` liczy STAWKE dla kazdej nogi kazdego kuponu. Ma cztery
guardy i zaden nie mial testu, mimo ze jeden powstal po REALNEJ AWARII —
komentarz w kodzie mowi wprost: "(x or {}) — Groq potrafi zwrocic
kupon=None / zdarzenia=None (crash prod 20.07)".

Pozostale guardy: bankroll z bazy moze przyjsc jako None, `get_stake_multiplier`
moze oddac None, a `kelly_stake` rzuca przy kursie 1.0 (dzielenie przez zero).
Kazdy z nich stoi miedzy modelem a kwota realnie stawiana.

`_oblicz_roznica_modeli` liczy rozjazd Poisson vs Bzzoiro — sygnal uzywany
pozniej do odrzucania kandydatow. Kandydat bez danych ML musi zostac POMINIETY,
a nie dostac rozniczy policzonej z zer.
"""
from __future__ import annotations

import pytest

import footstats.core.daily_phases as dp


def _zdarzenie(pewnosc=60, kurs=2.0, **kw) -> dict:
    return {"nr": 1, "mecz": "Legia – Lech", "typ": "1",
            "pewnosc_pct": pewnosc, "kurs": kurs, **kw}


def _dane(**kw) -> dict:
    baza = {"kupon_a": {"zdarzenia": [_zdarzenie()]}}
    baza.update(kw)
    return baza


# ── _dodaj_kelly: guardy wejscia ────────────────────────────────────────────

def test_dodaje_stawke_do_kazdej_nogi():
    dane = _dane()
    dp._dodaj_kelly(dane, bankroll=100.0)
    assert "kelly_stake" in dane["kupon_a"]["zdarzenia"][0]


def test_obsluguje_wszystkie_cztery_kupony():
    dane = {k: {"zdarzenia": [_zdarzenie()]}
            for k in ("kupon_a", "kupon_b", "kupon_c", "kupon_d")}
    dp._dodaj_kelly(dane, bankroll=100.0)
    for k in ("kupon_a", "kupon_b", "kupon_c", "kupon_d"):
        assert "kelly_stake" in dane[k]["zdarzenia"][0]


def test_dodaje_stawke_do_top3():
    dane = {"top3": [{"mecz": "A – B", "pewnosc_pct": 70, "kurs": 1.9}]}
    dp._dodaj_kelly(dane, bankroll=100.0)
    assert "kelly_stake" in dane["top3"][0]


@pytest.mark.parametrize("kupon", [None, {}, {"zdarzenia": None}, {"zdarzenia": []}])
def test_kupon_none_nie_wywala(kupon):
    """REGRESJA: crash prod 20.07 — Groq oddal kupon=None / zdarzenia=None."""
    dp._dodaj_kelly({"kupon_a": kupon}, bankroll=100.0)     # nie rzuca


def test_top3_none_nie_wywala():
    dp._dodaj_kelly({"top3": None}, bankroll=100.0)


def test_puste_dane_nie_wywalaja():
    dp._dodaj_kelly({}, bankroll=100.0)


@pytest.mark.parametrize("bankroll", [None, 0, -50, "sto", [], float("nan")])
def test_niepoprawny_bankroll_spada_na_domyslny(bankroll, monkeypatch):
    """Baza potrafi oddac None zamiast salda — stawka musi i tak powstac."""
    dane = _dane()
    try:
        dp._dodaj_kelly(dane, bankroll=bankroll)
    except (TypeError, ValueError):
        pytest.fail(f"bankroll={bankroll!r} wywalil liczenie stawki")
    assert "kelly_stake" in dane["kupon_a"]["zdarzenia"][0]


def test_brak_pewnosci_traktowany_jak_50():
    dane = {"kupon_a": {"zdarzenia": [{"kurs": 2.0}]}}
    dp._dodaj_kelly(dane, bankroll=100.0)
    assert "kelly_stake" in dane["kupon_a"]["zdarzenia"][0]


def test_brak_kursu_nie_dzieli_przez_zero():
    """kelly_stake przy kursie 1.0 dzieli przez (odds-1) = 0 — musi byc zlapane."""
    dane = {"kupon_a": {"zdarzenia": [{"pewnosc_pct": 60}]}}
    dp._dodaj_kelly(dane, bankroll=100.0)
    assert dane["kupon_a"]["zdarzenia"][0]["kelly_stake"] is not None


def test_wyjatek_kelly_daje_stawke_zapasowa(monkeypatch):
    import footstats.core.kelly as kelly_mod

    def _wybuch(*a, **k):
        raise TypeError("zle argumenty")

    monkeypatch.setattr(kelly_mod, "kelly_stake", _wybuch)
    dane = _dane()
    dp._dodaj_kelly(dane, bankroll=100.0)
    assert dane["kupon_a"]["zdarzenia"][0]["kelly_stake"] == 1.0


# ── _dodaj_kelly: mnoznik kalibracji ────────────────────────────────────────

@pytest.fixture
def kalibracja(monkeypatch):
    """Podstawia mnoznik i podsumowanie kalibracji."""
    stan = {"multiplier": 1.0, "summary": {"n": 0}}
    import footstats.core.calibration as cal
    monkeypatch.setattr(cal, "get_stake_multiplier", lambda: stan["multiplier"])
    monkeypatch.setattr(cal, "calibration_summary", lambda: stan["summary"])
    return stan


@pytest.mark.parametrize("zly", [None, 0, -1, "duzo"])
def test_niepoprawny_mnoznik_spada_na_jeden(kalibracja, zly):
    """Mnoznik = None przemnozylby bankroll przez None -> TypeError."""
    kalibracja["multiplier"] = zly
    dane = _dane()
    dp._dodaj_kelly(dane, bankroll=100.0)
    assert "kelly_stake" in dane["kupon_a"]["zdarzenia"][0]


def test_wyzszy_mnoznik_daje_wyzsza_stawke(kalibracja):
    """Sedno kalibracji stawki: dobra forma bota = wieksze stawki."""
    kalibracja["multiplier"] = 1.0
    dane_maly = _dane()
    dp._dodaj_kelly(dane_maly, bankroll=1000.0)

    kalibracja["multiplier"] = 2.0
    dane_duzy = _dane()
    dp._dodaj_kelly(dane_duzy, bankroll=1000.0)

    assert (dane_duzy["kupon_a"]["zdarzenia"][0]["kelly_stake"]
            >= dane_maly["kupon_a"]["zdarzenia"][0]["kelly_stake"])


def test_podsumowanie_kalibracji_drukowane(kalibracja, capsys):
    kalibracja["summary"] = {"n": 10, "hit_rate": 0.6, "won": 6, "note": "OK",
                             "forma_multiplier": 1.2, "forma_note": "3/3"}
    dp._dodaj_kelly(_dane(), bankroll=100.0)
    out = capsys.readouterr().out
    assert "Kalibracja" in out and "60%" in out


def test_brak_historii_nie_drukuje_kalibracji(kalibracja, capsys):
    kalibracja["summary"] = {"n": 0}
    dp._dodaj_kelly(_dane(), bankroll=100.0)
    assert "Kalibracja:" not in capsys.readouterr().out


# ── _oblicz_roznica_modeli ──────────────────────────────────────────────────

def _kandydat(pw=50.0, pr=25.0, pp=25.0, wynik_g=2, wynik_a=1, **kw) -> dict:
    return {"pw": pw, "pr": pr, "pp": pp,
            "wynik_g": wynik_g, "wynik_a": wynik_a, "liga": "ENG-Premier League", **kw}


def test_dodaje_roznice_modeli():
    wyniki = [_kandydat()]
    dp._oblicz_roznica_modeli(wyniki)
    assert "roznica_modeli" in wyniki[0]
    assert 0.0 <= wyniki[0]["roznica_modeli"] <= 1.0


def test_kandydat_bez_danych_ml_pomijany():
    """Brak prawdopodobienstw Bzzoiro = brak porownania. Zero nie jest wynikiem."""
    wyniki = [_kandydat(pw=0, pr=0, pp=0)]
    dp._oblicz_roznica_modeli(wyniki)
    assert "roznica_modeli" not in wyniki[0]


def test_zgodne_modele_daja_mala_roznice():
    """Poisson z 2-1 przewiduje przewage gospodarza; ML tez -> maly rozjazd."""
    zgodny = [_kandydat(pw=62.0, pr=22.0, pp=16.0, wynik_g=2, wynik_a=1)]
    dp._oblicz_roznica_modeli(zgodny)

    rozjechany = [_kandydat(pw=10.0, pr=20.0, pp=70.0, wynik_g=3, wynik_a=0)]
    dp._oblicz_roznica_modeli(rozjechany)

    assert zgodny[0]["roznica_modeli"] < rozjechany[0]["roznica_modeli"]


def test_zerowy_wynik_nie_daje_zerowej_lambdy():
    """Lambda ma dolna granice 0.3 — 0 rozwalilby rozklad Poissona."""
    wyniki = [_kandydat(wynik_g=0, wynik_a=0)]
    dp._oblicz_roznica_modeli(wyniki)
    assert "roznica_modeli" in wyniki[0]


def test_none_w_typowanym_wyniku_nie_wywala():
    wyniki = [_kandydat(wynik_g=None, wynik_a=None)]
    dp._oblicz_roznica_modeli(wyniki)
    assert "roznica_modeli" in wyniki[0]


def test_pusta_lista_nie_wywala():
    dp._oblicz_roznica_modeli([])


def test_przetwarza_wszystkich_kandydatow():
    wyniki = [_kandydat(), _kandydat(pw=70.0, pr=20.0, pp=10.0)]
    dp._oblicz_roznica_modeli(wyniki)
    assert all("roznica_modeli" in k for k in wyniki)
