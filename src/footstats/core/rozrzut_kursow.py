"""
rozrzut_kursow.py — czyste funkcje pilotu rozrzutu kursow.

PO CO: cztery pomiary mowia, ze model nie bije RYNKU. Nie mierzylismy nigdy,
czy da sie bic pojedyncza ksiazke. `edge_b = kurs_b * p_uczciwe - 1` odpowiada
na to bez czekania na wyniki meczow — wariancja wyniku meczu w ogole nie wchodzi
do rownania. Spec: docs/superpowers/specs/2026-08-27-rozrzut-kursow-pilot-design.md

Zero I/O, zero dostepu do bazy. Wejscie: `kwoty` = {bukmacher: {outcome: cena}}.
"""
from __future__ import annotations

from statistics import median

# Kolejnosc ma znaczenie: pierwsza ksiazka z KOMPLETNYM rynkiem wygrywa.
# Pinnacle to sharp o najwezszej marzy; gieldy (betfair, matchbook) sa jeszcze
# blizej ceny prawdziwej, ale rzadziej kwotuja ligi egzotyczne.
KSIAZKI_REFERENCYJNE: tuple[str, ...] = ("pinnacle", "betfair_ex_eu", "matchbook")

# Ponizej dwoch wynikow devig nie ma sensu: suma odwrotnosci z jednego kursu
# znormalizowana do 1 dalaby p=1.0, czyli cene uczciwa 1.00 dla kazdego rynku.
_MIN_WYNIKOW = 2


def devig_proporcjonalny(ceny: dict[str, float]) -> dict[str, float]:
    """
    Zdejmuje marze bukmachera proporcjonalnie: p_i = (1/kurs_i) / suma(1/kurs).

    Znany mankament: przy skrajnych faworytach zawyza longshoty
    (favourite-longshot bias). Na pilota wystarcza; gdyby pomysl przezyl,
    do rozwazenia Shin albo power devig.

    Zwraca pusty slownik gdy danych brak albo ktorys kurs jest niepoprawny.
    """
    if len(ceny) < _MIN_WYNIKOW:
        return {}
    odwrotnosci: dict[str, float] = {}
    for nazwa, kurs in ceny.items():
        try:
            k = float(kurs)
        except (TypeError, ValueError):
            return {}
        if k <= 1.0:
            return {}
        odwrotnosci[nazwa] = 1.0 / k
    suma = sum(odwrotnosci.values())
    if suma <= 0:
        return {}
    return {nazwa: v / suma for nazwa, v in odwrotnosci.items()}


def cena_referencyjna(
    kwoty: dict[str, dict[str, float]],
) -> tuple[str, dict[str, float]] | None:
    """
    Wybiera ksiazke referencyjna i zwraca (nazwa, prawdopodobienstwa uczciwe).

    Lancuch: pinnacle -> betfair_ex_eu -> matchbook -> mediana wszystkich ksiazek.
    Ksiazka z niepelnym rynkiem jest pomijana — devig z jednego wyniku dalby
    cene uczciwa 1.00 i kazdy inny kurs wygladalby na gigantyczna przewage.

    Raport MUSI pokazywac zwrocona nazwe: mediana miekkich ksiazek jest
    referencja znacznie slabsza i wniosek trzeba wtedy czytac inaczej.
    """
    if not kwoty:
        return None

    for ksiazka in KSIAZKI_REFERENCYJNE:
        ceny = kwoty.get(ksiazka)
        if not ceny:
            continue
        p = devig_proporcjonalny(ceny)
        if p:
            return ksiazka, p

    # Mediana per outcome, ale tylko po outcome'ach obecnych u >= 1 ksiazki.
    zebrane: dict[str, list[float]] = {}
    for ceny in kwoty.values():
        for nazwa, kurs in (ceny or {}).items():
            try:
                k = float(kurs)
            except (TypeError, ValueError):
                continue
            if k > 1.0:
                zebrane.setdefault(nazwa, []).append(k)
    p = devig_proporcjonalny({n: median(v) for n, v in zebrane.items() if v})
    if not p:
        return None
    return "mediana", p


def edge_bukmacherow(
    kwoty: dict[str, dict[str, float]],
    p_uczciwe: dict[str, float],
) -> list[dict]:
    """
    Przewaga kazdej ksiazki wzgledem ceny uczciwej: edge = kurs * p_uczciwe - 1.

    Outcome bez ceny uczciwej jest POMIJANY, nie dostaje edge=0 — brak referencji
    to brak pomiaru, a nie pomiar rowny zeru.
    """
    wynik: list[dict] = []
    for ksiazka, ceny in (kwoty or {}).items():
        for nazwa, kurs in (ceny or {}).items():
            p = p_uczciwe.get(nazwa)
            if p is None or p <= 0:
                continue
            try:
                k = float(kurs)
            except (TypeError, ValueError):
                continue
            if k <= 1.0:
                continue
            wynik.append({
                "bookmaker": ksiazka,
                "outcome": nazwa,
                "price": k,
                "edge": k * p - 1.0,
            })
    return wynik


def rozrzut(kwoty: dict[str, dict[str, float]], outcome: str) -> dict | None:
    """
    Rozrzut cen jednego wyniku miedzy ksiazkami.

    `ksiazek` jest tu rownie wazne jak `rozpietosc_pct`: rynek kwotowany przez
    dwie ksiazki nie ma miedzy czym sie rozjechac i efektowna rozpietosc bylaby
    tam artefaktem, nie sygnalem.
    """
    ceny: list[float] = []
    for c in (kwoty or {}).values():
        kurs = (c or {}).get(outcome)
        try:
            k = float(kurs)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if k > 1.0:
            ceny.append(k)
    if not ceny:
        return None
    lo, hi = min(ceny), max(ceny)
    return {
        "outcome": outcome,
        "ksiazek": len(ceny),
        "min": lo,
        "max": hi,
        "mediana": median(ceny),
        "rozpietosc_pct": 100.0 * (hi / lo - 1.0) if lo > 0 else 0.0,
    }
