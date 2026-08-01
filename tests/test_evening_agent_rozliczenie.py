"""test_evening_agent_rozliczenie.py — dopasowanie meczu i status kuponu.

PO CO: to jest ścieżka, którą kupon dostaje WYNIK i zamienia się w wygraną albo
przegraną. Pomyłka tutaj to nie gorsza predykcja, tylko źle rozliczone pieniądze.

Sedno: dopasowanie meczu liczyło ŚREDNIĄ podobieństw obu drużyn
(`(sim_gosp + sim_gosc) / 2 >= 0.6`). Jedno idealne trafienie przepychało wtedy
złe dopasowanie drugiej strony:

    kupon "Legia – Lech Poznań"  vs  fixture "Legia – Lechia Gdańsk"
    1.00 + 0.58 = średnia 0.79  ->  PRZECHODZI, choć Lech/Lechia to 0.58

Obie drużyny grają w Ekstraklasie i obie mierzą się z Legią, więc to nie jest
przypadek teoretyczny. Ten sam mechanizm łapał "Rapid – Altach" na fixture
"Rapid – Austria Wien" (0.67).

Poprawka: OBIE strony muszą przejść próg (`min`, nie średnia) — tak jak
w `daily_phases`, `api_football`, `daily_agent` i `sofascore_odds`. Próg zostaje
0.6, żeby nie ruszać kalibracji; zmienia się tylko to, że nie da się go obejść
jedną dobrą połową.

Druga rzecz: API-Football zgłasza problemy z kontem przy HTTP 200 (patrz
`test_api_football_bledy_w_tresci.py`). W rozliczeniach objawia się to tym, że
`_fetch_results_today` zwraca pustą listę i WSZYSTKIE kupony zostają ACTIVE —
cicho, bez śladu, że źródło padło.
"""
from __future__ import annotations

import pytest

import footstats.evening_agent as ea

PROG = 0.6


def _fixture(home: str, away: str, hg=2, ag=1, status="FT", fid=1, ht=None) -> dict:
    f = {
        "fixture": {"id": fid, "status": {"short": status}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": hg, "away": ag},
    }
    if ht is not None:
        f["score"] = {"halftime": {"home": ht[0], "away": ht[1]}}
    return f


# ── _wynik_z_fixture ────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["FT", "AET", "PEN"])
def test_mecz_zakonczony_daje_wynik(status):
    """Dogrywka i karne to nadal zakończony mecz."""
    assert ea._wynik_z_fixture(_fixture("Legia", "Lech", status=status)) == ("Legia", "Lech", "2-1")


@pytest.mark.parametrize("status", ["NS", "1H", "HT", "2H", "PST", "CANC", "SUSP", ""])
def test_mecz_niezakonczony_to_brak_wyniku(status):
    """Rozliczenie meczu w trakcie zamroziłoby wynik z 30. minuty."""
    assert ea._wynik_z_fixture(_fixture("Legia", "Lech", status=status)) is None


@pytest.mark.parametrize("hg,ag", [(None, 1), (2, None), (None, None)])
def test_brak_goli_to_brak_wyniku(hg, ag):
    """Status FT bez goli to niekompletne dane, nie remis 0-0."""
    assert ea._wynik_z_fixture(_fixture("Legia", "Lech", hg=hg, ag=ag)) is None


def test_polowa_doklejona_do_wyniku():
    """Rynki typu "gol w każdej połowie" bez tego nie dają się rozliczyć."""
    _, _, wynik = ea._wynik_z_fixture(_fixture("Legia", "Lech", 3, 1, ht=(1, 1)))

    assert wynik == "3-1;HT:1-1"


def test_brak_danych_polowy_nie_psuje_wyniku():
    _, _, wynik = ea._wynik_z_fixture(_fixture("Legia", "Lech", 3, 1, ht=(None, None)))

    assert wynik == "3-1"


def test_pusty_fixture_nie_wywala():
    assert ea._wynik_z_fixture({}) is None


# ── _find_result: OBIE strony muszą pasować ────────────────────────────────

def test_dokladne_dopasowanie():
    fixtures = [_fixture("Legia Warszawa", "Lech Poznan", 2, 1)]

    assert ea._find_result("Legia Warszawa", "Lech Poznan", fixtures) == "2-1"


def test_podobna_nazwa_gosci_nie_przechodzi_przez_srednia():
    """REGRESJA: 1.00 + 0.58 = 0.79 >= 0.6 przepuszczało mecz z INNĄ drużyną.
    Kupon na Lech Poznań rozliczyłby się wynikiem Lechii Gdańsk."""
    fixtures = [_fixture("Legia Warszawa", "Lechia Gdansk", 4, 0)]

    assert ea._find_result("Legia Warszawa", "Lech Poznan", fixtures) is None


def test_podobna_nazwa_gospodarza_tez_nie_przechodzi():
    fixtures = [_fixture("Lechia Gdansk", "Lech Poznan", 4, 0)]

    assert ea._find_result("Legia Warszawa", "Lech Poznan", fixtures) is None


def test_inny_rywal_tego_samego_klubu_odrzucony():
    """"Rapid – Altach" nie może zebrać wyniku z "Rapid – Austria Wien"."""
    fixtures = [_fixture("Rapid Wien", "Austria Wien", 3, 3)]

    assert ea._find_result("Rapid Wien", "Rheindorf Altach", fixtures) is None


def test_rezerwy_nie_rozliczaja_pierwszego_zespolu():
    fixtures = [_fixture("Legia II", "Lech II", 5, 0)]

    assert ea._find_result("Legia", "Lech", fixtures) is None


def test_wariant_nazwy_nadal_pasuje():
    """Poprawka nie może zablokować legalnych wariantów zapisu."""
    fixtures = [_fixture("Gent", "KV Mechelen", 1, 0)]

    assert ea._find_result("Gent", "Mechelen", fixtures) == "1-0"


def test_wybiera_najlepsze_dopasowanie_z_wielu():
    fixtures = [
        _fixture("Legia Warszawa", "Lechia Gdansk", 4, 0),
        _fixture("Legia Warszawa", "Lech Poznan", 2, 1),
    ]

    assert ea._find_result("Legia Warszawa", "Lech Poznan", fixtures) == "2-1"


def test_brak_dopasowania_to_none():
    fixtures = [_fixture("Arka Gdynia", "Wisla Krakow")]

    assert ea._find_result("Legia", "Lech", fixtures) is None


def test_mecz_w_trakcie_nie_jest_zrodlem_wyniku():
    fixtures = [_fixture("Legia Warszawa", "Lech Poznan", 1, 0, status="1H")]

    assert ea._find_result("Legia Warszawa", "Lech Poznan", fixtures) is None


def test_pusta_lista_fixtures():
    assert ea._find_result("Legia", "Lech", []) is None


# ── _find_fixture_id: to samo dopasowanie, użyte do CLV ────────────────────

def test_fixture_id_znaleziony():
    fixtures = [_fixture("Legia Warszawa", "Lech Poznan", fid=77)]

    assert ea._find_fixture_id("Legia Warszawa", "Lech Poznan", fixtures) == 77


def test_fixture_id_nie_bierze_innego_rywala():
    """Zły fixture = closing odds z cudzego meczu, czyli fałszywy CLV."""
    fixtures = [_fixture("Legia Warszawa", "Lechia Gdansk", fid=77)]

    assert ea._find_fixture_id("Legia Warszawa", "Lech Poznan", fixtures) is None


def test_fixture_id_brak_dopasowania():
    assert ea._find_fixture_id("Legia", "Lech", [_fixture("Arka", "Wisla")]) is None


# ── _status_kuponu ─────────────────────────────────────────────────────────

def test_wszystkie_nogi_trafione_to_wygrana():
    assert ea._status_kuponu(["WIN", "WIN", "WIN"]) == "WON"


def test_jedna_przegrana_przesadza_o_calosci():
    """Akumulator: jedna wpadka zabija kupon niezależnie od reszty."""
    assert ea._status_kuponu(["WIN", "LOSS", "WIN"]) == "LOST"


def test_oczekujaca_noga_trzyma_kupon_aktywnym():
    """Kupon z nierozegranym meczem nie może zostać rozliczony wcześniej."""
    assert ea._status_kuponu(["WIN", "PENDING"]) == ea.STATUS_ACTIVE


def test_oczekujaca_wazniejsza_niz_przegrana():
    """Nawet z przegraną nogą czekamy — VOID reszty mógłby zmienić wynik."""
    assert ea._status_kuponu(["LOSS", "PENDING"]) == ea.STATUS_ACTIVE


def test_wszystko_uniewaznione_to_void():
    assert ea._status_kuponu(["VOID", "VOID"]) == "VOID"


def test_czesc_uniewazniona_to_partial():
    assert ea._status_kuponu(["WIN", "VOID"]) == "PARTIAL"


def test_kupon_bez_nog_to_void():
    """Pusta lista nóg nie może wyjść na wygraną przez `all([]) == True`."""
    assert ea._status_kuponu([]) == "VOID"


# ── _fetch_results_today: awaria źródła nie może udawać "brak meczów" ──────

class _Resp:
    def __init__(self, dane, status=200):
        self.status_code = status
        self._dane = dane

    def json(self):
        return self._dane


@pytest.fixture
def siec(monkeypatch):
    stan = {"odpowiedzi": [], "wywolania": 0}

    def fake_get(url, **kw):
        stan["wywolania"] += 1
        o = stan["odpowiedzi"].pop(0) if stan["odpowiedzi"] else _Resp({"response": []})
        if isinstance(o, Exception):
            raise o
        return o

    monkeypatch.setattr(ea.requests, "get", fake_get)
    # `time` jest importowane WEWNATRZ `_fetch_results_today`, nie na poziomie
    # modulu — podmieniamy wiec w samym `time`, nie w `ea`.
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(ea.console, "print", lambda *a, **k: None)
    return stan


def test_wyniki_pobrane(siec):
    siec["odpowiedzi"] = [_Resp({"response": [_fixture("Legia", "Lech")]})]

    assert len(ea._fetch_results_today("klucz", "2026-08-01")) == 1


def test_ponawia_przy_bledzie_serwera(siec):
    siec["odpowiedzi"] = [_Resp(None, status=500), _Resp({"response": [_fixture("A", "B")]})]

    assert len(ea._fetch_results_today("klucz", "2026-08-01")) == 1
    assert siec["wywolania"] == 2


def test_poddaje_sie_po_wyczerpaniu_prob(siec):
    siec["odpowiedzi"] = [_Resp(None, status=500)] * 3

    assert ea._fetch_results_today("klucz", "2026-08-01", retries=3) == []
    assert siec["wywolania"] == 3


def test_awaria_sieci_nie_wywala_rozliczenia(siec):
    siec["odpowiedzi"] = [ea.requests.RequestException("timeout")] * 3

    assert ea._fetch_results_today("klucz", "2026-08-01", retries=3) == []


def test_dzien_bez_meczow_to_pusta_lista(siec):
    siec["odpowiedzi"] = [_Resp({"response": []})]

    assert ea._fetch_results_today("klucz", "2026-12-25") == []
