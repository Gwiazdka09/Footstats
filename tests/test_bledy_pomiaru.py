"""test_bledy_pomiaru.py — testy dla src/footstats/core/bledy_pomiaru.py.

PO CO: 26.08 dwa razy odczytaliśmy gołą tabelę kubełków kalibracji
(deklarowane % vs trafione %, bez błędu standardowego) jako "model jest źle
wyskalowany". Po dołożeniu błędu okazało się, że wszystkie odchylenia mieszczą
się poniżej 2 SE, a test na całej próbie daje |z| < 1.3 dla każdego wyjścia.

Te testy pilnują dwóch rzeczy naraz:
  1. że funkcje liczą poprawnie (obciążenie, Wilson, kubełki, ECE);
  2. że przedział Wilsona NIE wybucha przy skrajnych proporcjach (0/n, n/n) —
     to jest dokładnie ten regres, który w prototypie dał fałszywe "4572 SE".
"""
from __future__ import annotations

import math

import pytest

# UWAGA na nazewnictwo: funkcja produkcyjna nazywa się `sprawdz_obciazenie`, a nie
# `test_obciazenia`, celowo. Pytest kolekcjonuje każdą nazwę `test_*` widoczną w pliku
# testowym — także zaimportowaną — i próbowałby uruchomić funkcję produkcyjną jako test,
# wywalając się na "fixture 'pary' not found". Nie nazywaj tak funkcji w `src/`.
from footstats.core.bledy_pomiaru import ece, kubelki_z_bledem, przedzial_wilsona
from footstats.core.bledy_pomiaru import sprawdz_obciazenie


# --- sprawdz_obciazenie -------------------------------------------------------


def test_obciazenia_model_idealny_nie_jest_istotny() -> None:
    """Model idealny (p = faktyczna częstość) → |z| małe, nieistotne."""
    # 200 par: p=0.5, połowa zaszła (y=1), połowa nie (y=0) — idealna kalibracja.
    pary = [(0.5, 1) for _ in range(100)] + [(0.5, 0) for _ in range(100)]
    wynik = sprawdz_obciazenie(pary)
    assert wynik is not None
    assert abs(wynik["z"]) < 1.3
    assert wynik["istotne"] is False
    assert wynik["n"] == 200


def test_obciazenia_model_zanizajacy_jest_istotny() -> None:
    """Model deklaruje 0.2, a zdarzenie zachodzi w 50% przy n=200 → istotne, dodatnie."""
    pary = [(0.2, 1) for _ in range(100)] + [(0.2, 0) for _ in range(100)]
    wynik = sprawdz_obciazenie(pary)
    assert wynik is not None
    assert wynik["istotne"] is True
    assert wynik["roznica_pp"] > 0
    assert wynik["p_value"] < 0.05


def test_obciazenia_pusta_lista_zwraca_none() -> None:
    """Brak danych → nie ma czego testować."""
    assert sprawdz_obciazenie([]) is None


def test_obciazenia_wszystkie_p_jeden_zwraca_none_bez_dzielenia_przez_zero() -> None:
    """Wariancja = 0 (wszystkie p dokładnie 1.0) → None, żadnego ZeroDivisionError/inf."""
    pary = [(1.0, 1) for _ in range(20)]
    assert sprawdz_obciazenie(pary) is None


# --- przedzial_wilsona -------------------------------------------------------


def test_wilson_zero_trafien_daje_dodatnia_szerokosc_i_dolna_granice_nieujemna() -> None:
    """0/10 trafień: naiwne SE=0 → tu przedział musi mieć dodatnią szerokość."""
    dol, gora = przedzial_wilsona(0, 10)
    assert gora > dol
    assert dol >= 0.0


def test_wilson_wszystkie_trafienia_daje_dodatnia_szerokosc_i_gorna_granice_nieprzekraczajaca_jeden() -> None:
    """10/10 trafień: naiwne SE=0 → tu przedział musi mieć dodatnią szerokość."""
    dol, gora = przedzial_wilsona(10, 10)
    assert gora > dol
    assert gora <= 1.0


def test_wilson_n_zero_zwraca_pelny_zakres() -> None:
    """Brak obserwacji → nie wiemy nic, cały zakres [0, 1]."""
    assert przedzial_wilsona(0, 0) == (0.0, 1.0)


def test_wilson_zawiera_obserwowana_proporcje_dla_przypadku_typowego() -> None:
    """Przedział ufności musi obejmować samą obserwowaną proporcję."""
    trafienia, n = 55, 100
    dol, gora = przedzial_wilsona(trafienia, n)
    p_obs = trafienia / n
    assert dol <= p_obs <= gora


def test_wilson_antyregresja_n5_5z5_deklarowane_85_procent_miesci_sie_w_przedziale() -> None:
    """
    ANTYREGRESJA: n=5, trafienia=5/5, deklarowane=0.85.

    To jest dokładnie ten wiersz z prototypu, który dał fałszywe "4572 SE"
    (naiwne SE=0 przy 100% trafień, więc (1.0 - 0.85) / 0 -> wybuch). Wilson
    przy n=5 ma być SZEROKI, więc 0.85 musi się w nim mieścić, a wynik ma
    być skończony i sensowny (nie inf, nie NaN).
    """
    dol, gora = przedzial_wilsona(5, 5)
    assert math.isfinite(dol)
    assert math.isfinite(gora)
    assert dol <= 0.85 <= gora
    assert 0.0 <= dol < gora <= 1.0


# --- kubelki_z_bledem -------------------------------------------------------


def _pary_kalibrowane(p: float, n: int) -> list[tuple[float, int]]:
    """Pomocnik: n par o deklarowanym p, gdzie trafia dokładnie round(p*n) z nich."""
    trafienia = round(p * n)
    return [(p, 1) for _ in range(trafienia)] + [(p, 0) for _ in range(n - trafienia)]


def test_kubelki_ponizej_min_n_znikaja() -> None:
    """Kubełek z liczebnością < min_n nie ma prawa pojawić się w wyniku."""
    pary = [(0.15, 1), (0.15, 0), (0.15, 1)]  # 3 obserwacje w kubełku 10-20%
    wynik = kubelki_z_bledem(pary, szerokosc=10, min_n=5)
    assert wynik == []


def test_kubelki_p_jeden_ladu_w_ostatnim_kubelku() -> None:
    """p=1.0 to skrajny przypadek — musi trafić do 90-100%, nie do 100-110%."""
    pary = _pary_kalibrowane(0.95, 10) + [(1.0, 1) for _ in range(6)]
    wynik = kubelki_z_bledem(pary, szerokosc=10, min_n=5)
    zakresy = [(b["zakres_od_pct"], b["zakres_do_pct"]) for b in wynik]
    assert (90, 100) in zakresy
    # w kubełku 90-100 muszą być obie grupy: p=0.95 (10 szt) i p=1.0 (6 szt)
    ostatni = next(b for b in wynik if b["zakres_od_pct"] == 90)
    assert ostatni["n"] == 16


def test_kubelki_poza_przedzialem_false_gdy_zgodne() -> None:
    """Deklarowane zgadza się z trafionym → poza_przedzialem False."""
    pary = _pary_kalibrowane(0.5, 100)
    wynik = kubelki_z_bledem(pary, szerokosc=10, min_n=5)
    kubelek = next(b for b in wynik if b["zakres_od_pct"] == 50)
    assert kubelek["poza_przedzialem"] is False


def test_kubelki_poza_przedzialem_true_gdy_deklarowane_daleko_od_trafionego() -> None:
    """Deklarowane 0.55 (środek kubełka 50-60), trafiono 5% przy dużym n → poza przedziałem."""
    n = 300
    trafienia = 15  # 5% z n=300, mocno rozjechane z deklarowanym 0.55
    pary = [(0.55, 1) for _ in range(trafienia)] + [(0.55, 0) for _ in range(n - trafienia)]
    wynik = kubelki_z_bledem(pary, szerokosc=10, min_n=5)
    kubelek = next(b for b in wynik if b["zakres_od_pct"] == 50)
    assert kubelek["poza_przedzialem"] is True


def test_kubelki_posortowane_rosnaco_po_zakres_od() -> None:
    """Kolejność zwróconych kubełków ma być rosnąca po dolnej granicy zakresu."""
    pary = (
        _pary_kalibrowane(0.85, 20)
        + _pary_kalibrowane(0.15, 20)
        + _pary_kalibrowane(0.55, 20)
    )
    wynik = kubelki_z_bledem(pary, szerokosc=10, min_n=5)
    zakresy = [b["zakres_od_pct"] for b in wynik]
    assert zakresy == sorted(zakresy)


# --- ece ---------------------------------------------------------------------


def test_ece_model_idealny_bliskie_zera() -> None:
    """Model idealnie skalibrowany w każdym kubełku → ECE bliskie 0."""
    pary = (
        _pary_kalibrowane(0.15, 50)
        + _pary_kalibrowane(0.55, 50)
        + _pary_kalibrowane(0.85, 50)
    )
    wynik = ece(pary, szerokosc=10)
    assert wynik is not None
    assert wynik < 0.02


def test_ece_model_przesuniety_o_stala() -> None:
    """Model deklaruje o 0.2 za dużo w każdym kubełku → ECE ≈ 0.2."""
    # deklarowane 0.7, ale faktycznie trafia 0.5 -> przesunięcie o 0.2
    trafienia = 50
    n = 100
    pary = [(0.7, 1) for _ in range(trafienia)] + [(0.7, 0) for _ in range(n - trafienia)]
    wynik = ece(pary, szerokosc=10)
    assert wynik is not None
    assert abs(wynik - 0.2) < 0.02


def test_ece_pusta_lista_zwraca_none() -> None:
    """Brak danych → None."""
    assert ece([]) is None


def test_ece_nie_stosuje_min_n_obejmuje_calosc() -> None:
    """Nawet mały kubełek (poniżej typowego min_n=5) ma wliczać się do ECE."""
    pary = [(0.5, 1), (0.5, 0), (0.5, 1)]  # tylko 3 obserwacje
    wynik = ece(pary, szerokosc=10)
    assert wynik is not None
    assert wynik >= 0.0


# --- przedzial_mediany -------------------------------------------------------

def test_przedzial_mediany_stalej_listy_jest_punktem() -> None:
    from footstats.core.bledy_pomiaru import przedzial_mediany
    dol, gora = przedzial_mediany([0.05] * 30)
    assert dol == pytest.approx(0.05)
    assert gora == pytest.approx(0.05)


def test_przedzial_mediany_zawiera_mediane() -> None:
    from statistics import median

    from footstats.core.bledy_pomiaru import przedzial_mediany
    dane = [i / 100.0 for i in range(40)]
    dol, gora = przedzial_mediany(dane)
    assert dol <= median(dane) <= gora


def test_przedzial_mediany_zweza_sie_gdy_probka_rosnie() -> None:
    """Sedno progu ze specu: przy malej probie przedzial ma byc szeroki, zeby
    '+2,3%' nie udawalo wyniku istotnego.

    UWAGA na konstrukcje: obie proby musza pochodzic z TEGO SAMEGO zakresu
    [0, 1]. Porownanie range(10)/100 z range(200)/100 mierzyloby rozciagniecie
    danych, nie niepewnosc — szerszy przedzial wyszedlby przy WIEKSZYM n."""
    from footstats.core.bledy_pomiaru import przedzial_mediany
    maly = przedzial_mediany([i / 9.0 for i in range(10)])
    duzy = przedzial_mediany([i / 199.0 for i in range(200)])
    assert (duzy[1] - duzy[0]) < (maly[1] - maly[0])


def test_przedzial_mediany_pustej_listy_zwraca_none() -> None:
    from footstats.core.bledy_pomiaru import przedzial_mediany
    assert przedzial_mediany([]) is None


def test_przedzial_mediany_malej_proby_daje_pelny_zakres() -> None:
    """Ponizej 6 obserwacji rangi schodza poza zakres proby — uczciwiej oddac
    caly zakres niz udawac przedzial."""
    from footstats.core.bledy_pomiaru import przedzial_mediany
    assert przedzial_mediany([0.01, 0.09, 0.05]) == (0.01, 0.09)


def test_przedzial_mediany_nie_wychodzi_poza_dane() -> None:
    """Rangi musza byc przyciete do [1, n] — inaczej indeks wyjdzie poza liste."""
    from footstats.core.bledy_pomiaru import przedzial_mediany
    dane = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    dol, gora = przedzial_mediany(dane)
    assert dol >= min(dane)
    assert gora <= max(dane)

