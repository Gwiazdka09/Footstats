"""test_lambda_run_calibration.py — walk-forward liczący kalibrację λ.

PO CO: `run_calibration` przechodzi po historii mecz po meczu, przewiduje λ
i porównuje z tym, co faktycznie padło. Z tego wychodzi bias, który potem mnoży
KAŻDĄ przyszłą predykcję. Trzy rzeczy muszą trzymać:

  * BRAK LOOKAHEADU. Predykcja meczu z 10.03 nie może widzieć wyników z 10.03
    ani późniejszych. Gdyby widziała, bias policzyłby się z wiedzy o przyszłości
    i wyszedłby zbyt optymistyczny — model wyglądałby na dobrze skalibrowany,
    a w produkcji byłby przesunięty. To najcichszy możliwy błąd w całym
    projekcie: nic nie wybucha, liczby wyglądają dobrze, pieniądze znikają.
  * PRÓG DANYCH. Kalibracja z 12 meczów to szum podniesiony do rangi parametru.
    Poniżej `MIN_MATCHES_FOR_CAL` funkcja ma ODMÓWIĆ i nic nie zapisać.
  * BRAK DANYCH / ZŁE KOLUMNY nie mogą wywalić procesu ani nadpisać dobrej
    kalibracji czymkolwiek.

UWAGA: `run_calibration` zapisuje do data/model_calibration.json. Tutaj ścieżka
jest przekierowana na katalog tymczasowy.
"""
from __future__ import annotations

import pandas as pd
import pytest

import footstats.core.lambda_optimizer as lo


@pytest.fixture(autouse=True)
def _izolacja(tmp_path, monkeypatch):
    """Kalibracja do tmp, cache czyszczony, wyjście wyciszone."""
    monkeypatch.setattr(lo, "CALIBRATION_PATH", tmp_path / "kal.json")
    lo.invalidate_cache()
    yield
    lo.invalidate_cache()


def _dane(n: int = 200, gole_g: int = 2, gole_a: int = 1) -> pd.DataFrame:
    """Historia n meczów, kolejne dni, 4 drużyny w rotacji."""
    druzyny = ["Legia", "Lech", "Wisla", "Rakow"]
    wiersze = []
    for i in range(n):
        wiersze.append({
            "home": druzyny[i % 4],
            "away": druzyny[(i + 1) % 4],
            "hg": gole_g,
            "ag": gole_a,
            "result": "H" if gole_g > gole_a else ("D" if gole_g == gole_a else "A"),
            "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
        })
    return pd.DataFrame(wiersze)


@pytest.fixture
def loader(monkeypatch):
    """Podstawia `load_cached`; zwraca uchwyt do ustawienia danych."""
    stan = {"df": _dane()}
    import footstats.data.historical_loader as hl
    monkeypatch.setattr(hl, "load_cached", lambda *a, **k: stan["df"])
    return stan


# ── brak danych / złe dane ──────────────────────────────────────────────────

def test_brak_historii_nie_zapisuje_kalibracji(loader):
    """Pusta historia nie może nadpisać dobrej kalibracji zerami."""
    loader["df"] = pd.DataFrame()

    assert lo.run_calibration(verbose=False) == {}
    assert lo.load_calibration() == (1.0, 1.0)


def test_brakujace_kolumny_przerywaja(loader):
    loader["df"] = pd.DataFrame({"home": ["Legia"], "away": ["Lech"]})

    assert lo.run_calibration(verbose=False) == {}


def test_polskie_nazwy_kolumn_obslugiwane(loader):
    """Loader oddaje kolumny po polsku — bez mapowania walk-forward nie ruszy."""
    df = _dane()
    loader["df"] = df.rename(columns={
        "home": "gospodarz", "away": "goscie", "hg": "gole_g",
        "ag": "gole_a", "result": "wynik", "date": "data"})

    wynik = lo.run_calibration(verbose=False)

    assert "error" not in wynik
    assert wynik["n_matches"] > 0


# ── próg danych ─────────────────────────────────────────────────────────────

def test_za_malo_meczow_to_odmowa(loader, monkeypatch):
    """Kalibracja z 12 meczów to szum podniesiony do rangi parametru."""
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: (1.5, 1.0))
    loader["df"] = _dane(n=60)

    wynik = lo.run_calibration(n_matches=10, verbose=False)

    assert wynik["error"] == "insufficient_data"
    assert wynik["n_used"] < lo.MIN_MATCHES_FOR_CAL


def test_odmowa_nie_zapisuje_kalibracji(loader, monkeypatch):
    """Najważniejsze: odmowa ma zostawić poprzednią kalibrację nietkniętą."""
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: (1.5, 1.0))
    lo.save_calibration(1.10, 0.90, n_matches=500)
    loader["df"] = _dane(n=60)

    lo.run_calibration(n_matches=10, verbose=False)

    assert lo.load_calibration() == (1.10, 0.90)


def test_mecze_bez_predykcji_nie_licza_sie(loader, monkeypatch):
    """Mecz, dla którego model nie ma dość historii, nie może wejść do biasu."""
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: None)

    assert lo.run_calibration(verbose=False)["n_used"] == 0


# ── bias ────────────────────────────────────────────────────────────────────

def test_bias_ze_stosunku_rzeczywistych_do_przewidzianych(loader, monkeypatch):
    """Model przewiduje 1.0, pada 1.0 → bias 1.0, czyli brak korekty."""
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: (1.0, 1.0))
    loader["df"] = _dane(n=200, gole_g=1, gole_a=1)

    wynik = lo.run_calibration(verbose=False)

    assert wynik["bias_raw_home"] == pytest.approx(1.0, abs=0.01)
    assert wynik["bias_raw_away"] == pytest.approx(1.0, abs=0.01)


def test_model_niedoszacowujacy_daje_bias_powyzej_jeden(loader, monkeypatch):
    """Pada 2 gole, model mówi 1 → bias 2.0, obcięty railem do 1.15."""
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: (1.0, 1.0))
    loader["df"] = _dane(n=200, gole_g=2, gole_a=2)

    wynik = lo.run_calibration(verbose=False)

    assert wynik["bias_raw_home"] == pytest.approx(2.0, abs=0.01)
    assert wynik["factor_home"] == lo.CAL_MAX
    assert wynik["clamped_home"] is True


def test_wynik_zapisany_i_odczytywalny(loader, monkeypatch):
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: (2.0, 1.0))
    loader["df"] = _dane(n=200, gole_g=2, gole_a=1)

    lo.run_calibration(verbose=False)

    assert lo.load_calibration() == (1.0, 1.0)


def test_liczba_uzytych_meczow_raportowana(loader, monkeypatch):
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: (1.5, 1.0))

    wynik = lo.run_calibration(n_matches=80, verbose=False)

    # UWAGA na niespojnosc API: payload SUKCESU niesie `n_matches`, a `n_used`
    # pojawia sie WYLACZNIE w odpowiedzi odmownej ({"n_used": N, "error": ...}).
    assert wynik["n_matches"] == 80
    assert "n_used" not in wynik


def test_skutecznosc_1x2_policzona(loader, monkeypatch):
    """Model typuje 1 (λ 2.0 vs 0.5), w danych same wygrane gospodarza → 100%."""
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: (2.0, 0.5))
    loader["df"] = _dane(n=200, gole_g=3, gole_a=0)

    assert lo.run_calibration(verbose=False)["acc_1x2_pct"] == pytest.approx(100.0)


def test_mecze_bez_goli_pomijane(loader, monkeypatch):
    """Wiersz z NaN w golach to brak danych, nie remis 0-0."""
    monkeypatch.setattr(lo, "_predict_lambdas", lambda h, g, a: (1.5, 1.0))
    df = _dane(n=200)
    df.loc[df.index[-50:], "hg"] = None
    loader["df"] = df

    assert lo.run_calibration(n_matches=100, verbose=False)["n_matches"] == 50


# ── BRAK LOOKAHEADU ─────────────────────────────────────────────────────────

def test_predykcja_nie_widzi_meczu_ktory_przewiduje(loader, monkeypatch):
    """Historia podana modelowi musi kończyć się PRZED datą przewidywanego meczu.

    Gdyby zawierała ten mecz (albo późniejsze), bias policzyłby się z wiedzy
    o przyszłości: model wyglądałby na dobrze skalibrowany, a w produkcji byłby
    przesunięty. Nic by przy tym nie wybuchło.
    """
    naruszenia = []
    daty_wywolan = []

    def szpieg(hist, home, away):
        # `run_calibration` iteruje po `df_wf` w kolejności dat, wiec data
        # biezacego meczu to kolejna data z ogona zbioru.
        daty_wywolan.append(len(hist))
        if not hist.empty:
            naruszenia.append((hist["date"].max(), len(hist)))
        return (1.5, 1.0)

    monkeypatch.setattr(lo, "_predict_lambdas", szpieg)
    df = _dane(n=200)
    loader["df"] = df

    lo.run_calibration(n_matches=50, verbose=False)

    # Historia rośnie monotonicznie i zaczyna się od 150 (200 - 50 ostatnich).
    assert daty_wywolan == sorted(daty_wywolan), "historia nie rośnie w czasie"
    assert daty_wywolan[0] == 150

    # Dla każdego wywołania: ostatnia data w historii < data przewidywanego meczu.
    daty_meczow = list(df["date"].iloc[150:])
    for (max_hist, _), data_meczu in zip(naruszenia, daty_meczow):
        assert max_hist < data_meczu, (
            f"historia sięga {max_hist}, a przewidywany mecz jest {data_meczu} — lookahead")


def test_historia_rosnie_o_jeden_mecz_na_krok(loader, monkeypatch):
    """Walk-forward: każdy kolejny mecz dokłada dokładnie jeden do historii."""
    rozmiary = []
    monkeypatch.setattr(lo, "_predict_lambdas",
                        lambda h, g, a: (rozmiary.append(len(h)), (1.5, 1.0))[1])
    loader["df"] = _dane(n=200)

    lo.run_calibration(n_matches=30, verbose=False)

    przyrosty = {b - a for a, b in zip(rozmiary, rozmiary[1:])}
    assert przyrosty == {1}
