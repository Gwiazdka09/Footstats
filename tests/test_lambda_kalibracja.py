"""test_lambda_kalibracja.py — kalibracja λ i korekta za kontuzje.

PO CO: λ to rdzeń modelu Poissona. Błąd tutaj nie wywala niczego — po prostu
KAŻDA predykcja jest przekrzywiona, a widać to dopiero po tygodniach w ROI.

Dwa bezpieczniki, które muszą trzymać:

  * SAFETY RAIL [0.85, 1.15] na współczynnikach kalibracji. Kalibracja liczona
    jest z historii; pojedynczy dziwny okres (mało meczów, seria remisów) potrafi
    dać bias 1.6, a taki mnożnik przesunąłby wszystkie λ o 60%. Rail obcina to
    przy ZAPISIE i przy ODCZYCIE — plik podmieniony ręcznie też nie przejdzie.
  * CAP ±20% na karach za kontuzje. Bez niego drużyna z ośmioma absencjami
    dostawałaby λ bliskie zeru.

Uszkodzony albo brakujący plik kalibracji ma dawać (1.0, 1.0) — model bez
kalibracji jest gorszy, ale działa; model z połową wczytanego JSON-a jest
nieprzewidywalny.

UWAGA: `save_calibration` pisze do data/model_calibration.json. Tutaj ścieżka
jest przekierowana na katalog tymczasowy — testy nie mogą nadpisać kalibracji
produkcyjnej.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import footstats.core.lambda_optimizer as lo
from footstats.core.lambda_optimizer import (
    CAL_MAX,
    CAL_MIN,
    injury_correction,
    injury_lambda_factors,
)


@pytest.fixture(autouse=True)
def kalibracja_w_tmp(tmp_path, monkeypatch):
    """Przekierowuje plik kalibracji na tmp i czyści cache przed każdym testem."""
    monkeypatch.setattr(lo, "CALIBRATION_PATH", tmp_path / "model_calibration.json")
    lo.invalidate_cache()
    yield tmp_path / "model_calibration.json"
    lo.invalidate_cache()


# ── load_calibration ────────────────────────────────────────────────────────

def test_brak_pliku_to_neutralne_wspolczynniki():
    """Model bez kalibracji ma działać, nie wywalać się."""
    assert lo.load_calibration() == (1.0, 1.0)


@pytest.mark.parametrize("smiec", [
    "{niepoprawny json", "", '{"factor_home": "abc"}',
    # Poprawny JSON, ale zly typ na wierzchu — `.get()` rzuca AttributeError.
    # Nie lapal go pierwotny `except (OSError, ValueError, KeyError)`, wiec
    # wyjatek wychodzil na zewnatrz mimo kontraktu z docstringa.
    "[]", '"tekst"', "123", "null",
])
def test_uszkodzony_plik_to_neutralne_wspolczynniki(kalibracja_w_tmp, smiec):
    """Model z połową wczytanego JSON-a byłby nieprzewidywalny.

    Ta ścieżka jest w gorącej części predykcji — wyjątek stąd zatrzymałby
    liczenie WSZYSTKICH meczów, zamiast zejść na model bez kalibracji."""
    kalibracja_w_tmp.write_text(smiec, encoding="utf-8")

    assert lo.load_calibration() == (1.0, 1.0)


def test_poprawny_plik_wczytany(kalibracja_w_tmp):
    kalibracja_w_tmp.write_text(json.dumps({"factor_home": 1.05, "factor_away": 0.95}))

    assert lo.load_calibration() == (1.05, 0.95)


@pytest.mark.parametrize("zapisany,oczekiwany", [
    (1.60, CAL_MAX), (0.20, CAL_MIN), (99.0, CAL_MAX), (-5.0, CAL_MIN),
])
def test_odczyt_tez_obcina_do_railu(kalibracja_w_tmp, zapisany, oczekiwany):
    """Plik podmieniony ręcznie nie może ominąć bezpiecznika."""
    kalibracja_w_tmp.write_text(
        json.dumps({"factor_home": zapisany, "factor_away": zapisany}))

    assert lo.load_calibration() == (oczekiwany, oczekiwany)


def test_brak_pola_to_wartosc_neutralna(kalibracja_w_tmp):
    kalibracja_w_tmp.write_text(json.dumps({"factor_home": 1.1}))

    assert lo.load_calibration() == (1.1, 1.0)


def test_plik_czytany_raz(kalibracja_w_tmp):
    """Kalibracja siedzi w gorącej ścieżce — odczyt z dysku przy każdym meczu
    byłby zbędnym kosztem."""
    kalibracja_w_tmp.write_text(json.dumps({"factor_home": 1.05, "factor_away": 0.95}))
    lo.load_calibration()

    kalibracja_w_tmp.write_text(json.dumps({"factor_home": 1.15, "factor_away": 0.85}))

    assert lo.load_calibration() == (1.05, 0.95)


def test_uniewaznienie_cache_wymusza_ponowny_odczyt(kalibracja_w_tmp):
    kalibracja_w_tmp.write_text(json.dumps({"factor_home": 1.05, "factor_away": 0.95}))
    lo.load_calibration()
    kalibracja_w_tmp.write_text(json.dumps({"factor_home": 1.15, "factor_away": 0.85}))

    lo.invalidate_cache()

    assert lo.load_calibration() == (1.15, 0.85)


# ── save_calibration ────────────────────────────────────────────────────────

def test_zapis_i_odczyt_w_obie_strony(kalibracja_w_tmp):
    lo.save_calibration(1.05, 0.95, n_matches=200)

    assert lo.load_calibration() == (1.05, 0.95)


@pytest.mark.parametrize("bias,oczekiwany", [(1.60, CAL_MAX), (0.20, CAL_MIN)])
def test_zapis_obcina_do_railu(kalibracja_w_tmp, bias, oczekiwany):
    """Bias 1.6 z dziwnego okresu przesunąłby wszystkie λ o 60%."""
    wynik = lo.save_calibration(bias, bias, n_matches=50)

    assert wynik["factor_home"] == oczekiwany
    assert wynik["factor_away"] == oczekiwany


def test_obciecie_jest_odnotowane(kalibracja_w_tmp):
    """Bez tej flagi nie wiadomo, że model chciał czegoś skrajnego."""
    wynik = lo.save_calibration(1.60, 1.0, n_matches=50)

    assert wynik["clamped_home"] is True
    assert wynik["clamped_away"] is False


def test_surowy_bias_zachowany_do_audytu(kalibracja_w_tmp):
    wynik = lo.save_calibration(1.60, 0.20, n_matches=50)

    assert wynik["bias_raw_home"] == 1.6
    assert wynik["bias_raw_away"] == 0.2


def test_rail_zapisany_w_pliku(kalibracja_w_tmp):
    wynik = lo.save_calibration(1.0, 1.0, n_matches=10)

    assert wynik["safety_rail"] == [CAL_MIN, CAL_MAX]


def test_liczba_meczow_i_skutecznosc_zapisane(kalibracja_w_tmp):
    """Kalibracja z 12 meczów znaczy co innego niż z 500 — bez tego pola
    nie da się ocenić, czy w ogóle jej ufać."""
    wynik = lo.save_calibration(1.0, 1.0, n_matches=200, acc_1x2=54.321)

    assert wynik["n_matches"] == 200
    assert wynik["acc_1x2_pct"] == 54.32


def test_brak_skutecznosci_to_none(kalibracja_w_tmp):
    assert lo.save_calibration(1.0, 1.0, n_matches=10)["acc_1x2_pct"] is None


def test_zapis_uniewaznia_cache(kalibracja_w_tmp):
    """Bez tego proces liczyłby dalej na starych współczynnikach."""
    lo.load_calibration()

    lo.save_calibration(1.10, 0.90, n_matches=100)

    assert lo.load_calibration() == (1.10, 0.90)


def test_plik_zapisany_z_data(kalibracja_w_tmp):
    lo.save_calibration(1.0, 1.0, n_matches=10)

    dane = json.loads(kalibracja_w_tmp.read_text(encoding="utf-8"))
    assert dane["updated_at"].endswith("Z")


# ── injury_lambda_factors ───────────────────────────────────────────────────

def _kontuzja(pozycja: str, nazwa: str = "Gracz") -> dict:
    return {"name": nazwa, "position": pozycja}


def test_brak_kontuzji_nic_nie_zmienia():
    assert injury_lambda_factors([]) == (1.0, 1.0)


@pytest.mark.parametrize("poz", ["F", "M", "f", "m"])
def test_brak_ofensywnego_obniza_wlasne_lambda(poz):
    atak, leak = injury_lambda_factors([_kontuzja(poz)])

    assert atak == 0.95
    assert leak == 1.0, "brak napastnika nie może podnosić λ rywala"


@pytest.mark.parametrize("poz", ["D", "G", "d", "g"])
def test_brak_defensywnego_podnosi_lambda_rywala(poz):
    atak, leak = injury_lambda_factors([_kontuzja(poz)])

    assert atak == 1.0, "brak obrońcy nie może obniżać własnego ataku"
    assert leak == 1.05


def test_kary_sie_sumuja():
    atak, leak = injury_lambda_factors([_kontuzja("F"), _kontuzja("M"), _kontuzja("D")])

    assert atak == 0.90
    assert leak == 1.05


def test_cap_na_ataku():
    """Osiem absencji nie może zbić λ do zera."""
    atak, _ = injury_lambda_factors([_kontuzja("F") for _ in range(10)])

    assert atak == 0.80


def test_cap_na_obronie():
    _, leak = injury_lambda_factors([_kontuzja("D") for _ in range(10)])

    assert leak == 1.20


def test_nieznana_pozycja_ignorowana():
    assert injury_lambda_factors([_kontuzja("X"), {"name": "bez pozycji"}]) == (1.0, 1.0)


def test_pusta_pozycja_nie_wywala():
    assert injury_lambda_factors([{"name": "X", "position": None}]) == (1.0, 1.0)


# ── goal_shares (v2): utrata topowego strzelca boli mocniej ─────────────────

def test_topowy_strzelec_boli_mocniej_niz_rezerwowy():
    gwiazda = injury_lambda_factors([_kontuzja("F", "Lewandowski")],
                                    goal_shares={"Lewandowski": 0.40})[0]
    rezerwa = injury_lambda_factors([_kontuzja("F", "Rezerwowy")],
                                    goal_shares={"Rezerwowy": 0.02})[0]

    assert gwiazda < rezerwa


def test_kara_liczona_z_udzialu_w_golach():
    """Udział 0.40 * skala 0.5 = kara 20%."""
    atak, _ = injury_lambda_factors([_kontuzja("F", "Gwiazda")],
                                    goal_shares={"Gwiazda": 0.40})

    assert atak == 0.80


def test_gracz_spoza_mappingu_dostaje_kare_plaska():
    """Brak w bazie strzelców to nie powód, żeby absencję zignorować."""
    atak, _ = injury_lambda_factors([_kontuzja("F", "Nieznany")],
                                    goal_shares={"Ktos Inny": 0.30})

    assert atak == 0.95


def test_udzial_w_golach_nie_dotyczy_obroncow():
    """Obrońcy nie strzelają — leak zostaje płaski."""
    _, leak = injury_lambda_factors([_kontuzja("D", "Obronca")],
                                    goal_shares={"Obronca": 0.50})

    assert leak == 1.05


def test_cap_dziala_takze_z_udzialami():
    atak, _ = injury_lambda_factors(
        [_kontuzja("F", "A"), _kontuzja("F", "B")],
        goal_shares={"A": 0.50, "B": 0.50})

    assert atak == 0.80


def test_brak_mappingu_to_zachowanie_plaskie():
    """goal_shares=None → tryb v1, bez zmian względem starszej wersji."""
    assert injury_lambda_factors([_kontuzja("F", "Ktokolwiek")])[0] == 0.95


# ── injury_correction (zgodność wsteczna dla bet_builder) ───────────────────

def test_korekta_bez_kontuzji_nie_zmienia_lambda():
    assert injury_correction(1.50, [], is_home=True) == 1.50


def test_gospodarz_ma_mniejsza_kare():
    """Większa tolerancja u siebie — rotacja mniej boli przy własnej publiczności."""
    dom = injury_correction(1.50, [_kontuzja("F")], is_home=True)
    wyjazd = injury_correction(1.50, [_kontuzja("F")], is_home=False)

    assert dom > wyjazd


def test_korekta_obniza_a_nie_podnosi():
    """Kontuzja ma zabierać gole, nie dodawać."""
    assert injury_correction(1.50, [_kontuzja("F")], is_home=False) < 1.50


def test_korekta_ignoruje_defensywnych():
    """Ta funkcja liczy tylko własny atak — obrona jest w modelu dwustronnym."""
    assert injury_correction(1.50, [_kontuzja("D")], is_home=False) == 1.50


# ── walk-forward: λ z historii ──────────────────────────────────────────────

def _historia(n: int, gole_dom: float = 2.0, gole_wyj: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame({
        "home": ["Legia"] * n,
        "away": ["Lech"] * n,
        "hg": [gole_dom] * n,
        "ag": [gole_wyj] * n,
        "result": ["H"] * n,
    })


def test_lambda_ze_sredniej_goli():
    assert lo._lambda_from_hist(_historia(10), "Legia", as_home=True) == 2.0


def test_za_malo_meczow_to_brak_lambdy():
    """Średnia z trzech meczów to szum, nie parametr modelu."""
    assert lo._lambda_from_hist(_historia(3), "Legia", as_home=True) is None


def test_lambda_liczona_osobno_dom_i_wyjazd():
    """Mieszanie stron zatarłoby przewagę własnego boiska."""
    hist = _historia(10)

    assert lo._lambda_from_hist(hist, "Lech", as_home=False) == 1.0
    assert lo._lambda_from_hist(hist, "Lech", as_home=True) is None


def test_forma_ze_zwyciestw():
    assert lo._forma(_historia(5), "Legia") == 3.0


def test_forma_bez_historii_jest_neutralna():
    """Brak danych ma dawać wartość środkową, nie zero."""
    pusta = pd.DataFrame({"home": [], "away": [], "hg": [], "ag": [], "result": []})

    assert lo._forma(pusta, "Nieznany") == 1.0


def test_predykcja_wymaga_obu_druzyn():
    assert lo._predict_lambdas(_historia(3), "Legia", "Lech") is None


def test_predykcja_koryguje_o_forme():
    lh, la = lo._predict_lambdas(_historia(10), "Legia", "Lech")

    assert lh > 2.0, "lepsza forma gospodarza ma podnosić jego λ"
    assert la < 1.0
