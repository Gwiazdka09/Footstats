"""
bledy_pomiaru.py — miary niepewności dla tabel kalibracji.

PO CO: 26.08 dwa razy odczytaliśmy gołą tabelę kubełków kalibracji
(deklarowane % vs trafione %) jako "model jest źle wyskalowany", bo tabela nie
niosła błędu standardowego. Po dołożeniu SE okazało się, że wszystkie
odchylenia mieszczą się poniżej 2 SE, a test na całej próbie daje |z| < 1.3 dla
każdego wyjścia.

Ten moduł to CZYSTE funkcje, zero dostępu do bazy, zero I/O — tylko `math`.
Wejściem jest zawsze `pary: list[tuple[float, int]]`, gdzie pierwszy element to
deklarowane prawdopodobieństwo (0–1), drugi to 0/1 czy zdarzenie zaszło.
"""
from __future__ import annotations

import math


def sprawdz_obciazenie(pary: list[tuple[float, int]]) -> dict | None:
    """
    Test czy model jest systematycznie obciążony na danym wyjściu.

    Cała próba naraz = 1 stopień swobody, więc dużo większa moc niż rozbicie
    na kubełki. Wariancja liczona jako suma p*(1-p) (przybliżenie
    Poisson-binomial rozkładem normalnym — uprawnione przy n rzędu setek).

    Zwraca None gdy `pary` jest puste albo wariancja wynosi 0 (wszystkie p to
    dokładnie 0 lub 1 — nie ma czego testować, bez dzielenia przez zero).
    """
    if not pary:
        return None

    n = len(pary)
    oczekiwane = sum(p for p, _ in pary)
    zaszlo = sum(y for _, y in pary)
    wariancja = sum(p * (1.0 - p) for p, _ in pary)

    if wariancja == 0.0:
        return None

    z = (zaszlo - oczekiwane) / math.sqrt(wariancja)
    p_value = math.erfc(abs(z) / math.sqrt(2.0))

    return {
        "n": n,
        "deklarowane_pct": oczekiwane / n * 100.0,
        "zaszlo_pct": zaszlo / n * 100.0,
        "roznica_pp": (zaszlo - oczekiwane) / n * 100.0,
        "z": z,
        "p_value": p_value,
        "istotne": p_value < 0.05,
    }


def przedzial_wilsona(trafienia: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    Przedział ufności Wilsona dla proporcji, w skali 0–1.

    Naiwny błąd standardowy sqrt(p(1-p)/n) daje ZERO gdy trafiono 0% albo
    100%, przez co iloraz "odchylenie / SE" wybucha do absurdu. Wilson nie ma
    tej patologii — przy skrajnych proporcjach przedział jest szeroki, ale
    skończony.
    """
    if n <= 0:
        return (0.0, 1.0)

    p = trafienia / n
    z2 = z * z
    mianownik = 1.0 + z2 / n
    centrum = (p + z2 / (2 * n)) / mianownik
    polowa = (z * math.sqrt(p * (1.0 - p) / n + z2 / (4 * n * n))) / mianownik

    dol = max(0.0, centrum - polowa)
    gora = min(1.0, centrum + polowa)
    return (dol, gora)


def kubelki_z_bledem(
    pary: list[tuple[float, int]],
    szerokosc: int = 10,
    min_n: int = 5,
) -> list[dict]:
    """
    Rozbicie na kubełki po `szerokosc` punktów procentowych (deklarowane %).

    Kubełek z liczebnością < `min_n` jest pomijany. `poza_przedzialem`
    (True/False) zastępuje ilorazowe "ile SE" — jest odporne na skrajne
    proporcje. p=1.0 trafia do ostatniego kubełka (nie do 100-110%).
    """
    liczba_kubelkow = math.ceil(100 / szerokosc)
    grupy: dict[int, list[tuple[float, int]]] = {i: [] for i in range(liczba_kubelkow)}

    for p, y in pary:
        idx = min(int(p * 100 // szerokosc), liczba_kubelkow - 1)
        grupy[idx].append((p, y))

    wynik: list[dict] = []
    for idx in range(liczba_kubelkow):
        grupa = grupy[idx]
        if len(grupa) < min_n:
            continue

        n = len(grupa)
        deklarowane = sum(p for p, _ in grupa) / n
        trafienia = sum(y for _, y in grupa)
        trafione = trafienia / n
        dol, gora = przedzial_wilsona(trafienia, n)

        wynik.append({
            "zakres_od_pct": idx * szerokosc,
            "zakres_do_pct": (idx + 1) * szerokosc,
            "n": n,
            "deklarowane_pct": deklarowane * 100.0,
            "trafione_pct": trafione * 100.0,
            "dol_pct": dol * 100.0,
            "gora_pct": gora * 100.0,
            "poza_przedzialem": not (dol <= deklarowane <= gora),
        })

    return wynik


def ece(pary: list[tuple[float, int]], szerokosc: int = 10) -> float | None:
    """
    Expected Calibration Error: średnia z |deklarowane − trafione| po
    kubełkach, ważona liczebnością kubełka, w skali 0–1.

    Bez `min_n` — ECE ma obejmować całość, nawet małe kubełki.
    """
    if not pary:
        return None

    n_calkowite = len(pary)
    kubelki = kubelki_z_bledem(pary, szerokosc=szerokosc, min_n=1)

    suma_wazona = sum(
        abs(k["deklarowane_pct"] - k["trafione_pct"]) / 100.0 * k["n"]
        for k in kubelki
    )
    return suma_wazona / n_calkowite


# Ponizej tylu obserwacji rangi ze statystyk pozycyjnych schodza poza zakres
# proby i przedzial przestaje cokolwiek znaczyc — uczciwiej oddac caly zakres.
_MIN_N_MEDIANY = 6


def przedzial_mediany(
    wartosci: list[float],
    z: float = 1.96,
) -> tuple[float, float] | None:
    """
    Bezrozkładowy przedział ufności dla mediany (statystyki pozycyjne).

    `przedzial_wilsona` dotyczy PROPORCJI. Dla wielkości ciągłej — jak `edge`
    w pilocie rozrzutu kursów — potrzebny jest przedział oparty na rangach:
    granicami są j-ta i k-ta wartość z posortowanej próbki, gdzie

        j = floor(n/2 − z·√n/2)
        k = ceil(1 + n/2 + z·√n/2)

    Nie zakłada normalności rozkładu, co tu ma znaczenie: rozkład `edge` jest
    skośny, bo kursy są ograniczone od dołu przez 1.0, a od góry nie.

    PO CO: próg zabicia pilota (+2%) stosujemy do DOLNEJ granicy, nie do punktu.
    Przy ~20 meczach na ligę tygodniowo mediana ma szeroki przedział i „+2,3%"
    może nie różnić się istotnie od „+1,7%". Gołe liczby bez miary niepewności
    dwa razy 26.08 doprowadziły w tym projekcie do fałszywego wniosku.

    Zwraca None dla pustej listy; przy n < 6 zwraca (min, max).
    """
    if not wartosci:
        return None
    posortowane = sorted(float(w) for w in wartosci)
    n = len(posortowane)
    if n < _MIN_N_MEDIANY:
        return (posortowane[0], posortowane[-1])
    polowa = z * math.sqrt(n) / 2.0
    j = max(1, int(math.floor(n / 2.0 - polowa)))
    k = min(n, int(math.ceil(1.0 + n / 2.0 + polowa)))
    return (posortowane[j - 1], posortowane[k - 1])

