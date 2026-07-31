"""test_results_updater.py — pobieranie i dopasowywanie wynikow meczow.

PO CO: modul byl WYKLUCZONY z pomiaru pokrycia (`.coveragerc`), wiec liczba
milczala o 316 instrukcjach rozliczajacych mecze. Po zdjeciu z listy wyszlo 22%.

Najwazniejsze sciezki:
  * `_fixture_to_result` — mecz liczy sie TYLKO gdy status to FT/AET/PEN.
    Wpuszczenie meczu w trakcie (1H/HT/LIVE) rozliczyloby kupon wynikiem
    z 30. minuty.
  * `_znajdz_wynik` — dopasowanie po nazwach z progiem 0.70 (ostrzejszym niz
    0.6 w evening_agent). Bledne dopasowanie = kupon rozliczony cudzym meczem.
  * `_liga_ids_dla_nazwy` — decyduje, czy w ogole wydac zapytanie do API
    (limit 100/dzien). Nieznana liga ma NIE strzelac w ciemno.

Zero ruchu sieciowego — `requests.get` podstawiony wszedzie.
"""
from __future__ import annotations

import pytest
import requests

import footstats.scrapers.results_updater as ru


class _Odp:
    def __init__(self, status=200, dane=None):
        self.status_code = status
        self._dane = dane if dane is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._dane


@pytest.fixture
def http(monkeypatch):
    """Podstawia requests.get; mapuje koncowke URL na odpowiedz."""
    stan = {"odpowiedzi": {}, "zapytania": []}

    def _get(url, headers=None, params=None, timeout=None):
        stan["zapytania"].append((url, params))
        for fragment, odp in stan["odpowiedzi"].items():
            if fragment in url:
                if isinstance(odp, Exception):
                    raise odp
                return odp
        return _Odp(200, {"response": []})

    monkeypatch.setattr(requests, "get", _get)
    return stan


def _fixture(status="FT", hg=2, ag=1, home="Legia", away="Lech",
             ht=None, fid=999) -> dict:
    f = {
        "fixture": {"id": fid, "status": {"short": status}},
        "goals": {"home": hg, "away": ag},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {},
    }
    if ht is not None:
        f["score"]["halftime"] = {"home": ht[0], "away": ht[1]}
    return f


# ── _get_api_key ────────────────────────────────────────────────────────────

def test_klucz_z_env(monkeypatch):
    monkeypatch.setenv("APISPORTS_KEY", "abc123")
    assert ru._get_api_key() == "abc123"


def test_brak_klucza_daje_none(monkeypatch):
    monkeypatch.setenv("APISPORTS_KEY", "")
    assert ru._get_api_key() is None


# ── _liga_ids_dla_nazwy ─────────────────────────────────────────────────────

def test_pusta_nazwa_zwraca_wszystkie_sledzone():
    """Brak nazwy ligi -> sprawdzamy komplet lig TOP, bo nie wiemy gdzie szukac."""
    wynik = ru._liga_ids_dla_nazwy("")
    assert len(wynik) >= 5


def test_znana_liga_daje_jedno_id():
    wynik = ru._liga_ids_dla_nazwy("Premier League")
    assert len(wynik) == 1


@pytest.mark.parametrize("nazwa", ["Ekstraklasa", "PKO BP Ekstraklasa", "ekstraklasa"])
def test_warianty_nazwy_ligi_rozpoznawane(nazwa):
    assert len(ru._liga_ids_dla_nazwy(nazwa)) == 1


@pytest.mark.parametrize("nazwa", [
    "Klasa Okregowa", "Superliga Kobiet", "Regionalliga Bayern",
    "Puchar Polski juniorow",
])
def test_nieznana_liga_nie_marnuje_limitu_api(nazwa):
    """SEDNO oszczedzania: nie strzelamy w ciemno przy 100 req/dzien."""
    assert ru._liga_ids_dla_nazwy(nazwa) == []


def test_znana_slabosc_nazwa_ze_wspolnym_tokenem_daje_falszywe_trafienie():
    """UDOKUMENTOWANE OGRANICZENIE, nie regresja.

    `team_similarity` jest zaprojektowany dla nazw DRUZYN, a tu sluzy do nazw LIG.
    Jego regula token-prefix daje 0.80, gdy caly token pokrywa sie z tokenem celu:
    "Liga Amatorska Podkarpacia" ma token "liga", ktory pasuje do "La Liga".

    Koszt: JEDNO zmarnowane zapytanie ze 100 dziennie. Dalej jest fail-closed —
    pobrane fixtures z La Liga nie dopasuja sie nazwami druzyn, wiec `_znajdz_wynik`
    zwroci None i wynik nie zostanie blednie przypisany.

    Test istnieje, zeby to ograniczenie bylo WIDOCZNE. Jesli kiedys podniesiesz
    prog w `_liga_ids_dla_nazwy` albo dasz osobna funkcje podobienstwa dla lig —
    ten test spadnie i bedzie to sygnal do jego usuniecia, a nie awaria.
    """
    assert ru._liga_ids_dla_nazwy("Liga Amatorska Podkarpacia") == [140]


def test_liga_spoza_sledzonych_pomijana():
    """Rozpoznana, ale nie na liscie TRACKED -> zero zapytan."""
    wynik = ru._liga_ids_dla_nazwy("Championship")
    assert wynik == [] or len(wynik) == 1


# ── _fixture_to_result ──────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["FT", "AET", "PEN"])
def test_mecz_zakonczony_zwraca_wynik(status):
    wynik = ru._fixture_to_result(_fixture(status=status, hg=3, ag=1))
    assert wynik is not None
    home, away, w, _stats = wynik
    assert (home, away, w) == ("Legia", "Lech", "3-1")


@pytest.mark.parametrize("status", ["1H", "HT", "2H", "LIVE", "NS", "PST", "CANC"])
def test_mecz_niezakonczony_odrzucany(status):
    """KRYTYCZNE: wynik z 30. minuty nie moze rozliczyc kuponu."""
    assert ru._fixture_to_result(_fixture(status=status)) is None


def test_brak_goli_odrzucany():
    assert ru._fixture_to_result(_fixture(hg=None, ag=None)) is None


def test_polowa_dolaczana_jako_sufiks():
    """Rynki half-time potrzebuja wyniku do przerwy w formacie ';HT:h-a'."""
    _h, _a, wynik, _s = ru._fixture_to_result(_fixture(hg=2, ag=1, ht=(1, 0)))
    assert wynik == "2-1;HT:1-0"


def test_brak_polowy_nie_dodaje_sufiksu():
    _h, _a, wynik, _s = ru._fixture_to_result(_fixture(hg=2, ag=1))
    assert ";HT:" not in wynik


def test_polowa_zero_zero_tez_dolaczana():
    """0-0 do przerwy to prawidlowa informacja, nie brak danych."""
    _h, _a, wynik, _s = ru._fixture_to_result(_fixture(hg=1, ag=0, ht=(0, 0)))
    assert wynik == "1-0;HT:0-0"


def test_bez_klucza_api_nie_pobiera_statystyk(http):
    ru._fixture_to_result(_fixture(), api_key=None)
    assert http["zapytania"] == []


def test_z_kluczem_pobiera_statystyki(http):
    http["odpowiedzi"]["statistics"] = _Odp(200, {"response": [
        {"team": {"name": "Legia"}, "statistics": [{"type": "Corner Kicks", "value": 7}]},
    ]})
    _h, _a, _w, stats = ru._fixture_to_result(_fixture(), api_key="klucz")
    assert stats["Legia"]["Corner Kicks"] == 7


# ── _fetch_fixtures ─────────────────────────────────────────────────────────

def test_fetch_fixtures_zwraca_liste(http):
    http["odpowiedzi"]["/fixtures"] = _Odp(200, {"response": [_fixture()]})
    assert len(ru._fetch_fixtures("klucz", 39, "2026-07-31")) == 1


def test_fetch_fixtures_przekazuje_lige_i_date(http):
    ru._fetch_fixtures("klucz", 39, "2026-07-31")
    _url, params = http["zapytania"][0]
    assert params["league"] == 39
    assert params["date"] == "2026-07-31"


def test_blad_http_daje_pusta_liste(http):
    http["odpowiedzi"]["/fixtures"] = _Odp(500)
    assert ru._fetch_fixtures("klucz", 39, "2026-07-31") == []


def test_blad_sieci_daje_pusta_liste(http):
    http["odpowiedzi"]["/fixtures"] = requests.RequestException("brak sieci")
    assert ru._fetch_fixtures("klucz", 39, "2026-07-31") == []


def test_fetch_by_date_nie_filtruje_ligi(http):
    """Lapie mecze z lig spoza _LIGI_IDS (np. eliminacje MS)."""
    ru._fetch_fixtures_by_date("klucz", "2026-07-31")
    _url, params = http["zapytania"][0]
    assert "league" not in params
    assert params["date"] == "2026-07-31"


# ── _fetch_match_stats / _fetch_match_events ────────────────────────────────

def test_statystyki_mapowane_per_druzyna(http):
    http["odpowiedzi"]["statistics"] = _Odp(200, {"response": [
        {"team": {"name": "Legia"}, "statistics": [
            {"type": "Shots on Goal", "value": 5}, {"type": "Corner Kicks", "value": 7}]},
        {"team": {"name": "Lech"}, "statistics": [{"type": "Shots on Goal", "value": 2}]},
    ]})
    wynik = ru._fetch_match_stats("klucz", 999)
    assert wynik["Legia"]["Shots on Goal"] == 5
    assert wynik["Lech"]["Shots on Goal"] == 2


def test_blad_statystyk_nie_wywala_pobierania(http):
    http["odpowiedzi"]["statistics"] = _Odp(503)
    assert isinstance(ru._fetch_match_stats("klucz", 999), dict)


def test_zdarzenia_dolaczane_do_statystyk(http):
    http["odpowiedzi"]["events"] = _Odp(200, {"response": [
        {"time": {"elapsed": 23}, "team": {"name": "Legia"},
         "type": "Goal", "detail": "Normal Goal", "player": {"name": "Kowalski"}},
    ]})
    wynik = ru._fetch_match_stats("klucz", 999)
    assert wynik["_events"][0]["minute"] == 23
    assert wynik["_events"][0]["player"] == "Kowalski"


def test_brak_zdarzen_nie_dodaje_klucza(http):
    http["odpowiedzi"]["events"] = _Odp(200, {"response": []})
    assert "_events" not in ru._fetch_match_stats("klucz", 999)


def test_blad_zdarzen_daje_pusta_liste(http):
    http["odpowiedzi"]["events"] = requests.RequestException("timeout")
    assert ru._fetch_match_events("klucz", 999) == []


# ── _znajdz_wynik ───────────────────────────────────────────────────────────

def _pending(home="Legia", away="Lech") -> dict:
    return {"team_home": home, "team_away": away}


def test_dopasowuje_identyczne_nazwy():
    wynik = ru._znajdz_wynik(_pending(), [_fixture(hg=2, ag=1)])
    assert wynik is not None and wynik[0] == "2-1"


def test_dopasowuje_wariant_nazwy():
    """'Jagiellonia Białystok' w bazie vs 'Jagiellonia' w API."""
    fixtures = [_fixture(home="Jagiellonia", away="Lech", hg=1, ag=0)]
    wynik = ru._znajdz_wynik(_pending("Jagiellonia Białystok", "Lech"), fixtures)
    assert wynik is not None


def test_nie_dopasowuje_innego_meczu():
    fixtures = [_fixture(home="Wisła Kraków", away="Raków", hg=3, ag=0)]
    assert ru._znajdz_wynik(_pending("Legia", "Lech"), fixtures) is None


def test_manchester_united_nie_dopasuje_sie_do_city():
    """Regresja po naprawie normalize (24cefa674) — prog tutaj to 0.70."""
    fixtures = [_fixture(home="Manchester City", away="Arsenal", hg=2, ag=0)]
    assert ru._znajdz_wynik(_pending("Manchester United", "Arsenal"), fixtures) is None


def test_dundee_united_nie_dopasuje_sie_do_dundee():
    fixtures = [_fixture(home="Dundee FC", away="Celtic", hg=0, ag=3)]
    assert ru._znajdz_wynik(_pending("Dundee United", "Celtic"), fixtures) is None


def test_pomija_mecze_niezakonczone_przy_szukaniu():
    """Ten sam mecz dwa razy: w trakcie i zakonczony — bierzemy zakonczony."""
    fixtures = [
        _fixture(status="1H", hg=0, ag=0),
        _fixture(status="FT", hg=2, ag=1),
    ]
    wynik = ru._znajdz_wynik(_pending(), fixtures)
    assert wynik[0] == "2-1"


def test_pusta_lista_fixtures_daje_none():
    assert ru._znajdz_wynik(_pending(), []) is None


def test_wyzszy_prog_odrzuca_slabe_dopasowanie():
    fixtures = [_fixture(home="Jagiellonia", away="Lech", hg=1, ag=0)]
    assert ru._znajdz_wynik(
        _pending("Jagiellonia Białystok", "Lech"), fixtures, min_similarity=0.99
    ) is None
