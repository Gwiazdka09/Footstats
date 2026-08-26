"""ZADANIE D — „drugi wybór": czy typ nr 2 modelu trafia częściej niż nr 1.

PO CO: `model_log` zapisuje już wszystkie prawdopodobieństwa (`prob_home`,
`prob_draw`, ..., `prob_btts`) i pełny wynik (`actual_result`), ale mierzy
tylko typ GŁÓWNY (argmax). Nie wiadomo, czy druga lub trzecia pozycja rankingu
modelu nie trafiałaby częściej.

PUŁAPKA: bazy 7 rynków są rozstrzelone o 31 pp (zmierzone na produkcji
2026-08-26, n=424): "1" 43.9%, "X" 23.6%, "2" 32.5%, Over 2.5 55.0%,
Under 2.5 45.0%, BTTS 52.6%. Rynek dwustronny (Over/Under, BTTS/NIE) ma z
definicji jedną stronę ≥50% i wygrywa argmax po surowym prawdopodobieństwie
niezależnie od tego, czy model cokolwiek wie o meczu — to dokładnie ten sam
mechanizm co `_pomijaj_btts` w `system_paper.py:42`. Dlatego głównej miary
NIE stanowi surowa trafność, tylko przewaga nad bazą WŁASNEGO rynku
(`przewaga_nad_baza`), liczona z tej samej próbki, a nie z zaszytej tabeli.

PRZEKAZYWANIE RANKINGU: `przewaga_nad_baza`, `rozklad_rynkow`,
`rozklad_z_przewaga` i `policz_nierozliczalne` przyjmują `rankingi` — WYNIK
`ranking_rynkow` policzony JUŻ RAZ na wiersz przez wywołującego, nie surowe
wiersze `model_log`. Powód: raport wywoływał te funkcje osobno dla #1/#2/#3
i rozkładu, a każda sama liczyła ranking od nowa — 3 nierozliczalne wiersze
dawały 147 linii WARNING z `oblicz_tip_correct` zamiast 21 (jedno przejście).
"""
from __future__ import annotations

from footstats.utils.betting import oblicz_tip_correct

# (nazwa rynku, klucz prawdopodobienstwa w wierszu, dopelnienie klucza,
#  tip rozpoznawany przez `oblicz_tip_correct`)
_DEFINICJE: tuple[tuple[str, str, str | None, str], ...] = (
    ("1", "prob_home", None, "1"),
    ("X", "prob_draw", None, "X"),
    ("2", "prob_away", None, "2"),
    ("Over 2.5", "prob_over25", None, "OVER 2.5"),
    ("Under 2.5", "prob_over25", "dopelnienie", "UNDER 2.5"),
    ("BTTS", "prob_btts", None, "BTTS"),
    ("BTTS NIE", "prob_btts", "dopelnienie", "BTTS NIE"),
)


def _prawdopodobienstwo(wiersz: dict, klucz: str, dopelnij: str | None) -> float | None:
    """Zwraca `prob` dla rynku albo None, jesli danych brak — bez zgadywania."""
    wartosc = wiersz.get(klucz)
    if wartosc is None:
        return None
    wartosc = float(wartosc)
    return 100.0 - wartosc if dopelnij else wartosc


def ranking_rynkow(wiersz: dict) -> list[dict]:
    """Dla jednego wiersza `model_log` zwraca do 7 rynkow posortowanych
    MALEJACO po prawdopodobienstwie modelu.

    `trafiony` liczony jest ZAWSZE z `actual_result` przez `oblicz_tip_correct`,
    NIGDY z `model_tip`/`tip_correct` — inaczej rynki, ktorych model nie
    wytypowal jako glowny (np. "1" przy `model_tip="X"`), zostalyby bez
    odpowiedzi mimo ze wynik jest znany. Brak prawdopodobienstwa (NULL)
    pomija rynek w calosci; nierozliczalny wynik daje `trafiony=None` dla
    wszystkich pozycji, ale rynki zostaja w rankingu (znamy tylko prob).
    """
    actual_result = wiersz.get("actual_result")
    ranking = []
    for rynek, klucz, dopelnij, tip in _DEFINICJE:
        prob = _prawdopodobienstwo(wiersz, klucz, dopelnij)
        if prob is None:
            continue
        trafiony = oblicz_tip_correct(tip, actual_result)
        ranking.append({"rynek": rynek, "prob": prob, "trafiony": trafiony})
    # Remis prawdopodobienstw dwoch rynkow rozstrzyga KOLEJNOSC w _DEFINICJE
    # (sort jest stabilny) — arbitralne, ale deterministyczne. Na prodzie
    # 26.08 dotyczylo to ok. 15 wierszy na granicach #1/#2 i #2/#3.
    ranking.sort(key=lambda pozycja: pozycja["prob"], reverse=True)
    return ranking


def _pozycja_z_rankingu(ranking: list[dict], rank: int) -> dict | None:
    """Rynek na pozycji `rank` (1-indeksowanej) w JUŻ POLICZONYM rankingu."""
    if len(ranking) < rank:
        return None
    return ranking[rank - 1]


def _bazy_rynkow(rankingi: list[list[dict]]) -> dict[str, float]:
    """Wlasna czestosc trafien kazdego z 7 rynkow w PRZEKAZANEJ probce —
    NIEZALEZNA od tego, czy model akurat ten rynek wybral na ktorejkolwiek
    pozycji. To jest "baza" z tabeli w zadaniu, ale liczona na zywo, zeby
    dane mowily same, a nie zaszyta liczba z opisu.
    """
    sumy: dict[str, int] = {}
    liczniki: dict[str, int] = {}
    for ranking in rankingi:
        for pozycja in ranking:
            if pozycja["trafiony"] is None:
                continue
            rynek = pozycja["rynek"]
            sumy[rynek] = sumy.get(rynek, 0) + pozycja["trafiony"]
            liczniki[rynek] = liczniki.get(rynek, 0) + 1
    return {rynek: 100.0 * suma / liczniki[rynek] for rynek, suma in sumy.items()}


def przewaga_nad_baza(rankingi: list[list[dict]], rank: int) -> dict:
    """Trafnosc, baza i przewaga (w pp) dla pozycji `rank` (1-indeksowanej).

    `n == 0` ma DWIE ROZNE przyczyny, zwrocone osobno jako `brak_pozycji`
    (wiersz mial za malo rynkow z prawdopodobienstwem, wiec pozycja `rank`
    w ogole nie istnieje) i `nierozliczalne` (rynek na tej pozycji BYL, ale
    wynik — dogrywka/karne — nie pozwolil go rozliczyc). Sklejenie ich w
    jedno dawalo falszywa diagnoze: raport twierdzil "zaden wiersz nie ma
    tylu rynkow" o probce, w ktorej kazdy wiersz mial komplet 7 rynkow,
    tylko akurat AET.

    `baza` to SREDNIA bazowa czestosc rynkow FAKTYCZNIE wybranych na tej
    pozycji, liczona z tej samej probki (patrz `_bazy_rynkow`) — nie
    surowa trafnosc. Dzieki temu rynek dwustronny o wysokiej bazie wlasnej
    (np. Over 2.5 55%) nie wygrywa tylko dlatego, ze ma wysoka trafnosc
    rowna wlasnej bazie; przewage widac dopiero ponad nia.
    """
    bazy = _bazy_rynkow(rankingi)
    trafienia: list[int] = []
    bazy_wybranych: list[float] = []
    brak_pozycji = 0
    nierozliczalne = 0
    for ranking in rankingi:
        pozycja = _pozycja_z_rankingu(ranking, rank)
        if pozycja is None:
            brak_pozycji += 1
            continue
        if pozycja["trafiony"] is None:
            nierozliczalne += 1
            continue
        trafienia.append(pozycja["trafiony"])
        # `pozycja["trafiony"]` nie jest None, wiec ten sam wpis wliczyl sie
        # tez do `_bazy_rynkow` na TEJ SAMEJ liscie `rankingi` — klucz jest
        # wiec gwarantowany, bez potrzeby sprawdzania None.
        bazy_wybranych.append(bazy[pozycja["rynek"]])

    n = len(trafienia)
    trafnosc = 100.0 * sum(trafienia) / n if n else None
    baza = sum(bazy_wybranych) / len(bazy_wybranych) if bazy_wybranych else None
    przewaga = trafnosc - baza if trafnosc is not None and baza is not None else None

    return {
        "n": n,
        "trafnosc": trafnosc,
        "baza": baza,
        "przewaga": przewaga,
        "brak_pozycji": brak_pozycji,
        "nierozliczalne": nierozliczalne,
    }


def rozklad_rynkow(rankingi: list[list[dict]], rank: int) -> dict[str, int]:
    """Ile razy kazdy rynek zajmuje pozycje `rank` — miara wprost
    stronniczosci 2-way. Liczy TYLKO wiersze rozliczalne (trafiony != None)
    — ten sam filtr co `przewaga_nad_baza`, zeby mianownik byl spojny z
    tabela trafnosci nad nim (wczesniej rozklad sumowal sie do 427, a `n`
    w tabeli obok mowil 424 — 3 nierozliczalne wiersze liczyly sie tu, a
    tam nie, wiec dwie liczby obok siebie mowily co innego).
    """
    rozklad: dict[str, int] = {}
    for ranking in rankingi:
        pozycja = _pozycja_z_rankingu(ranking, rank)
        if pozycja is None or pozycja["trafiony"] is None:
            continue
        rynek = pozycja["rynek"]
        rozklad[rynek] = rozklad.get(rynek, 0) + 1
    return rozklad


def rozklad_z_przewaga(rankingi: list[list[dict]], rank: int) -> list[dict]:
    """Jak `rozklad_rynkow`, ale z metrykami per rynek (n/trafnosc/baza/
    przewaga), posortowane malejaco po `n`.

    PO CO: naglowkowe "#1: +12.0pp" usrednia WSZYSTKIE rynki wybrane na
    pozycji #1 w jedna liczbe, a to ukrywa, ze najczestszy z nich moze miec
    przewage UJEMNA — zmierzone 26.08: BTTS na #1 (n=134, 32% wierszy) ma
    przewage -3.3pp, replikuje sie w obu polowach chronologicznych. Bez tej
    tabeli czytelnik wychodzi z falszywym wnioskiem "typ glowny ma przewage".
    """
    bazy = _bazy_rynkow(rankingi)
    trafienia_per_rynek: dict[str, list[int]] = {}
    for ranking in rankingi:
        pozycja = _pozycja_z_rankingu(ranking, rank)
        if pozycja is None or pozycja["trafiony"] is None:
            continue
        trafienia_per_rynek.setdefault(pozycja["rynek"], []).append(pozycja["trafiony"])

    wynik = []
    for rynek, trafienia in trafienia_per_rynek.items():
        n = len(trafienia)
        trafnosc = 100.0 * sum(trafienia) / n
        # Jak w `przewaga_nad_baza`: rynek pochodzi z wpisu o trafiony != None,
        # wiec jest gwarantowany w `bazy` policzonej na tej samej `rankingi`.
        baza = bazy[rynek]
        wynik.append({
            "rynek": rynek,
            "n": n,
            "trafnosc": trafnosc,
            "baza": baza,
            "przewaga": trafnosc - baza,
        })
    wynik.sort(key=lambda pozycja: pozycja["n"], reverse=True)
    return wynik


def policz_nierozliczalne(rankingi: list[list[dict]]) -> int:
    """Ile wierszy ma PELNY ranking nierozliczalny — kazdy obecny rynek z
    `trafiony=None` (dogrywka/karne). Bez tej liczby n==0 na ktorejs
    pozycji wyglada jak brak danych strukturalnych, a to inny problem —
    patrz `przewaga_nad_baza`. Wiersz bez ZADNEGO prawdopodobienstwa (pusty
    ranking) NIE liczy sie tutaj — to osobna, rzadsza usterka danych.
    """
    return sum(
        1 for ranking in rankingi
        if ranking and all(pozycja["trafiony"] is None for pozycja in ranking)
    )
