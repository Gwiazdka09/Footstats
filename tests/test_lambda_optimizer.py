"""test_lambda_optimizer.py — kalibracja lambd i predykcja walk-forward.

PO CO: modul mial 35%. Dwie rzeczy sa tu krytyczne dla modelu:

1. SAFETY RAIL (`CAL_MIN`/`CAL_MAX` = 0.85-1.15). Kalibracja mnozy lambdy
   Poissona. Bez ogranicznika jeden dziwny przebieg walk-forward moglby zapisac
   wspolczynnik 3.0 i rozjechac WSZYSTKIE przyszle predykcje. Ogranicznik nie
   mial testu.

2. CACHE `load_calibration`. Trzyma wspolczynniki w pamieci procesu — jesli nie
   uniewazni sie go po zapisie, joby licza na starych wartosciach do restartu.

`_predict_lambdas` to walk-forward BEZ zapisu do DB: strona ma znaczenie
(gole u siebie z kolumny `hg`, na wyjezdzie z `ag`) — pomylka odwraca sile
atakow, tak samo jak w scraperze xG.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import footstats.core.lambda_optimizer as lo


@pytest.fixture(autouse=True)
def plik_kalibracji(tmp_path, monkeypatch):
    """CALIBRATION_PATH na tmp + czysty cache przed i po kazdym tescie."""
    sciezka = tmp_path / "kal" / "model_calibration.json"
    monkeypatch.setattr(lo, "CALIBRATION_PATH", sciezka)
    lo.invalidate_cache()
    yield sciezka
    lo.invalidate_cache()


def _hist(*mecze) -> pd.DataFrame:
    """(home, away, hg, ag) -> DataFrame w schemacie walk-forward."""
    wiersze = []
    for home, away, hg, ag in mecze:
        wynik = "H" if hg > ag else ("A" if ag > hg else "D")
        wiersze.append({"home": home, "away": away, "hg": hg, "ag": ag,
                        "result": wynik})
    return pd.DataFrame(wiersze)


# ── load_calibration ────────────────────────────────────────────────────────

def test_brak_pliku_daje_neutralne_wspolczynniki():
    """Brak kalibracji NIE moze zmieniac predykcji — 1.0 to tozsamosc."""
    assert lo.load_calibration() == (1.0, 1.0)


def test_uszkodzony_plik_daje_neutralne(plik_kalibracji):
    plik_kalibracji.parent.mkdir(parents=True)
    plik_kalibracji.write_text("{niepoprawny", encoding="utf-8")
    assert lo.load_calibration() == (1.0, 1.0)


def test_wczytuje_zapisane_wspolczynniki(plik_kalibracji):
    lo.save_calibration(bias_h=1.05, bias_a=0.95, n_matches=200)
    assert lo.load_calibration() == (1.05, 0.95)


@pytest.mark.parametrize("zapisane,oczekiwane", [
    (3.0, lo.CAL_MAX),      # absurdalnie wysoki
    (0.1, lo.CAL_MIN),      # absurdalnie niski
    (1.05, 1.05),           # w normie — bez zmian
])
def test_odczyt_tez_przycina_do_safety_rail(plik_kalibracji, zapisane, oczekiwane):
    """Recznie podmieniony plik nie moze ominac ogranicznika."""
    plik_kalibracji.parent.mkdir(parents=True, exist_ok=True)
    plik_kalibracji.write_text(
        json.dumps({"factor_home": zapisane, "factor_away": 1.0}), encoding="utf-8")

    assert lo.load_calibration()[0] == pytest.approx(oczekiwane)


def test_wynik_jest_cachowany(plik_kalibracji):
    lo.save_calibration(bias_h=1.05, bias_a=0.95, n_matches=200)
    lo.load_calibration()

    plik_kalibracji.unlink()                  # plik znika...
    assert lo.load_calibration() == (1.05, 0.95), "cache nie zadzialal"


def test_invalidate_cache_wymusza_ponowny_odczyt(plik_kalibracji):
    """Bez tego joby licza na starych wspolczynnikach az do restartu procesu."""
    lo.save_calibration(bias_h=1.05, bias_a=0.95, n_matches=200)
    lo.load_calibration()

    plik_kalibracji.write_text(
        json.dumps({"factor_home": 1.10, "factor_away": 0.90}), encoding="utf-8")
    lo.invalidate_cache()

    assert lo.load_calibration() == (1.10, 0.90)


def test_zapis_sam_uniewaznia_cache(plik_kalibracji):
    lo.save_calibration(bias_h=1.05, bias_a=0.95, n_matches=200)
    lo.load_calibration()

    lo.save_calibration(bias_h=1.10, bias_a=0.90, n_matches=200)
    assert lo.load_calibration() == (1.10, 0.90), "zapis nie uniewaznil cache"


# ── save_calibration: safety rail ───────────────────────────────────────────

def test_zapis_przycina_wartosc_za_wysoka(plik_kalibracji):
    """SEDNO: dziwny przebieg walk-forward nie moze rozjechac wszystkich predykcji."""
    wynik = lo.save_calibration(bias_h=2.50, bias_a=1.0, n_matches=200)

    assert wynik["factor_home"] == lo.CAL_MAX
    assert wynik["clamped_home"] is True
    assert wynik["bias_raw_home"] == 2.5, "surowa wartosc ma zostac w pliku do diagnostyki"


def test_zapis_przycina_wartosc_za_niska(plik_kalibracji):
    wynik = lo.save_calibration(bias_h=1.0, bias_a=0.20, n_matches=200)
    assert wynik["factor_away"] == lo.CAL_MIN
    assert wynik["clamped_away"] is True


def test_wartosc_w_normie_nieprzycinana(plik_kalibracji):
    wynik = lo.save_calibration(bias_h=1.02, bias_a=0.98, n_matches=200)
    assert wynik["factor_home"] == 1.02
    assert wynik["clamped_home"] is False and wynik["clamped_away"] is False


def test_zapis_ma_metadane_do_audytu(plik_kalibracji):
    wynik = lo.save_calibration(bias_h=1.01, bias_a=0.99, n_matches=150, acc_1x2=54.321)

    assert wynik["n_matches"] == 150
    assert wynik["acc_1x2_pct"] == 54.32
    assert wynik["safety_rail"] == [lo.CAL_MIN, lo.CAL_MAX]
    assert wynik["updated_at"].endswith("Z")


def test_brak_accuracy_zapisany_jako_none(plik_kalibracji):
    assert lo.save_calibration(1.0, 1.0, 100)["acc_1x2_pct"] is None


def test_zapis_tworzy_katalog(plik_kalibracji):
    assert not plik_kalibracji.parent.exists()
    lo.save_calibration(1.0, 1.0, 100)
    assert plik_kalibracji.exists()


# ── _lambda_from_hist ───────────────────────────────────────────────────────

def test_lambda_gospodarza_z_goli_domowych():
    hist = _hist(*[("Legia", "X", 2, 0) for _ in range(6)])
    assert lo._lambda_from_hist(hist, "Legia", as_home=True) == 2.0


def test_lambda_goscia_z_goli_wyjazdowych():
    """Strona ma znaczenie — pomylka odwraca sile atakow."""
    hist = _hist(*[("X", "Lech", 0, 3) for _ in range(6)])
    assert lo._lambda_from_hist(hist, "Lech", as_home=False) == 3.0


def test_za_malo_meczow_daje_none():
    hist = _hist(*[("Legia", "X", 2, 0) for _ in range(lo.MIN_HIST - 1)])
    assert lo._lambda_from_hist(hist, "Legia", as_home=True) is None


def test_bierze_ostatnie_n_meczow():
    stare = [("Legia", "X", 0, 0) for _ in range(10)]
    nowe = [("Legia", "X", 4, 0) for _ in range(10)]
    hist = _hist(*stare, *nowe)
    assert lo._lambda_from_hist(hist, "Legia", as_home=True, n=10) == 4.0


def test_nieznana_druzyna_daje_none():
    hist = _hist(("Legia", "Lech", 1, 1))
    assert lo._lambda_from_hist(hist, "Nieistniejacy", as_home=True) is None


# ── _forma ──────────────────────────────────────────────────────────────────

def test_forma_liczy_punkty_z_obu_stron():
    """Wygrana u siebie i na wyjezdzie warta tyle samo — 3 pkt."""
    hist = _hist(("Legia", "A", 2, 0), ("B", "Legia", 0, 1))
    assert lo._forma(hist, "Legia") == 3.0


def test_forma_remis_to_punkt():
    hist = _hist(("Legia", "A", 1, 1), ("B", "Legia", 2, 2))
    assert lo._forma(hist, "Legia") == 1.0


def test_forma_porazka_to_zero():
    hist = _hist(("Legia", "A", 0, 3), ("B", "Legia", 2, 0))
    assert lo._forma(hist, "Legia") == 0.0


def test_forma_bez_meczow_daje_neutralne():
    """Brak historii = 1.0, czyli korekta formy nic nie zmienia."""
    assert lo._forma(_hist(("A", "B", 1, 0)), "Nieznany") == 1.0


def test_forma_bierze_ostatnie_n():
    stare = [("Legia", "X", 5, 0) for _ in range(5)]
    nowe = [("Legia", "X", 0, 5) for _ in range(5)]
    assert lo._forma(_hist(*stare, *nowe), "Legia", n=5) == 0.0


# ── _predict_lambdas ────────────────────────────────────────────────────────

def _hist_dla_pary(gole_dom=2, gole_wyj=1, n=8):
    mecze = [("Legia", f"R{i}", gole_dom, 0) for i in range(n)]
    mecze += [(f"S{i}", "Lech", 0, gole_wyj) for i in range(n)]
    return _hist(*mecze)


def test_predykcja_zwraca_pare_lambd():
    wynik = lo._predict_lambdas(_hist_dla_pary(), "Legia", "Lech")
    assert wynik is not None
    lh, la = wynik
    assert lh > 0 and la > 0


def test_brak_historii_gospodarza_daje_none():
    hist = _hist(*[("S", "Lech", 0, 1) for _ in range(8)])
    assert lo._predict_lambdas(hist, "Legia", "Lech") is None


def test_brak_historii_goscia_daje_none():
    hist = _hist(*[("Legia", "R", 2, 0) for _ in range(8)])
    assert lo._predict_lambdas(hist, "Legia", "Lech") is None


def test_lepsza_forma_gospodarza_podnosi_jego_lambde():
    """Korekta formy: zespol w formie ma dostac WYZSZA lambde niz baza."""
    baza = _hist_dla_pary()
    lh_baza, _ = lo._predict_lambdas(baza, "Legia", "Lech")

    # Legia wygrywa wszystko, Lech przegrywa wszystko
    forma = _hist(
        *[("Legia", f"R{i}", 3, 0) for i in range(8)],
        *[(f"S{i}", "Lech", 3, 1) for i in range(8)],
    )
    lh_forma, _ = lo._predict_lambdas(forma, "Legia", "Lech")

    assert lh_forma > lh_baza


def test_korekta_formy_ograniczona():
    """Skrajna roznica formy nie moze rozjechac lambd — korekta ma twarde limity."""
    skrajne = _hist(
        *[("Legia", f"R{i}", 5, 0) for i in range(10)],
        *[(f"S{i}", "Lech", 5, 1) for i in range(10)],
    )
    lh, la = lo._predict_lambdas(skrajne, "Legia", "Lech")
    baza_lh = 5.0

    assert lh <= baza_lh * 1.4 + 0.01, "korekta przekroczyla gorny limit 1.4"
    assert la >= 1.0 / 1.4 - 0.01, "korekta przekroczyla dolny limit"


# ── injury_correction ───────────────────────────────────────────────────────

def _kontuzja(pozycja="F", **kw) -> dict:
    return {"position": pozycja, **kw}


def test_brak_kontuzji_nie_zmienia_lambdy():
    assert lo.injury_correction(1.5, [], is_home=True) == 1.5


def test_kara_ograniczona_twardym_limitem():
    """Nawet cala druzyna na kontuzjach nie moze zjechac ponizej -20%."""
    wielu = [_kontuzja("F") for _ in range(20)]
    wynik = lo.injury_correction(2.0, wielu, is_home=True)
    assert wynik >= 2.0 * (1 - lo._CAP) - 0.001
