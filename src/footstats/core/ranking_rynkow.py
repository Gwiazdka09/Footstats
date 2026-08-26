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
    ranking.sort(key=lambda pozycja: pozycja["prob"], reverse=True)
    return ranking


def _pozycja(wiersz: dict, rank: int) -> dict | None:
    """Rynek na pozycji `rank` (1-indeksowanej) w rankingu tego wiersza."""
    ranking = ranking_rynkow(wiersz)
    if len(ranking) < rank:
        return None
    return ranking[rank - 1]


def _bazy_rynkow(wiersze: list[dict]) -> dict[str, float]:
    """Wlasna czestosc trafien kazdego z 7 rynkow w PRZEKAZANEJ probce —
    NIEZALEZNA od tego, czy model akurat ten rynek wybral na ktorejkolwiek
    pozycji. To jest "baza" z tabeli w zadaniu, ale liczona na zywo, zeby
    dane mowily same, a nie zaszyta liczba z opisu.
    """
    sumy: dict[str, int] = {}
    liczniki: dict[str, int] = {}
    for wiersz in wiersze:
        for pozycja in ranking_rynkow(wiersz):
            if pozycja["trafiony"] is None:
                continue
            rynek = pozycja["rynek"]
            sumy[rynek] = sumy.get(rynek, 0) + pozycja["trafiony"]
            liczniki[rynek] = liczniki.get(rynek, 0) + 1
    return {rynek: 100.0 * suma / liczniki[rynek] for rynek, suma in sumy.items()}


def przewaga_nad_baza(wiersze: list[dict], rank: int) -> dict:
    """Trafnosc, baza i przewaga (w pp) dla pozycji `rank` (1-indeksowanej).

    `baza` to SREDNIA bazowa czestosc rynkow FAKTYCZNIE wybranych na tej
    pozycji, liczona z tej samej probki `wiersze` (patrz `_bazy_rynkow`) —
    nie surowa trafnosc. Dzieki temu rynek dwustronny o wysokiej bazie
    wlasnej (np. Over 2.5 55%) nie wygrywa tylko dlatego, ze ma wysoka
    trafnosc rowna wlasnej bazie; przewage widac dopiero ponad nia.
    """
    bazy = _bazy_rynkow(wiersze)
    trafienia: list[int] = []
    bazy_wybranych: list[float] = []
    for wiersz in wiersze:
        pozycja = _pozycja(wiersz, rank)
        if pozycja is None or pozycja["trafiony"] is None:
            continue
        trafienia.append(pozycja["trafiony"])
        baza_rynku = bazy.get(pozycja["rynek"])
        if baza_rynku is not None:
            bazy_wybranych.append(baza_rynku)

    n = len(trafienia)
    trafnosc = 100.0 * sum(trafienia) / n if n else None
    baza = sum(bazy_wybranych) / len(bazy_wybranych) if bazy_wybranych else None
    przewaga = trafnosc - baza if trafnosc is not None and baza is not None else None

    return {"n": n, "trafnosc": trafnosc, "baza": baza, "przewaga": przewaga}


def rozklad_rynkow(wiersze: list[dict], rank: int) -> dict[str, int]:
    """Ile razy kazdy rynek zajmuje pozycje `rank` — miara wprost stronniczosci
    2-way (argmax po surowym prawdopodobienstwie faworyzuje rynki dwustronne).
    """
    rozklad: dict[str, int] = {}
    for wiersz in wiersze:
        pozycja = _pozycja(wiersz, rank)
        if pozycja is None:
            continue
        rynek = pozycja["rynek"]
        rozklad[rynek] = rozklad.get(rynek, 0) + 1
    return rozklad
