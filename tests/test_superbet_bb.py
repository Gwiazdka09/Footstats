"""test_superbet_bb.py — kursy BetBuilder z Superbet.

PO CO: moduł miał 13% pokrycia, a dostarcza KURSY, z których budowane są kupony
BetBuilder. Dwie rzeczy w `znajdz_url_meczu` są nie do obrony:

  * dopasowanie po 6 pierwszych znakach nazwy — "Manchester United" i
    "Manchester City" dają ten sam prefiks "manche", więc warunek "obie drużyny
    w URL-u" spełniał DOWOLNY mecz Manchesteru;
  * fallback `return hrefs[0]` — gdy nic nie pasowało, zwracany był PIERWSZY
    wynik wyszukiwania. Dalej `pobierz_kursy_bb` wyciąga z niego match_id
    i pobiera kursy CAŁKIEM INNEGO meczu, a trafiają one do wyniku pod kluczem
    "Dom vs Gost", czyli podpisane nazwą meczu, którego nie dotyczą.

Ścieżka jest za flagą `--bb` (domyślnie wyłączona, wymaga loginu Superbet), więc
nie psuła danych produkcyjnych — ale brak kursów jest zawsze lepszy niż kursy
z cudzego meczu.
"""
from __future__ import annotations

import pytest

import footstats.scrapers.superbet_bb as bb


# ── _match_id_z_url ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,oczekiwane", [
    ("https://superbet.pl/kursy/pilka-nozna/legia-lech-1234567", "1234567"),
    ("https://superbet.pl/kursy/pilka-nozna/legia-lech-1234567/", "1234567"),
    ("https://superbet.pl/kursy/pilka-nozna/legia-lech-1234567?x=1", "1234567"),
    ("https://superbet.pl/kursy/pilka-nozna/legia-lech-12345678901", "12345678901"),
])
def test_match_id_wyciagniety(url, oczekiwane):
    assert bb._match_id_z_url(url) == oczekiwane


@pytest.mark.parametrize("url", [
    "https://superbet.pl/kursy/pilka-nozna/legia-lech",       # brak id
    "https://superbet.pl/kursy/pilka-nozna/legia-lech-12345",  # za krotkie (<7)
    "",
])
def test_brak_match_id(url):
    assert bb._match_id_z_url(url) is None


# ── _parsuj_markets_api ─────────────────────────────────────────────────────

def _market(nazwa: str, odds: list[dict]) -> dict:
    return {"name": nazwa, "odds": odds}


def _odd(nazwa: str, cena, status: str = "ACTIVE") -> dict:
    return {"name": nazwa, "price": cena, "status": status}


def test_parsuje_rynki_na_typy():
    dane = {"markets": [_market("Wynik meczu", [_odd("Legia", 2.10), _odd("Lech", 3.40)])]}

    typy = bb._parsuj_markets_api(dane)

    assert [(t.nazwa, t.kurs) for t in typy] == [
        ("Wynik meczu: Legia", 2.1), ("Wynik meczu: Lech", 3.4)]


def test_pomija_kursy_nieaktywne():
    """Zawieszony kurs w kuponie to kupon nie do postawienia."""
    dane = {"markets": [_market("Wynik", [_odd("Legia", 2.1, status="SUSPENDED"),
                                          _odd("Lech", 3.4)])]}

    typy = bb._parsuj_markets_api(dane)

    assert [t.nazwa for t in typy] == ["Wynik: Lech"]


@pytest.mark.parametrize("rynek", ["Awans", "Handicap azjatycki", "Podwójna szansa",
                                   "AWANS do finału", "podwójna szansa + BTTS"])
def test_pomija_rynki_wykluczone(rynek):
    dane = {"markets": [_market(rynek, [_odd("X", 2.0)])]}

    assert bb._parsuj_markets_api(dane) == []


@pytest.mark.parametrize("rynek", ["Zawodnik - strzelec", "Strzelec pierwszego gola",
                                   "Asystent meczu", "Player - shots"])
def test_pomija_rynki_zawodnikow_domyslnie(rynek):
    """Rynki graczy to ~1400 typów zamiast ~80 — bloat, nie wartość."""
    dane = {"markets": [_market(rynek, [_odd("Kowalski", 3.0)])]}

    assert bb._parsuj_markets_api(dane) == []


def test_rynki_zawodnikow_na_zadanie():
    dane = {"markets": [_market("Strzelec gola", [_odd("Kowalski", 3.0)])]}

    typy = bb._parsuj_markets_api(dane, filtruj_gracze=False)

    assert len(typy) == 1


@pytest.mark.parametrize("kurs", [1.0, 1.001, 0.5])
def test_pomija_kursy_na_progu_i_ponizej(kurs):
    """Pewniaki nie wnoszą nic do kuponu, a psują iloczyn kursów."""
    dane = {"markets": [_market("Wynik", [_odd("Legia", kurs)])]}

    assert bb._parsuj_markets_api(dane) == []


@pytest.mark.parametrize("cena", [None, "abc", ""])
def test_pomija_niepoprawna_cene(cena):
    dane = {"markets": [_market("Wynik", [_odd("Legia", cena)])]}

    assert bb._parsuj_markets_api(dane) == []


def test_cena_jako_string_akceptowana():
    dane = {"markets": [_market("Wynik", [_odd("Legia", "2.15")])]}

    assert bb._parsuj_markets_api(dane)[0].kurs == 2.15


def test_pomija_rynek_bez_nazwy():
    dane = {"markets": [_market("   ", [_odd("Legia", 2.1)])]}

    assert bb._parsuj_markets_api(dane) == []


def test_pomija_selekcje_bez_nazwy():
    dane = {"markets": [_market("Wynik", [_odd("  ", 2.1)])]}

    assert bb._parsuj_markets_api(dane) == []


def test_pusta_odpowiedz_nie_wywraca():
    assert bb._parsuj_markets_api({}) == []
    assert bb._parsuj_markets_api({"markets": []}) == []


def test_nazwa_przycieta_do_stu_znakow():
    dane = {"markets": [_market("R" * 80, [_odd("S" * 80, 2.1)])]}

    assert len(bb._parsuj_markets_api(dane)[0].nazwa) == 100


# ── znajdz_url_meczu ────────────────────────────────────────────────────────

class _Page:
    """Atrapa strony Playwright — oddaje ustaloną listę linków."""

    def __init__(self, hrefs: list[str]):
        self.hrefs = hrefs
        self.odwiedzone: list[str] = []

    def goto(self, url, **kw):
        self.odwiedzone.append(url)

    def evaluate(self, skrypt):
        return self.hrefs


@pytest.fixture(autouse=True)
def _bez_popupow_i_czekania(monkeypatch):
    monkeypatch.setattr(bb, "zamknij_popup", lambda *a, **k: None)
    monkeypatch.setattr(bb.time, "sleep", lambda *_: None)


BAZA = "https://superbet.pl/kursy/pilka-nozna/"


def test_znajduje_mecz_z_obiema_druzynami():
    page = _Page([BAZA + "legia-warszawa-lech-poznan-1234567"])

    assert bb.znajdz_url_meczu(page, "Legia Warszawa", "Lech Poznan") == page.hrefs[0]


def test_wybiera_mecz_z_obiema_druzynami_sposrod_wielu():
    trafny = BAZA + "legia-warszawa-lech-poznan-1234567"
    page = _Page([BAZA + "legia-warszawa-arka-gdynia-1111111", trafny])

    assert bb.znajdz_url_meczu(page, "Legia Warszawa", "Lech Poznan") == trafny


def test_derby_nie_myli_druzyn():
    """"Manchester United" i "Manchester City" dawały ten sam prefiks "manche",
    więc mecz United z Arsenalem spełniał warunek "obie drużyny w URL-u"."""
    page = _Page([BAZA + "manchester-united-arsenal-1234567"])

    assert bb.znajdz_url_meczu(page, "Manchester United", "Manchester City") is None


def test_rezerwy_nie_udaja_pierwszego_zespolu():
    page = _Page([BAZA + "legia-ii-warszawa-lech-ii-poznan-1234567"])

    assert bb.znajdz_url_meczu(page, "Legia Warszawa", "Lech Poznan") is None


def test_brak_dopasowania_to_none_a_nie_pierwszy_lepszy():
    """REGRESJA: `return hrefs[0]` oddawał kursy CAŁKIEM INNEGO meczu, podpisane
    nazwą meczu, którego nie dotyczą."""
    page = _Page([BAZA + "arka-gdynia-wisla-krakow-1111111",
                  BAZA + "gornik-zabrze-piast-gliwice-2222222"])

    assert bb.znajdz_url_meczu(page, "Legia Warszawa", "Lech Poznan") is None


def test_brak_wynikow_to_none():
    assert bb.znajdz_url_meczu(_Page([]), "Legia", "Lech") is None


def test_blad_strony_to_none():
    class _Zepsuta(_Page):
        def goto(self, url, **kw):
            raise RuntimeError("timeout")

    assert bb.znajdz_url_meczu(_Zepsuta([]), "Legia", "Lech") is None


# ── pobierz_kursy_bb ────────────────────────────────────────────────────────

class _Odpowiedz:
    def __init__(self, dane, ok=True, status=200):
        self._dane, self.ok, self.status = dane, ok, status

    def json(self):
        return self._dane


class _Request:
    def __init__(self, odpowiedz):
        self._o = odpowiedz
        self.wywolania: list[str] = []

    def get(self, url, **kw):
        self.wywolania.append(url)
        if isinstance(self._o, Exception):
            raise self._o
        return self._o


class _PageZApi(_Page):
    def __init__(self, odpowiedz):
        super().__init__([])
        self.request = _Request(odpowiedz)


def test_brak_match_id_konczy_bez_zapytania():
    page = _PageZApi(_Odpowiedz({}))

    assert bb.pobierz_kursy_bb(page, BAZA + "legia-lech") == []
    assert page.request.wywolania == []


def test_api_niedostepne_zwraca_puste():
    page = _PageZApi(_Odpowiedz(None, ok=False, status=503))

    assert bb.pobierz_kursy_bb(page, BAZA + "legia-lech-1234567") == []


def test_blad_api_zwraca_puste_zamiast_wywalac():
    page = _PageZApi(RuntimeError("connection reset"))

    assert bb.pobierz_kursy_bb(page, BAZA + "legia-lech-1234567") == []


def test_dedup_zostawia_najwyzszy_kurs():
    """Ten sam typ w dwóch rynkach — do kuponu bierzemy lepszy kurs."""
    dane = {"markets": [_market("Wynik", [_odd("Legia", 2.10)]),
                        _market("Wynik", [_odd("Legia", 2.35)])]}
    page = _PageZApi(_Odpowiedz(dane))

    typy = bb.pobierz_kursy_bb(page, BAZA + "legia-lech-1234567")

    assert [(t.nazwa, t.kurs) for t in typy] == [("Wynik: Legia", 2.35)]


def test_match_id_trafia_do_zapytania():
    page = _PageZApi(_Odpowiedz({"markets": []}))

    bb.pobierz_kursy_bb(page, BAZA + "legia-lech-7654321")

    assert "match_id=7654321" in page.request.wywolania[0]
