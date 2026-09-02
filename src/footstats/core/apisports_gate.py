"""Jedyna bramka do API-Football (api-sports.io) — wyłącznik ruchu w jednym miejscu.

PO CO ISTNIEJE
--------------
Klucz był czytany w OŚMIU miejscach: `os.getenv("APISPORTS_KEY")` w `daily_agent`
(×2), `evening_agent` i `results_updater`, oraz `_czytaj_wszystkie_klucze()` w
`api_football`, `af_source`, `fixtures_fallback` i `source_manager`. Wyłączenie
źródła wymagałoby ośmiu zgodnych zmian, a JEDNO przeoczone miejsce dalej
wysyłałoby zapytania. To ten sam kształt błędu, który już nas kosztował (reguła
singla żyjąca w czterech kopiach) — tyle że tutaj ceną jest trwała blokada konta.

STAN NA 2026-09-02
------------------
Rano konto było zawieszone DRUGI raz — `/fixtures?date=2026-09-02` oddawało:

    {"errors": {"access": "Your account is suspended, check on
     https://dashboard.api-football.com."}, "response": []}

Wieczorem wykupiony plan **Pro**. Zmierzone przez `/status`:

    plan Pro, active do 2026-10-02, limit_day 7500
    naglowki: x-ratelimit-limit 300 (na MINUTE), x-ratelimit-requests-limit 7500

Dostawca potwierdził wcześniej mailem, że zawieszenia za wiele kont dotyczą
WYŁĄCZNIE planu Free — na płatnym ta przesłanka znika.

Dlatego bramka jest **domyślnie OTWARTA**, a wyłącznikiem jest `APISPORTS_ENABLED=0`.
Odwrotny default (zamknięty) byłby pułapką: konto jest opłacone, a źródło
milczałoby, dopóki ktoś nie przypomniałby sobie o zmiennej — czyli dokładnie ta
cicha degradacja, którą ta bramka ma wykrywać.

Bezpieczeństwo daje tu ZATRZASK poniżej, nie domyślne wyłączenie: gdyby konto
kiedykolwiek znów zostało zawieszone, ruch ustaje po pierwszej takiej odpowiedzi,
bez czekania na człowieka i bez redeployu.

Potok tego API nie potrzebuje do życia i to jest zmierzone: 2026-09-02, przy koncie
zawieszonym od 01.08, powstało 31 kuponów. API-Football jest warstwą redundancji
(fallback listy meczów, składy/sędzia do `decision_score` fazy final, jedno
z pięciu źródeł rozliczeń), nie zależnością — i tak ma zostać.

ZATRZASK (latch)
----------------
`zglos_odpowiedz` rozpoznaje zawieszenie w treści odpowiedzi i zamyka bramkę na
resztę życia procesu — env tego nie przebije. Chodzi o różnicę między
„wyłączyliśmy" a „przestaliśmy wysyłać": gdyby konto zawieszono ponownie po
włączeniu, bez zatrzasku potok waliłby w nie do końca doby. Latch nie ma resetu
w locie — świadomie: odblokowanie ma być decyzją człowieka po restarcie, nie
efektem ubocznym kolejnego przebiegu.

Limit dzienny (`requests: You have reached the request limit`) NIE zatrzaskuje —
to normalny stan doby, nie decyzja dostawcy o koncie.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

ENV_WYLACZNIK = "APISPORTS_ENABLED"
ENV_KLUCZ = "APISPORTS_KEY"

# Fragmenty komunikatów api-sports oznaczające decyzję dostawcy o KONCIE
# (a nie o pojedynczym zapytaniu). Małymi literami — porównanie jest bezwielkościowe.
_KOMUNIKATY_BLOKADY = ("suspend", "banned", "blocked", "disabled")

_FALSZ = ("0", "false", "no", "off")

# Zatrzask na czas życia procesu. Ustawiany wyłącznie przez `zglos_odpowiedz`.
_ZAWIESZONE: bool = False


def blad_konta(dane: object) -> str | None:
    """Komunikat błędu z treści odpowiedzi api-sports, albo None gdy go nie ma.

    api-sports zgłasza problemy Z KONTEM przy HTTP 200, w polu `errors`:
      {"errors": {"access": "Your account is suspended..."}, "response": []}
      {"errors": {"token": "Error/Missing application key"}}
      {"errors": {"requests": "You have reached the request limit for the day"}}

    Uwaga na typ: przy poprawnej odpowiedzi `errors` bywa PUSTĄ LISTĄ `[]`, a nie
    pustym słownikiem — liczy się prawdziwościowość, nie `is None`.
    """
    if not isinstance(dane, dict):
        return "odpowiedz nie jest obiektem JSON"
    errors = dane.get("errors")
    if not errors:
        return None
    if isinstance(errors, dict):
        return "; ".join(f"{k}: {v}" for k, v in errors.items())
    return str(errors)


def zglos_odpowiedz(dane: object) -> bool:
    """Sprawdza odpowiedź pod kątem blokady konta. True = bramka zatrzaśnięta.

    Wołać po KAŻDEJ odpowiedzi z api-sports. Odpowiedź nie będąca JSON-em (strona
    błędu proxy, HTML 502) to awaria sieci, nie decyzja o koncie — nie zatrzaskuje.
    """
    global _ZAWIESZONE
    if not isinstance(dane, dict):
        return False
    komunikat = blad_konta(dane)
    if not komunikat:
        return False
    if not any(slowo in komunikat.lower() for slowo in _KOMUNIKATY_BLOKADY):
        return False
    if not _ZAWIESZONE:
        log.error(
            "API-Football zglosil BLOKADE KONTA (%s) — zamykam bramke do konca"
            " tego procesu. Dalsze zapytania z zawieszonego konta grozily blokada"
            " trwala. Sprawdz konto na dashboard.api-football.com; bramka otworzy"
            " sie sama przy nastepnym starcie procesu (%s musi wtedy NIE byc"
            " ustawione na 0).", komunikat, ENV_WYLACZNIK,
        )
    _ZAWIESZONE = True
    return True


def wlaczone() -> bool:
    """Czy wolno wysłać zapytanie do API-Football. Domyślnie TAK.

    Dwa niezależne powody odmowy, oba muszą być widoczne osobno (patrz `stan`):
      * zatrzask po blokadzie konta — silniejszy, env go nie przebije;
      * jawne `APISPORTS_ENABLED=0` — ręczny wyłącznik dla człowieka.

    Czytane przy każdym wywołaniu (jak `ensemble._env_market_weight`), więc
    ubicie źródła to zmiana zmiennej środowiskowej, nie redeploy kodu.
    """
    if _ZAWIESZONE:
        return False
    return os.getenv(ENV_WYLACZNIK, "").strip().lower() not in _FALSZ


def klucz() -> str | None:
    """Klucz API-Football albo None, gdy bramka zamknięta lub klucza brak.

    Wołający ma traktować None jak „brak klucza" — każda ścieżka już to obsługuje
    (degraduje do FlashScore / football-data / Bzzoiro), więc zamknięta bramka nie
    wywraca potoku, tylko zdejmuje z niego jedną warstwę redundancji.

    JAWNIE PUSTA ZMIENNA WYGRYWA Z `.env`. `_czytaj_wszystkie_klucze` robi
    `os.getenv(x) or z_pliku[x]`, więc `APISPORTS_KEY=""` przechodzi na wartość
    z pliku — a to znaczy co innego niż „brak klucza". Kosztowało to realny wyciek:
    2026-09-02 test ustawił pustą zmienną, bramka dobrała PRAWDZIWY klucz z `.env`
    i pytest wypisał go w komunikacie asercji. Stary `_get_api_key` czytał samo
    `os.environ` i tego problemu nie miał — bramka nie ma prawa być bardziej
    „pomocna" od kodu, który zastępuje.
    """
    if not wlaczone():
        return None

    z_env = os.getenv(ENV_KLUCZ)
    if z_env is not None:
        return z_env.strip() or None

    from footstats.config import ENV_APISPORTS, _czytaj_wszystkie_klucze

    return _czytaj_wszystkie_klucze().get(ENV_APISPORTS) or None


def stan() -> dict:
    """Migawka do diagnostyki (`/pipeline-health`, logi startowe).

    Bez tego zamknięta bramka wygląda w logach identycznie jak brak meczów w
    źródle — a to dwa różne stany, których nie wolno mylić.
    """
    return {
        "wlaczone": wlaczone(),
        "zawieszone_w_tym_procesie": _ZAWIESZONE,
        "env_wylacznik": os.getenv(ENV_WYLACZNIK, "") or None,
        "klucz_obecny": bool(os.getenv(ENV_KLUCZ, "").strip()),
    }
