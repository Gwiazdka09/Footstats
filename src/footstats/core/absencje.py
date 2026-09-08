"""
absencje.py — łączy „kto nie zagra" z „ile ten ktoś znaczy".

Podział pracy między źródłami jest tu całą treścią modułu:

    FotMob      mówi KTO nie zagra    — pewne, aktualne, 147 lig
    player_db   mówi ILE ZNACZY       — pełny poprzedni sezon, 2775 graczy

Odwrotnie się nie da. `performance.seasonGoals` FotMoba jest na starcie sezonu
szumem: Premier League po dwóch kolejkach dała 5 goli na dwie kadry, więc udział
jednego strzelca wyszedłby 0,4 i model policzyłby jego absencję jako utratę 40%
ataku. `team_goal_shares_recent` sięga po poprzedni pełny sezon i takiego skoku
nie ma.

Ten moduł NIE liczy λ — od tego jest `core/availability_edge.py`. Tutaj jest
wyłącznie dopasowanie nazwisk, bo to ono decyduje, czy cokolwiek zadziała, i to
ono cicho zawodzi, gdy dwa źródła piszą tego samego człowieka inaczej.

DLACZEGO nie przez `injuries_*` i `injury_lambda_factors`: absencje FotMoba nie
mają pozycji (`positionId` to `None` albo sentinel `1000`), a tamta funkcja
klasyfikuje właśnie po pozycji — zwróciłaby `(1.0, 1.0)` i całe wpięcie byłoby
cichym no-opem. `absence_attack_factor` bierze same udziały, bez pozycji.
"""
from __future__ import annotations

import logging

from footstats.scrapers.teamnews.base import klucz_gracza as _klucz
from footstats.scrapers.teamnews.base import klucz_skrocony as _klucz_skrocony

log = logging.getLogger(__name__)

_MIN_CZLONOW = 2   # "Pedro" trafiłoby w dowolnego Pedro w lidze


def _dopasuj(klucz: str, klucze_bazy: dict[str, float],
             skroty_bazy: dict[str, list[float]] | None = None) -> float | None:
    """
    Udział gracza albo None.

    Trzy reguły, wszystkie zachowawcze i w tej kolejności:

    1. Dokładna równość po normalizacji.
    2. Prefiks, bo baza bywa pełniejsza od źródła ("Kylian Mbappe-Lottin" vs
       "Kylian Mbappe").
    3. Inicjał + nazwisko, bo źródła piszą imiona inaczej: API-Football oddaje
       "H. Ekitike", FotMob "Hugo Ekitike". Skrót nie jest prefiksem pełnego
       imienia, więc reguły 1 i 2 ich nie łączą — a to 66% nazwisk w bazie
       (16 093 z 24 417, pomiar 07.09.2026) i realna przyczyna produkcyjnego
       „udzialy absencji 3/24 dopasowane".

    Reguły 2 i 3 wymagają co najmniej dwóch członów i MUSZĄ być jednoznaczne:
    dwóch kandydatów oznacza odrzucenie, bo przypisanie cudzego udziału jest
    gorsze niż brak udziału. Przy udziale 20% i capie 0.35 pomyłka przesuwa λ
    o kilkanaście procent w złą stronę.
    """
    if klucz in klucze_bazy:
        return klucze_bazy[klucz]
    if len(klucz.split()) < _MIN_CZLONOW:
        return None

    trafienia = [v for k, v in klucze_bazy.items() if k.startswith(klucz)]
    if len(trafienia) == 1:
        return trafienia[0]
    if len(trafienia) > 1:
        log.debug("absencje: %r pasuje do %d wpisow — odrzucam jako niejednoznaczne",
                  klucz, len(trafienia))
        return None

    kandydaci = (skroty_bazy or {}).get(_klucz_skrocony(klucz), [])
    if len(kandydaci) == 1:
        return kandydaci[0]
    if len(kandydaci) > 1:
        log.debug("absencje: skrot %r pasuje do %d wpisow — odrzucam",
                  _klucz_skrocony(klucz), len(kandydaci))
    return None


def udzialy_absencji(
    nazwiska: list[str], goal_shares: dict[str, float]
) -> tuple[list[float], list[str]]:
    """
    Zamienia nazwiska nieobecnych na ich udziały w golach drużyny.

    Zwraca `(udzialy, nietrafione)`. Gracz spoza bazy trafia do `nietrafione`,
    NIE do `udzialy` jako zero — zero znaczyłoby "zmierzyłem, nie strzela",
    a my nie wiemy. Rozmiar `nietrafione` jest miarą zdrowia całego połączenia
    i dlatego wychodzi z funkcji, zamiast ginąć w środku.
    """
    if not nazwiska or not goal_shares:
        return [], [n for n in nazwiska if (n or "").strip()]

    klucze_bazy = {_klucz(n): v for n, v in goal_shares.items()}
    # Indeks po inicjale i nazwisku — LISTA, nie wartosc, bo jednoznacznosci
    # pilnuje `_dopasuj`, a bez policzenia kandydatow nie da sie jej sprawdzic.
    skroty_bazy: dict[str, list[float]] = {}
    for n, v in goal_shares.items():
        skroty_bazy.setdefault(_klucz_skrocony(n), []).append(v)

    udzialy: list[float] = []
    nietrafione: list[str] = []
    for nazwisko in nazwiska:
        if not (nazwisko or "").strip():
            continue
        udzial = _dopasuj(_klucz(nazwisko), klucze_bazy, skroty_bazy)
        if udzial is None:
            nietrafione.append(nazwisko)
        else:
            udzialy.append(udzial)
    return udzialy, nietrafione
