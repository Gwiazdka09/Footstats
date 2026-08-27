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

# Ile wynikow MUSI miec kompletny rynek. Bez tej wiedzy nie da sie wykryc luki:
# gdy `Draw` nie kwotuje NIKT, unia wynikow sama kurczy sie do dwoch i wszystkie
# ksiazki wygladaja na kompletne. Z samych cen tego nie widac — trzeba znac typ
# rynku, a znamy go (kolumna `market` w `odds_snapshots`).
#
# Dlaczego to jest krytyczne: devig po OKROJONYM zestawie normalizuje do 1 zbyt
# malo skladnikow, wiec kazde p wychodzi za duze, cena uczciwa za niska, a KAZDY
# `edge` zawyzony. Zmierzone na realnej migawce z 27.08: Pinnacle bez `Draw` daje
# cene uczciwa Crystal Palace 3.85 zamiast 4.99, czyli edge betfaira +37.8%
# zamiast +6.24%. Prog zabicia pilota to +2%, wiec taki blad nie wyglada na blad
# — wyglada na odkrycie. Cichy, bo nie rzuca wyjatkiem i nie psuje zadnego testu.
WYNIKI_RYNKU: dict[str, int] = {"h2h": 3, "totals": 2}


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


def _zdrowe_ceny(ceny: dict[str, float] | None) -> dict[str, float]:
    """Same kwotowania nadajace sie do liczenia. Kurs <= 1.0 nie jest kwotowaniem."""
    czyste: dict[str, float] = {}
    for nazwa, kurs in (ceny or {}).items():
        try:
            k = float(kurs)
        except (TypeError, ValueError):
            continue
        if k > 1.0:
            czyste[nazwa] = k
    return czyste


def ksiazki_kompletne(
    kwoty: dict[str, dict[str, float]],
    oczekiwane_wyniki: int | None = None,
) -> dict[str, dict[str, float]]:
    """
    Ksiazki kwotujace PELNY rynek — tylko one moga byc referencja.

    Dwa tryby, bo sa dwie rozne luki:

    1. `oczekiwane_wyniki` podane (np. 3 dla `h2h`) — kompletna znaczy „kwotuje
       dokladnie tyle wynikow". To jedyny tryb wykrywajacy sytuacje, w ktorej
       wynik wypadl u WSZYSTKICH ksiazek naraz. Wtedy unia tez sie kurczy, wiec
       porownanie ksiazek miedzy soba niczego nie pokaze — trzeba znac typ rynku.
    2. Bez parametru — kompletna znaczy „kwotuje cala unie wynikow widziana
       w tej migawce". Slabsze, ale lapie czesty przypadek: jedna ksiazka ma luke,
       ktorej pozostale nie maja.
    """
    czyste = {b: _zdrowe_ceny(c) for b, c in (kwoty or {}).items()}
    czyste = {b: c for b, c in czyste.items() if c}
    if not czyste:
        return {}

    if oczekiwane_wyniki is not None:
        return {b: c for b, c in czyste.items() if len(c) == oczekiwane_wyniki}

    unia = {nazwa for c in czyste.values() for nazwa in c}
    return {b: c for b, c in czyste.items() if set(c) == unia}


def cena_referencyjna(
    kwoty: dict[str, dict[str, float]],
    oczekiwane_wyniki: int | None = None,
) -> tuple[str, dict[str, float]] | None:
    """
    Wybiera ksiazke referencyjna i zwraca (nazwa, prawdopodobienstwa uczciwe).

    Lancuch: pinnacle -> betfair_ex_eu -> matchbook -> mediana KOMPLETNYCH ksiazek.

    `oczekiwane_wyniki` przekazuj zawsze, gdy znasz typ rynku — patrz
    `WYNIKI_RYNKU` i `ksiazki_kompletne`. Bez tego nie da sie wykryc wyniku,
    ktory wypadl u wszystkich ksiazek naraz.

    Zwraca None, gdy ZADNA ksiazka nie kwotuje pelnego rynku. To jest wynik,
    nie awaria: lepiej nie podac ceny uczciwej niz podac policzona z dziury.
    Mediana liczona jest wylacznie po ksiazkach kompletnych — mieszanie ksiazek
    o roznych zestawach wynikow tworzy rynek, ktorego nie kwotuje nikt.

    Raport MUSI pokazywac zwrocona nazwe: mediana miekkich ksiazek jest
    referencja znacznie slabsza i wniosek trzeba wtedy czytac inaczej.
    """
    kompletne = ksiazki_kompletne(kwoty, oczekiwane_wyniki)
    if not kompletne:
        return None

    for ksiazka in KSIAZKI_REFERENCYJNE:
        p = devig_proporcjonalny(kompletne.get(ksiazka) or {})
        if p:
            return ksiazka, p

    zebrane: dict[str, list[float]] = {}
    for ceny in kompletne.values():
        for nazwa, kurs in ceny.items():
            zebrane.setdefault(nazwa, []).append(kurs)
    p = devig_proporcjonalny({n: median(v) for n, v in zebrane.items()})
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
