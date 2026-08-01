"""test_form_sila.py — siła drużyn i forma: wagi czasowe, atak/obrona.

PO CO: `_oblicz_sile_wazona` zamienia historię meczów na wskaźniki ataku i obrony
używane potem przez model. Trzy własności muszą trzymać, bo błąd w nich nie
wywala niczego, tylko przekrzywia każdą predykcję:

  * WAGI CZASOWE. Trzy ostatnie mecze ważą 1.5, kolejne cztery 1.0, starsze 0.5.
    Odwrócenie kolejności (najstarsze jako najświeższe) dałoby wskaźniki oparte
    na formie sprzed pół roku — i wyglądałoby zupełnie normalnie.
  * STRONA MECZU. Dla gospodarza „strzelone" to `gole_g`, dla gościa `gole_a`.
    Zamiana tych pól odwraca atak z obroną, czyli zamienia najlepszą drużynę
    w najgorszą.
  * NORMALIZACJA do średniej ligowej — atak 1.0 znaczy „przeciętny". Bez tego
    liczby z lig o różnej liczbie goli nie dają się porównywać.

`_opponent_adjust` (korekta o trudność terminarza) jest za flagą i domyślnie
WYŁĄCZONA — testy pilnują, że domyślnie nic nie zmienia.
"""
from __future__ import annotations

import pandas as pd
import pytest

import footstats.core.form as fm


def _mecze(wiersze: list[tuple]) -> pd.DataFrame:
    """(gospodarz, goscie, gole_g, gole_a, dzien) → DataFrame."""
    return pd.DataFrame([
        {"gospodarz": g, "goscie": a, "gole_g": gg, "gole_a": ga,
         "data": pd.Timestamp("2026-01-01") + pd.Timedelta(days=d)}
        for g, a, gg, ga, d in wiersze
    ])


# ── _wagi_mecze ─────────────────────────────────────────────────────────────

def test_trzy_najnowsze_waza_najwiecej():
    """Kolejność liczona OD KOŃCA — ostatni wiersz to najświeższy mecz."""
    df = _mecze([("A", "B", 1, 0, i) for i in range(10)])

    wagi = list(fm._wagi_mecze(df))

    assert wagi[-3:] == [1.5, 1.5, 1.5]


def test_srodkowe_mecze_waga_jeden():
    df = _mecze([("A", "B", 1, 0, i) for i in range(10)])

    assert list(fm._wagi_mecze(df))[-7:-3] == [1.0, 1.0, 1.0, 1.0]


def test_najstarsze_waza_najmniej():
    df = _mecze([("A", "B", 1, 0, i) for i in range(10)])

    assert list(fm._wagi_mecze(df))[:3] == [0.5, 0.5, 0.5]


def test_wagi_malejace_w_czasie():
    """Świeższy mecz nigdy nie może ważyć mniej niż starszy."""
    df = _mecze([("A", "B", 1, 0, i) for i in range(12)])

    wagi = list(fm._wagi_mecze(df))

    assert all(a <= b for a, b in zip(wagi, wagi[1:]))


def test_krotka_historia_same_wysokie_wagi():
    df = _mecze([("A", "B", 1, 0, i) for i in range(2)])

    assert list(fm._wagi_mecze(df)) == [1.5, 1.5]


def test_pusta_historia_nie_wywala():
    assert len(fm._wagi_mecze(_mecze([]))) == 0


# ── _oblicz_sile_wazona: strona meczu ──────────────────────────────────────

def test_atak_gospodarza_z_goli_gospodarza():
    """Dla gospodarza strzelone to `gole_g` — zamiana odwróciłaby atak z obroną."""
    df = _mecze([("A", "B", 3, 0, i) for i in range(8)])

    sily, srednia = fm._oblicz_sile_wazona(df)

    assert sily["A"]["gole_sr"] == pytest.approx(3.0)
    assert sily["A"]["strac_sr"] == pytest.approx(0.0)


def test_atak_goscia_z_goli_goscia():
    df = _mecze([("A", "B", 0, 2, i) for i in range(8)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["B"]["gole_sr"] == pytest.approx(2.0)
    assert sily["B"]["strac_sr"] == pytest.approx(0.0)


def test_druzyna_grajaca_obie_strony():
    """Wskaźnik łączy dom i wyjazd ważąc liczbą meczów po każdej stronie."""
    df = _mecze([("A", "B", 2, 0, 1), ("C", "A", 0, 4, 2)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["A"]["gole_sr"] == pytest.approx(3.0)


# ── normalizacja ────────────────────────────────────────────────────────────

def test_atak_jeden_to_druzyna_przecietna():
    """Wszyscy strzelają tyle samo → każdy ma atak dokładnie 1.0."""
    df = _mecze([("A", "B", 1, 1, 1), ("B", "A", 1, 1, 2),
                 ("C", "D", 1, 1, 3), ("D", "C", 1, 1, 4)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert all(s["atak"] == pytest.approx(1.0) for s in sily.values())


def test_lepszy_atak_daje_wyzszy_wskaznik():
    df = _mecze([("A", "B", 4, 0, 1), ("B", "A", 0, 4, 2),
                 ("C", "D", 1, 1, 3), ("D", "C", 1, 1, 4)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["A"]["atak"] > sily["C"]["atak"]
    assert sily["A"]["obrona"] < sily["C"]["obrona"], "mniej straconych = niższy wskaźnik"


def test_liczba_meczow_raportowana():
    df = _mecze([("A", "B", 1, 0, 1), ("C", "A", 0, 1, 2), ("A", "D", 2, 1, 3)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["A"]["mecze"] == 3


# ── forma punktowa ──────────────────────────────────────────────────────────

def test_same_zwyciestwa_to_maksymalna_forma():
    df = _mecze([("A", "B", 2, 0, i) for i in range(5)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["A"]["forma_pkt"] == pytest.approx(3.0)


def test_same_porazki_to_zerowa_forma():
    df = _mecze([("A", "B", 0, 2, i) for i in range(5)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["A"]["forma_pkt"] == pytest.approx(0.0)


def test_same_remisy_to_punkt():
    df = _mecze([("A", "B", 1, 1, i) for i in range(5)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["A"]["forma_pkt"] == pytest.approx(1.0)


def test_remis_liczony_z_perspektywy_goscia():
    """Gość wygrywa, gdy `gole_a > gole_g` — odwrotnie niż gospodarz."""
    df = _mecze([("A", "B", 0, 3, i) for i in range(5)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["B"]["forma_pkt"] == pytest.approx(3.0)
    assert sily["A"]["forma_pkt"] == pytest.approx(0.0)


def test_swieza_forma_wazy_wiecej_niz_stara():
    """Cztery porażki, potem trzy zwycięstwa: waga 1.5 na świeżych ma dać
    formę POWYŻEJ prostej średniej (3*3)/(7) = 1.29."""
    df = _mecze([("A", "B", 0, 2, i) for i in range(4)]
                + [("A", "B", 2, 0, 4 + i) for i in range(3)])

    sily, _ = fm._oblicz_sile_wazona(df)

    assert sily["A"]["forma_pkt"] > 1.29


# ── korekta o trudność terminarza (za flagą) ───────────────────────────────

def test_korekta_domyslnie_wylaczona(monkeypatch):
    monkeypatch.delenv("SCHEDULE_ADJUSTED_RATINGS", raising=False)

    assert fm._schedule_adj_on() is False


@pytest.mark.parametrize("wartosc", ["1", "true", "TRUE", "yes", " 1 "])
def test_flaga_wlacza_korekte(monkeypatch, wartosc):
    monkeypatch.setenv("SCHEDULE_ADJUSTED_RATINGS", wartosc)

    assert fm._schedule_adj_on() is True


@pytest.mark.parametrize("wartosc", ["0", "false", "nie", ""])
def test_inne_wartosci_nie_wlaczaja(monkeypatch, wartosc):
    monkeypatch.setenv("SCHEDULE_ADJUSTED_RATINGS", wartosc)

    assert fm._schedule_adj_on() is False


def test_korekta_nie_mutuje_wejscia():
    """Zwracany jest NOWY słownik — mutacja psułaby wywołującego."""
    df = _mecze([("A", "B", 2, 0, 1), ("B", "A", 1, 1, 2)])
    sily, srednia = fm._oblicz_sile_wazona(df)
    kopia = {d: dict(v) for d, v in sily.items()}

    fm._opponent_adjust(df, sily, srednia)

    assert sily == kopia


def test_gole_przeciw_silnej_obronie_podnosza_atak():
    """Sedno korekty: trafienie mocnej obronie ma ważyć więcej niż słabej."""
    df = _mecze([("A", "Mocny", 2, 0, 1), ("B", "Slaby", 2, 0, 2)])
    sily = {
        "A": {"atak": 1.0, "obrona": 1.0}, "B": {"atak": 1.0, "obrona": 1.0},
        "Mocny": {"atak": 1.0, "obrona": 0.5}, "Slaby": {"atak": 1.0, "obrona": 2.0},
    }

    out = fm._opponent_adjust(df, sily, 1.0)

    assert out["A"]["atak"] > out["B"]["atak"]


def test_rywal_spoza_slownika_jest_neutralny():
    """Brak rywala w rankingu nie może wywalić korekty ani jej wypaczyć."""
    df = _mecze([("A", "Nieznany", 2, 0, 1)])
    sily = {"A": {"atak": 1.0, "obrona": 1.0}}

    out = fm._opponent_adjust(df, sily, 1.0)

    assert out["A"]["atak"] == pytest.approx(2.0)


def test_zerowa_sila_rywala_nie_dzieli_przez_zero():
    df = _mecze([("A", "Zero", 2, 0, 1)])
    sily = {"A": {"atak": 1.0, "obrona": 1.0}, "Zero": {"atak": 0.0, "obrona": 0.0}}

    out = fm._opponent_adjust(df, sily, 1.0)

    assert out["A"]["atak"] == pytest.approx(2.0)


# ── pobierz_forme ───────────────────────────────────────────────────────────

def test_forma_laczy_dom_i_wyjazd():
    df = _mecze([("A", "B", 1, 0, 1), ("C", "A", 0, 2, 2)])

    forma = fm.pobierz_forme("A", df)

    assert len(forma) == 2
    assert set(forma["miejsce"]) == {"Dom", "Wyjazd"}


def test_forma_oznacza_wynik_z_perspektywy_druzyny():
    """Ten sam mecz to wygrana dla jednej drużyny i porażka dla drugiej."""
    df = _mecze([("A", "B", 3, 1, 1)])

    assert fm.pobierz_forme("A", df)["wynik"].iloc[0] == "W"
    assert fm.pobierz_forme("B", df)["wynik"].iloc[0] == "P"


def test_forma_przypisuje_strzelone_wlasciwej_stronie():
    df = _mecze([("A", "B", 3, 1, 1)])

    assert fm.pobierz_forme("B", df)["strzelone"].iloc[0] == 1
    assert fm.pobierz_forme("B", df)["stracone"].iloc[0] == 3


def test_forma_ograniczona_do_n_ostatnich():
    df = _mecze([("A", "B", 1, 0, i) for i in range(20)])

    assert len(fm.pobierz_forme("A", df, n=5)) == 5


def test_forma_posortowana_po_dacie():
    df = _mecze([("A", "B", 1, 0, 5), ("A", "C", 2, 0, 1), ("A", "D", 3, 0, 3)])

    daty = list(fm.pobierz_forme("A", df)["data"])

    assert daty == sorted(daty)


def test_forma_nieznanej_druzyny_jest_pusta():
    df = _mecze([("A", "B", 1, 0, 1)])

    assert fm.pobierz_forme("Nieznany", df).empty
