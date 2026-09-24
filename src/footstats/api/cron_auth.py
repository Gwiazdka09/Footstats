"""Jedno źródło prawdy dla bramki `/cron/*`.

DLACZEGO OSOBNY MODUŁ: ten sam warunek stał w pięciu kopiach (cztery w
`routes/coupons.py`, jedna w `routes/status.py`). Wszystkie były poprawne, ale
to układ, w którym błąd musi kiedyś powstać — a akurat tu poprawka pominięta
w jednym wejściu znaczy otwarty endpoint produkcyjny, nie zła predykcja.
W tym projekcie regułę rozsianą po kilku wejściach pominięto już trzy razy
(21.09 piąte wejście `kupon_key` wywróciło potok).

CZŁON `not oczekiwany` JEST KRYTYCZNY: `hmac.compare_digest("", "")` zwraca
True, więc deploy bez zmiennej `CRON_SECRET` otwierałby endpoint dla każdego,
kto wyśle pusty nagłówek. Sekret czytamy przy każdym wywołaniu, nie na imporcie
— Cloud Run wstrzykuje go z Secret Managera, a testy przestawiają zmienną
w trakcie.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def sprawdz_cron_secret(podany: str) -> None:
    """Podnosi 401, gdy nagłówek nie zgadza się z `CRON_SECRET` albo go brak."""
    oczekiwany = os.getenv("CRON_SECRET", "")
    if not oczekiwany or not hmac.compare_digest(podany, oczekiwany):
        raise HTTPException(status_code=401, detail="Unauthorized")


def wymagaj_cron_secret(x_cron_secret: str = Header(default="")) -> None:
    """Ta sama bramka jako zależność FastAPI: `dependencies=[Depends(...)]`.

    Wersja dla nowych endpointów — nie trzeba pamiętać o wywołaniu w ciele
    funkcji, bo brak zależności widać w sygnaturze trasy.
    """
    sprawdz_cron_secret(x_cron_secret)
