"""Pytaliśmy API o wyniki z dat, których ono z definicji nie odda.

ZMIERZONE NA PRODUKCJI 23.08, przebieg rozliczenia o 06:00 (`/api/cron/settle`):

    cron_settle: {'settled': 0, 'partial': 21, 'errors': 0, 'voided': 0}
    API-Football odrzucil zapytanie (HTTP 200): plan: Free plans do not have
    access to this date, try from 2026-08-22 to 2026-08-24.
    flashscore.mobi: data 2026-08-15 poza zasięgiem (offset -8).

21 kuponów z 14-15.08 czekało na wyniki, których **żadne źródło już nie ma**:

  * darmowy plan API-Football wpuszcza wyłącznie okno `dziś ±1 dzień`,
  * `flashscore.mobi` sięga około 7 dni wstecz — i to źródło SAMO SIĘ PILNUJE
    (`flashscore_results.py`: „poza zasięgiem (offset -8)"), więc nie marnuje ruchu.

API-Football takiego progu nie miało, więc przy każdym przebiegu (2x dziennie)
pytaliśmy o daty z góry skazane na odmowę: 21 kuponów × 2 daty (mecz i mecz+1)
× 2 przebiegi. Dzienny limit konta to 100 zapytań i dzieli go potok dzienny,
który potrzebuje ich na składy i sędziego.

Osobno gorsze: `coupon_settlement` miał WŁASNĄ kopię tego zapytania, wołaną
surowym `requests.get` z pominięciem licznika budżetu — więc zużycie limitu
z tej ścieżki było dla nas NIEWIDOCZNE. (Widoczne w logach linie „Budzet AF"
pochodzą z klienta `api_football.py`, którego na ścieżce rozliczeń nie ma —
to był równoległy cron w tym samym oknie czasowym.)

Te testy pilnują progu po stronie API-Football — tej samej dyscypliny, którą
FlashScore miał od początku — w OBU miejscach. Próg jest env-strojony
(`AF_HORYZONT_DNI`), bo płatny plan nie ma tego ograniczenia.

AKTUALIZACJA 2026-09-02: konto przeszło na plan **Pro** i okno dat zniknęło
całkowicie (zmierzone: `/fixtures?date=` oddaje mecze nawet z 2020-08-01), więc
domyślny próg to teraz 30 dni, nie 1. Testy poniżej USTAWIAJĄ próg jawnie zamiast
polegać na domyślnej wartości — pilnują MECHANIZMU (próg jest respektowany,
zapytanie nie wychodzi), a nie konkretnej liczby, która zmienia się razem z planem.
Wcześniej mierzyły jedno i drugie naraz, więc zmiana planu wywalała je na czerwono
bez żadnej realnej regresji.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import footstats.scrapers.results_updater as ru


def _dzien(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


@pytest.fixture(autouse=True)
def prog_jak_na_darmowym_planie(monkeypatch):
    """Próg 1 dnia — wartość, dla której te scenariusze były pisane.

    Ustawiany jawnie, żeby test nie zmieniał znaczenia przy zmianie planu.
    """
    monkeypatch.setattr(ru, "AF_HORYZONT_DNI", 1)


@pytest.fixture
def bez_sieci(monkeypatch):
    """Notuje próby wyjścia do API. Test nie ma prawa dotknąć sieci."""
    wolania: list[dict] = []

    def fake_get(url, headers=None, params=None, timeout=None):
        wolania.append({"url": url, "params": params})
        raise AssertionError("zapytanie do API-Football nie powinno wyjsc")

    monkeypatch.setattr(ru.requests, "get", fake_get)
    return wolania


# ── próg zasięgu ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("offset", [0, 1, -1])
def test_data_w_oknie_darmowego_planu_jest_w_zasiegu(offset):
    assert ru.data_w_zasiegu_af(_dzien(offset)) is True


@pytest.mark.parametrize("offset", [-2, -8, -30, 5])
def test_data_poza_oknem_jest_poza_zasiegiem(offset):
    """15.08 przy dzisiejszym 23.08 to offset -8 — dokładnie ten przypadek."""
    assert ru.data_w_zasiegu_af(_dzien(offset)) is False


def test_data_nie_do_sparsowania_traktujemy_jak_poza_zasiegiem():
    """Śmieciowa data i tak dostałaby odmowę — nie płacimy za nią zapytaniem."""
    assert ru.data_w_zasiegu_af("nie-data") is False


def test_prog_da_sie_rozsunac_bez_zmiany_kodu(monkeypatch):
    """Płatny plan nie ma tego ograniczenia — próg musi być strojony env-em."""
    monkeypatch.setattr(ru, "AF_HORYZONT_DNI", 3650)
    assert ru.data_w_zasiegu_af(_dzien(-8)) is True


def test_domyslny_prog_obejmuje_okno_zycia_kuponu():
    """Domyślna wartość musi sięgać dalej niż `VOID_AFTER_DAYS`.

    Inaczej wraca dokładnie ta pułapka, która trzymała 23 kupony nierozliczone:
    kupon ma 10 dni na rozliczenie, a źródła przestawały odpowiadać wcześniej,
    więc umierał jako VOID zamiast dostać wynik. Czytamy stałą z modułu (nie
    fixture), bo pytanie brzmi o DOMYŚLNĄ wartość.
    """
    import importlib

    from footstats.core.coupon_settlement import VOID_AFTER_DAYS

    swiezy = importlib.reload(ru)
    assert swiezy.AF_HORYZONT_DNI > VOID_AFTER_DAYS


# ── zapytania faktycznie nie wychodzą ───────────────────────────────────────

def test_fixtures_po_dacie_nie_pyta_o_date_poza_zasiegiem(bez_sieci):
    """Sedno: zero ruchu do API, zero zjedzonego budżetu."""
    assert ru._fetch_fixtures_by_date("klucz", _dzien(-8)) == []
    assert bez_sieci == [], "budzet API poszedl na pytanie bez szans na odpowiedz"


def test_fixtures_dla_ligi_tez_respektuje_prog(bez_sieci):
    assert ru._fetch_fixtures("klucz", 106, _dzien(-8)) == []
    assert bez_sieci == []


def test_data_w_zasiegu_dalej_pyta(monkeypatch):
    """Regresja: próg nie może uciszyć zapytań, które mają sens."""
    wolania = []

    class _Odp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": [{"fixture": {}}]}

    def fake_get(url, headers=None, params=None, timeout=None):
        wolania.append(params)
        return _Odp()

    monkeypatch.setattr(ru.requests, "get", fake_get)

    wynik = ru._fetch_fixtures_by_date("klucz", _dzien(0))

    assert wynik == [{"fixture": {}}]
    assert len(wolania) == 1


# ── ta sama dyscyplina w ścieżce rozliczania kuponów ────────────────────────

def test_rozliczanie_kuponow_tez_nie_pyta_o_date_poza_zasiegiem(monkeypatch):
    """`coupon_settlement` miał WŁASNĄ kopię tego zapytania — bez progu i bez
    licznika budżetu, więc zjadała dzienny limit konta niewidocznie dla nas.

    Zmierzone 23.08: 21 kuponów ACTIVE z 14-15.08, każdy odpytywany dwa razy
    (data meczu i data+1) przy każdym z dwóch dziennych przebiegów rozliczenia —
    a odpowiedź nie mogła nadejść, bo darmowy plan wpuszcza tylko `dziś ±1 dzień`.
    """
    import footstats.core.coupon_settlement as cs

    def fake_get(*a, **kw):
        raise AssertionError("zapytanie do API-Football nie powinno wyjsc")

    monkeypatch.setattr("requests.get", fake_get)

    assert cs._get_fixtures_api("klucz", _dzien(-8)) == []


def test_rozliczanie_dalej_pyta_o_swieze_daty(monkeypatch):
    """Regresja: próg nie może odciąć rozliczania meczów z wczoraj."""
    import footstats.core.coupon_settlement as cs
    wolania = []

    class _Odp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": [{"fixture": {"id": 1}}]}

    def fake_get(url, headers=None, params=None, timeout=None):
        wolania.append(params)
        return _Odp()

    monkeypatch.setattr("requests.get", fake_get)

    assert cs._get_fixtures_api("klucz", _dzien(-1)) == [{"fixture": {"id": 1}}]
    assert len(wolania) == 1


# ── trzecie wejście: agregator multi-source ─────────────────────────────────

def test_zrodlo_konsensusu_tez_respektuje_prog(monkeypatch):
    """Trzecia droga do tego samego API — znaleziona dopiero po wdrożeniu.

    Pierwsze wdrożenie progu (23.08) NIE uciszyło produkcji: przebieg rozliczenia
    dalej zbierał 19 odmów `Free plans do not have access`. Okazało się, że
    `_find_leg_result` ma jeszcze Źródło 5 — agregator multi-source, który idzie
    przez `af_source` do klienta budżetowego, z pominięciem obu wcześniej
    zabezpieczonych wejść. Sam próg nie wystarczy, jeśli nie stoi na KAŻDYM wejściu.
    """
    from footstats.scrapers.sources.af_source import APIFootballSource

    zrodlo = APIFootballSource(klient=object())
    monkeypatch.setattr(
        zrodlo, "_get",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("nie powinno wyjsc")),
    )

    assert zrodlo.fetch(_dzien(-8)) == []


def test_zrodlo_konsensusu_dalej_pyta_o_swieze_daty(monkeypatch):
    from footstats.scrapers.sources.af_source import APIFootballSource

    zrodlo = APIFootballSource(klient=object())
    wolania = []

    def fake_get(endpoint, params=None):
        wolania.append(params)
        return {"response": []}

    monkeypatch.setattr(zrodlo, "_get", fake_get)

    assert zrodlo.fetch(_dzien(0)) == []
    assert len(wolania) == 1


# ── strażnik: żadne NOWE wejście nie przemyci się bez progu ─────────────────

def test_kazde_zapytanie_o_fixtures_po_dacie_ma_prog():
    """Próg musi stać na KAŻDYM wejściu do API-Football po dacie, nie na wybranych.

    Historia tej naprawy: pierwsze wdrożenie zabezpieczyło dwa wejścia i NIE
    uciszyło produkcji — trzecie (agregator multi-source) dalej zbierało odmowy.
    Potem znalazły się jeszcze dwa. Zamiast szukać czwartego po każdym wdrożeniu,
    ten test przechodzi po źródłach i pilnuje, żeby nowe zapytanie o `/fixtures`
    z parametrem `date` nie powstało bez sprawdzenia zasięgu.

    Pominięte świadomie: `daily_phases` (status NS) i `fixtures_fallback` pytają
    wyłącznie o dziś/jutro, czyli zawsze wewnątrz okna.
    """
    import re
    from pathlib import Path

    zrodla = Path("src/footstats")
    dozwolone_bez_progu = {
        "daily_phases.py",      # status=NS, tylko dzisiejsze mecze
        "fixtures_fallback.py",  # nadchodzące mecze
        "api_football.py",       # znajdz_fixture_id — mecz z terminarza, nie wynik
    }

    winowajcy = []
    for plik in zrodla.rglob("*.py"):
        if plik.name in dozwolone_bez_progu:
            continue
        tekst = plik.read_text(encoding="utf-8")
        if not re.search(r'"/fixtures"|/fixtures"', tekst):
            continue
        if '"date"' not in tekst:
            continue
        if "data_w_zasiegu_af" not in tekst:
            winowajcy.append(plik.name)

    assert winowajcy == [], (
        f"zapytanie o /fixtures po dacie bez progu zasiegu: {winowajcy}. "
        "Kazde wejscie musi wolac `data_w_zasiegu_af` — inaczej placimy "
        "requestem za pytanie, na ktore darmowy plan nie odpowie."
    )

# ── bramka: klucz wstrzyknięty parametrem też nie przechodzi ────────────────

def test_zamknieta_bramka_blokuje_klucz_podany_parametrem(bez_sieci, monkeypatch):
    """`_naglowek_af` to DRUGA linia obrony i musi mieć własny test.

    `_get_api_key()` przechodzi przez bramkę, ale klucz bywa tu wstrzykiwany
    parametrem — z `coupon_settlement`, `evening_agent` i z testów. Gdyby
    `_naglowek_af` sprawdzało tylko obecność klucza, wyłącznik miałby dziurę
    dokładnie tam, gdzie chodzi o niego najbardziej: przy koncie zawieszonym
    przez dostawcę.

    Mutacja `if not api_key or not wlaczone()` -> `if not api_key` PRZEŻYŁA całą
    resztę suity — stąd ten test.
    """
    monkeypatch.setenv("APISPORTS_ENABLED", "0")
    assert ru._fetch_fixtures_by_date("klucz-wstrzykniety", _dzien(0)) == []
    assert bez_sieci == [], "zamknieta bramka nie zatrzymala zapytania"


def test_zatrzasnieta_bramka_blokuje_mimo_wlaczonego_env(bez_sieci, monkeypatch):
    """Po blokadzie konta env już nie pomaga — zatrzask jest silniejszy."""
    from footstats.core import apisports_gate

    monkeypatch.delenv("APISPORTS_ENABLED", raising=False)
    apisports_gate.zglos_odpowiedz(
        {"errors": {"access": "Your account is suspended, check on dashboard."}}
    )
    assert ru._fetch_fixtures("klucz-wstrzykniety", 106, _dzien(0)) == []
    assert bez_sieci == []
