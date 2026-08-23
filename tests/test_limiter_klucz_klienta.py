"""Limiter kluczował po adresie pośrednika, więc miał JEDNO wiadro dla wszystkich.

ZMIERZONE NA PRODUKCJI 23.08 — logi dostępowe uvicorna pokazują adres, który widzi
aplikacja. 36 kolejnych zapytań z zupełnie różnych źródeł (Cloud Scheduler, curl
z sieci domowej, sondy zdrowia Cloud Run):

    36 × 169.254.169.126

To adres link-local infrastruktury Cloud Run. `get_remote_address` (czyli
`request.client.host`) zwraca go dla KAŻDEGO klienta.

DWA SKUTKI, drugi gorszy od pierwszego:
  * limit nie izoluje napastnika — dzieli wiadro z resztą świata;
  * dowolny klient może wyczerpać limit logowania (10/min) i **odciąć wszystkich
    pozostałych**. Limiter, który miał chronić dostępność, sam ją psuł.

DLACZEGO OSTATNI WPIS `X-Forwarded-For`, NIE PIERWSZY:
nagłówek jest listą, do której każdy pośrednik dopisuje adres swojego rozmówcy.
Klient może wysłać własny `X-Forwarded-For` — Cloud Run go zachowa i **dopisze
na końcu** adres, z którego faktycznie przyszło połączenie. Branie pierwszego
wpisu czyniłoby limit trywialnie omijalnym: wystarczyłoby losować nagłówek przy
każdym żądaniu. Ostatni wpis pochodzi od infrastruktury, nie od klienta.

ZAŁOŻENIE, które to opiera: usługa stoi bezpośrednio na `run.app`, bez własnego
load balancera (sprawdzone — brak konfiguracji LB). Gdyby kiedyś stanął przed nią
LB, ostatnim wpisem byłby jego adres i tę decyzję trzeba będzie przeliczyć.
"""
from __future__ import annotations

import pytest

from footstats.api.limiter import klucz_klienta

ADRES_PROXY = "169.254.169.126"


class _Req:
    """Minimalny stub `Request` — limiter czyta tylko nagłówki i `client.host`."""

    def __init__(self, xff: str | None = None, peer: str = ADRES_PROXY):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": peer})()
        self.scope = {"type": "http", "client": (peer, 12345), "headers": []}


# ── sedno: różni klienci = różne klucze ─────────────────────────────────────

def test_dwaj_klienci_za_tym_samym_proxy_maja_rozne_klucze():
    """Przed naprawą obaj dostawali `169.254.169.126` i wspólne wiadro."""
    a = klucz_klienta(_Req(xff="203.0.113.7"))
    b = klucz_klienta(_Req(xff="198.51.100.22"))

    assert a != b
    assert ADRES_PROXY not in (a, b)


def test_klucz_to_adres_klienta_nie_posrednika():
    assert klucz_klienta(_Req(xff="203.0.113.7")) == "203.0.113.7"


# ── odporność na podrobiony nagłówek ────────────────────────────────────────

def test_podrobiony_naglowek_nie_zmienia_klucza():
    """Sedno bezpieczeństwa: klient dopisuje swoje wpisy Z PRZODU, a infrastruktura
    dokleja prawdziwy adres na końcu. Branie pierwszego wpisu pozwalałoby omijać
    limit przez losowanie nagłówka."""
    klucze = {
        klucz_klienta(_Req(xff=f"{zmyslony}, 203.0.113.7"))
        for zmyslony in ("1.2.3.4", "9.9.9.9", "10.0.0.1, 172.16.0.1")
    }

    assert klucze == {"203.0.113.7"}, "klucz da sie podrobic naglowkiem"


def test_biale_znaki_nie_tworza_nowego_klucza():
    """`a, b` i `a,b` to ten sam klient — inaczej spacja podwajałaby limit."""
    assert klucz_klienta(_Req(xff="1.2.3.4,203.0.113.7")) == \
           klucz_klienta(_Req(xff="1.2.3.4 ,  203.0.113.7 "))


# ── zachowanie awaryjne ─────────────────────────────────────────────────────

def test_brak_naglowka_spada_do_adresu_polaczenia():
    """Lokalnie i w testach nagłówka nie ma — limiter musi dalej działać."""
    assert klucz_klienta(_Req(peer="127.0.0.1")) == "127.0.0.1"


def test_pusty_naglowek_traktowany_jak_brak():
    assert klucz_klienta(_Req(xff="   ", peer="127.0.0.1")) == "127.0.0.1"


def test_limiter_uzywa_tej_funkcji():
    """Funkcja bez podpięcia to martwy kod — limiter musi ją mieć jako `key_func`."""
    from footstats.api.limiter import limiter

    assert limiter._key_func is klucz_klienta


@pytest.mark.parametrize("naglowek", ["203.0.113.7", " 203.0.113.7 ", "1.1.1.1, 203.0.113.7"])
def test_klucz_jest_stabilny_dla_tego_samego_klienta(naglowek):
    """Niestabilny klucz = limit, który nigdy nie zadziała."""
    assert klucz_klienta(_Req(xff=naglowek)) == "203.0.113.7"
