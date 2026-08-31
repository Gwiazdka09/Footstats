"""test_daily_phases_enrich_final.py — faza final: składy i sędzia.

PO CO: `_enrichuj_finalna_faza` to ostatni krok dziennego joba w Cloud Run.
Dokleja do kandydatów skład i sędziego z API-Football, a te pola (`lineup_ok`,
`lineup_star_penalty`, `referee_signal`) wchodzą potem do selekcji i pewności.
Doklejenie ich z NIEWŁAŚCIWEGO meczu jest gorsze niż niedoklejenie niczego —
model dostaje dane, którym ufa, a które opisują inne spotkanie.

Dopasowanie ma dwa etapy: dokładny po znormalizowanych nazwach, a gdy zawiedzie —
dopasowanie luźne. To właśnie luźne było dziurą: sprawdzało podciąg
(`gh in fh or fh in gh`), więc "Legia" łapała fixture "Legia II". Rezerwy grają
zwykle w ten sam weekend, więc oba mecze bywają w jednej puli.

Job musi też PRZEŻYĆ awarię API-Football — dzienny pipeline nie może paść
dlatego, że zewnętrzne źródło zwróciło błąd.
"""
from __future__ import annotations

import pytest

import footstats.core.daily_phases as dp
import footstats.core.lineup_strength as ls
import footstats.scrapers.flashscore_match as fm
import footstats.scrapers.lineup_scraper as lsc
import footstats.scrapers.referee_db as rdb


def _fixture(home: str, away: str, fid: int = 1, referee: str = "") -> dict:
    return {
        "fixture": {"id": fid, "referee": referee},
        "teams": {"home": {"name": home}, "away": {"name": away}},
    }


class _Odpowiedz:
    def __init__(self, fixtures):
        self._f = fixtures

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._f}


@pytest.fixture
def api(monkeypatch):
    """Podstawia całe otoczenie fazy final; zwraca uchwyt do sterowania nim."""
    stan = {"fixtures": [], "lineup": None, "referee": None, "fs": {"success": False},
            "lineup_wywolania": [], "fs_wywolania": []}

    def fake_get(url, **kw):
        return _Odpowiedz(stan["fixtures"])

    def fake_lineup(fixture_id, api_key):
        stan["lineup_wywolania"].append(fixture_id)
        return stan["lineup"]

    def fake_scrape(home, away):
        stan["fs_wywolania"].append((home, away))
        return stan["fs"]

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(lsc, "get_lineup", fake_lineup)
    monkeypatch.setattr(rdb, "get_referee", lambda n: stan["referee"])
    monkeypatch.setattr(fm, "scrape_match_with_search", fake_scrape)
    monkeypatch.setattr(ls, "lineup_confidence_penalty_v2", lambda *a: 0.1)
    monkeypatch.setattr(ls, "lineup_offensive_strength", lambda *a: 0.5)
    monkeypatch.delenv("FOOTSTATS_REFRESH_PLAYERS", raising=False)
    return stan


def _kandydat(gosp="Legia", gosc="Lech Poznan") -> dict:
    return {"gospodarz": gosp, "goscie": gosc}


# ── rezerwy: sedno błędu ────────────────────────────────────────────────────

@pytest.mark.parametrize("rezerwy_gosp,rezerwy_gosc", [
    ("Legia II", "Lech Poznan II"),
    ("Legia B", "Lech Poznan B"),
    ("Legia U21", "Lech Poznan U21"),
])
def test_fixture_rezerw_nie_jest_dopasowany(api, rezerwy_gosp, rezerwy_gosc):
    """Mecz rezerw nie może oddać składu ani sędziego pierwszemu zespołowi."""
    api["fixtures"] = [_fixture(rezerwy_gosp, rezerwy_gosc, fid=99, referee="Kowalski")]
    api["lineup"] = {"home": {"missing_key_players": False, "startXI": []},
                     "away": {"missing_key_players": False, "startXI": []}}
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    # Od 30.08 brak dopasowanego meczu NIE konczy wiersza (FlashScore stal
    # wczesniej za `continue` i przez miesiac nie byl wolany ani razu), wiec
    # `lineup_ok` jest jawnie None zamiast nieobecny. Niezmiennik bez zmian:
    # ZADNE dane z meczu rezerw nie moga trafic do pierwszego zespolu.
    assert k.get("lineup_ok") is None, "skład rezerw doklejony do pierwszego zespołu"
    assert "lineup_star_penalty" not in k, "kara ze składu rezerw doklejona"
    assert not k.get("referee_name"), "sędzia z meczu rezerw doklejony do pierwszego zespołu"
    assert api["lineup_wywolania"] == [], "pobrano skład dla cudzego meczu"


def test_pierwszy_zespol_dopasowany_gdy_obok_stoi_fixture_rezerw(api):
    """Obecność rezerw w puli nie może przesłonić właściwego meczu."""
    api["fixtures"] = [_fixture("Legia II", "Lech Poznan II", fid=99),
                       _fixture("Legia", "Lech Poznan", fid=7)]
    api["lineup"] = {"home": {"missing_key_players": False, "startXI": []},
                     "away": {"missing_key_players": False, "startXI": []}}
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert api["lineup_wywolania"] == [7]
    assert k["lineup_ok"] is True


# ── dopasowanie właściwe ────────────────────────────────────────────────────

def test_dokladne_dopasowanie_po_nazwach(api):
    api["fixtures"] = [_fixture("Legia", "Lech Poznan", fid=5)]
    api["lineup"] = {"home": {"missing_key_players": False, "startXI": []},
                     "away": {"missing_key_players": False, "startXI": []}}
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert k["lineup_ok"] is True
    assert api["lineup_wywolania"] == [5]


def test_luzne_dopasowanie_wariantu_nazwy(api):
    """Legalny wariant nazwy ma nadal trafiać — poprawka nie może go zabić."""
    api["fixtures"] = [_fixture("Legia Warszawa", "Lech Poznan", fid=11)]
    api["lineup"] = {"home": {"missing_key_players": False, "startXI": []},
                     "away": {"missing_key_players": False, "startXI": []}}
    k = _kandydat("Legia", "Lech Poznan")

    dp._enrichuj_finalna_faza([k], "klucz")

    assert api["lineup_wywolania"] == [11]


def test_brak_fixture_nie_dokleja_danych_z_api_football(api):
    """Kandydat spoza pokrycia AF nie dostaje NICZEGO z API-Football.

    Do 30.08 test brzmial "zostawia kandydata nietknietego" i sprawdzal rownosc
    calego slownika. Ta obserwacja opisywala BUG: `continue` na braku fixture
    zabezpieczal takze FlashScore, ktory jest zrodlem NIEZALEZNYM od AF. Konto
    AF jest zawieszone od 01.08, wiec produkcja przez miesiac raportowala
    `Final enrichment: 0/N`. Niezmiennik, ktory faktycznie ma znaczenie, to
    brak danych Z API-FOOTBALL — nie brak jakichkolwiek zmian w slowniku."""
    api["fixtures"] = [_fixture("Arka Gdynia", "Wisla Krakow", fid=3)]
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert k.get("lineup_ok") is None
    assert "lineup_star_penalty" not in k
    assert not k.get("referee_name")
    assert api["lineup_wywolania"] == []


def test_brak_lineup_ok_gdy_zawodnicy_kluczowi_brakuja(api):
    api["fixtures"] = [_fixture("Legia", "Lech Poznan", fid=5)]
    api["lineup"] = {"home": {"missing_key_players": True, "startXI": []},
                     "away": {"missing_key_players": False, "startXI": []}}
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert k["lineup_ok"] is False


# ── odporność na awarie ─────────────────────────────────────────────────────

def test_brak_klucza_nie_rusza_sieci(monkeypatch):
    """Bez klucza faza ma odpuścić, nie próbować i nie wybuchać."""
    def wybucha(*a, **kw):
        raise AssertionError("sięgnięto po sieć mimo braku klucza")

    monkeypatch.setattr("requests.get", wybucha)
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "")

    assert k == {"gospodarz": "Legia", "goscie": "Lech Poznan"}


def test_awaria_api_nie_wywraca_joba(api, monkeypatch):
    """Dzienny pipeline nie może paść przez błąd zewnętrznego źródła."""
    def wybucha(*a, **kw):
        raise OSError("connection reset")

    monkeypatch.setattr("requests.get", wybucha)
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")  # nie rzuca

    assert "lineup_ok" not in k


def test_pusta_lista_fixtures_nie_wywraca(api):
    """Zawieszone konto AF oddaje dokladnie to: pusta liste meczow."""
    api["fixtures"] = []
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert k.get("lineup_ok") is None
    assert api["lineup_wywolania"] == []


def test_fixture_bez_nazw_druzyn_pomijany(api):
    """Śmieciowy wpis z API nie może wpaść do indeksu jako pasujący do wszystkiego."""
    api["fixtures"] = [_fixture("", "", fid=4)]
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert api["lineup_wywolania"] == []


# ── sędzia ──────────────────────────────────────────────────────────────────

def test_sedzia_zapisany_z_fixture(api):
    api["fixtures"] = [_fixture("Legia", "Lech Poznan", fid=5, referee="Jan Kowalski, POL")]
    # 4.2 bylo PONIZEJ progu KARTKOWY (4.3), a test i tak zadal "KARTKOWY" —
    # bo atrapa `referee_signal` zwracala te stala niezaleznie od statystyk.
    # Po rozdzieleniu odczytu od klasyfikacji sygnal liczy sie z tych liczb,
    # wiec dane musza odpowiadac temu, co test twierdzi.
    api["referee"] = {"avg_yellow": 5.1, "n_matches": 30}
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert k["referee_name"] == "Jan Kowalski"
    assert k["referee_signal"] == "KARTKOWY"
    assert k["referee_neutral"] is False
    assert k["referee_avg_y"] == 5.1


def test_flashscore_tylko_gdy_brak_sedziego(api):
    """Fallback kosztuje scraping — nie wolno go odpalać, gdy sędzia już jest."""
    api["fixtures"] = [_fixture("Legia", "Lech Poznan", fid=5, referee="Jan Kowalski")]
    api["referee"] = {"avg_yellow": 4.0, "n_matches": 10}

    dp._enrichuj_finalna_faza([_kandydat()], "klucz")

    assert api["fs_wywolania"] == []


def test_flashscore_uzupelnia_brakujacego_sedziego(api):
    api["fixtures"] = [_fixture("Legia", "Lech Poznan", fid=5, referee="")]
    api["fs"] = {"success": True, "referee": "Anna Nowak", "stadium": "Łazienkowska",
                 "absences": {"home": [{"name": "Kowal", "reason": "uraz"}], "away": []}}
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert api["fs_wywolania"] == [("Legia", "Lech Poznan")]
    assert k["referee_name"] == "Anna Nowak"
    assert k["fs_absencje_g"] == "Kowal (uraz)"
    assert "fs_absencje_a" not in k
    assert k["stadium"] == "Łazienkowska"


def test_flashscore_wolany_gdy_api_football_nic_nie_zna(api):
    """Odblokowane 30.08: FlashScore jest zrodlem NIEZALEZNYM od API-Football,
    a stal za `continue` na braku fixture. Konto AF zawieszone od 01.08 →
    przez miesiac nie odpalil sie ani razu, a produkcja raportowala
    `Final enrichment: 0/N`."""
    api["fixtures"] = []
    api["fs"] = {"success": True, "referee": "Szymon Marciniak",
                 "absences": {"home": [{"name": "Kowalski", "reason": "uraz"}],
                              "away": []}}
    k = _kandydat()

    dp._enrichuj_finalna_faza([k], "klucz")

    assert api["fs_wywolania"] == [("Legia", "Lech Poznan")]
    assert k["referee_name"] == "Szymon Marciniak"
    assert "Kowalski" in k.get("fs_absencje_g", "")
