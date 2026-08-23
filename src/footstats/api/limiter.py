"""Współdzielony rate-limiter (slowapi).

Wydzielony do osobnego modułu, by zarówno `api.main` (rejestracja middleware),
jak i routery (np. `api.auth` — twardszy limit na logowanie) mogły go importować
bez cyklu importów. `api.main` re-eksportuje `limiter` (testy/conftest go stamtąd biorą).
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def klucz_klienta(request: Request) -> str:
    """Adres KLIENTA, a nie pośrednika Cloud Run.

    ZMIERZONE 23.08 na logach dostępowych uvicorna: 36 kolejnych żądań z zupełnie
    różnych źródeł (Cloud Scheduler, curl z sieci domowej, sondy zdrowia) aplikacja
    widziała jako `169.254.169.126` — adres link-local infrastruktury Cloud Run.
    `get_remote_address` (czyli `request.client.host`) zwracał go dla KAŻDEGO
    klienta, więc limiter miał JEDNO wspólne wiadro dla całego świata.

    Dwa skutki, drugi gorszy: limit nie izolował napastnika, a dowolny klient mógł
    wyczerpać limit logowania (10/min) i odciąć wszystkich pozostałych. Mechanizm
    chroniący dostępność sam ją psuł.

    DLACZEGO OSTATNI WPIS, NIE PIERWSZY: `X-Forwarded-For` to lista, do której każdy
    pośrednik dopisuje adres swojego rozmówcy. Klient może wysłać własny nagłówek —
    Cloud Run go zachowa i dopisze na końcu adres, z którego faktycznie przyszło
    połączenie. Branie pierwszego wpisu czyniłoby limit trywialnie omijalnym:
    wystarczyłoby losować nagłówek przy każdym żądaniu.

    ZAŁOŻENIE: usługa stoi bezpośrednio na `run.app`, bez własnego load balancera.
    Gdyby kiedyś stanął przed nią LB, ostatnim wpisem byłby JEGO adres i tę decyzję
    trzeba będzie przeliczyć.
    """
    naglowek = (request.headers.get("x-forwarded-for") or "").strip()
    if naglowek:
        wpisy = [w.strip() for w in naglowek.split(",") if w.strip()]
        if wpisy:
            return wpisy[-1]
    # Brak nagłówka: lokalne uruchomienie i testy. Wtedy adres połączenia JEST
    # adresem klienta.
    return get_remote_address(request)


# Globalny limit 60/min per klient (siatka bezpieczeństwa); endpointy wrażliwe
# (logowanie/rejestracja) dokładają własny, twardszy limit dekoratorem.
limiter = Limiter(key_func=klucz_klienta, default_limits=["60/minute"])
