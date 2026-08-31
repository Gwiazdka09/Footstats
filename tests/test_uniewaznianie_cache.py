"""KROK 3b nie odswiezal kursow — odczytywal je z wlasnego cache'a.

Zmierzone 31.08. Produkcja raportowala `Odswiezono kursy LIVE: 0/46 meczow
zaktualizowanych`, co wygladalo na stojacy rynek. Przyczyna byla inna:

  * `BzzoiroClient._get` trzyma odpowiedzi w RAM-owym cache'u,
  * `CACHE_TTL_MIN = 30` minut,
  * KROK 1 (pobranie kandydatow) i KROK 3b (odswiezenie) chodza w TYM SAMYM
    procesie, w odstepie kilku-kilkunastu minut.

Drugie zapytanie trafialo wiec w cache i porownywalo bajt w bajt te same dane.
`updated = 0` bylo gwarantowane konstrukcja, nie obserwacja rynku. Krok kosztowal
34 s (przeliczenie Poissona) i nie mogl znalezc zmiany, chyba ze przebieg
przekroczyl 30 minut.

Potwierdzone pomiarem: dwa wywolania tej samej sciezki w jednym procesie,
5 minut po sobie, dalo `Cache HIT [5min]` i 0/11 zmienionych.
"""
from __future__ import annotations

import pytest

from footstats.utils import cache as c


@pytest.fixture(autouse=True)
def _czysty_cache():
    c._RAM_CACHE.clear()
    yield
    c._RAM_CACHE.clear()


def test_uniewaznia_wpisy_o_danym_prefiksie():
    c._cache_set("bz:/predictions/:{'a': 1}", {"x": 1})
    c._cache_set("bz:/events/:{'b': 2}", {"x": 2})

    usuniete = c.uniewaznij_cache("bz:")

    assert usuniete == 2
    assert c._cache_get("bz:/predictions/:{'a': 1}") is None


def test_nie_rusza_wpisow_innych_zrodel():
    """Cache jest wspolny dla kilku zrodel — czyszczenie Bzzoiro nie moze
    kasowac football-data, bo tamten ma inny koszt i inny sens odswiezania."""
    c._cache_set("bz:/predictions/:{}", {"x": 1})
    c._cache_set("fd:/matches/:{}", {"y": 2})

    c.uniewaznij_cache("bz:")

    assert c._cache_get("fd:/matches/:{}") == {"y": 2}


def test_zwraca_zero_gdy_nic_nie_pasuje():
    c._cache_set("fd:/matches/:{}", {"y": 2})

    assert c.uniewaznij_cache("bz:") == 0


def test_pusty_prefiks_NIE_kasuje_wszystkiego():
    """Ochrona przed literowka: pusty prefiks pasowalby do kazdego klucza
    i po cichu wyczyscilby caly cache, w tym budzet API-Football."""
    c._cache_set("bz:/predictions/:{}", {"x": 1})
    c._cache_set("fd:/matches/:{}", {"y": 2})

    with pytest.raises(ValueError):
        c.uniewaznij_cache("")

    assert len(c._RAM_CACHE) == 2


def test_po_uniewaznieniu_kolejny_zapis_dziala():
    c._cache_set("bz:/predictions/:{}", {"x": 1})
    c.uniewaznij_cache("bz:")
    c._cache_set("bz:/predictions/:{}", {"x": 99})

    assert c._cache_get("bz:/predictions/:{}") == {"x": 99}


# ── KROK 3b faktycznie omija cache ──────────────────────────────────────────

def test_odswiezenie_kursow_uniewaznia_cache_bzzoiro(monkeypatch):
    """Bez tego krok czyta wlasny cache i nie moze zobaczyc zadnej zmiany."""
    from footstats import daily_agent as da
    from footstats.scrapers.bzzoiro import ENV_BZZOIRO

    monkeypatch.setenv(ENV_BZZOIRO, "test-key")

    class _Klient:
        _valid = True

        def __init__(self, *a, **k):
            pass

        def waliduj(self):
            return True, "ok"

    monkeypatch.setattr("footstats.scrapers.bzzoiro.BzzoiroClient", _Klient)
    monkeypatch.setattr("footstats.core.quick_picks.szybkie_pewniaczki_2dni",
                        lambda *a, **k: [])

    c._cache_set("bz:/predictions/:{}", {"stare": True})
    c._cache_set("fd:/matches/:{}", {"inne_zrodlo": True})

    da._odswiez_kursy_live({(("a",), ("b",)): {"odds": {}}})

    assert c._cache_get("bz:/predictions/:{}") is None, (
        "KROK 3b musi wymusic swiezy odczyt, inaczej porownuje dane z soba"
    )
    assert c._cache_get("fd:/matches/:{}") is not None, "inne zrodla nietkniete"
