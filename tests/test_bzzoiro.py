"""test_bzzoiro.py — źródło predykcji ML i kursów (sports.bzzoiro.com).

PO CO: moduł miał 32,7% pokrycia, a dostarcza DWIE rzeczy, na których stoi cały
model: prawdopodobieństwa CatBoosta i kursy bukmacherskie.

`_bzz_parse_prob` obsługuje PIĘĆ formatów odpowiedzi API, bo format zmieniał się
w czasie. Każdy nierozpoznany format zwraca `None`, co dalej ląduje jako
"brak danych ML" — cicho i bez wyjątku. Test na każdy format to jedyna rzecz,
która pilnuje, że dodanie szóstego nie zepsuje pięciu poprzednich.

Najgroźniejszy szczegół to granica ułamek/procent: `0.55` znaczy 55%, ale `1.0`
znaczy 1%, nie 100%. Warunek jest ŚCIŚLE `< 1.0` i pomylenie go z `<= 1.0`
zamieniłoby pewniaka w typ nie do postawienia (albo odwrotnie).

`porownaj_z_poisson` to cross-walidacja dwóch modeli — jej alert jest sygnałem
"jeden z modeli się myli", więc musi zapalać się na właściwym progu.
"""
from __future__ import annotations

import pytest

import footstats.scrapers.bzzoiro as bz
from footstats.config import BZZOIRO_MAX_ROZN
from footstats.scrapers.bzzoiro import BzzoiroClient, _bzz_parse_prob


# ── _bzz_parse_prob: formaty ────────────────────────────────────────────────

def test_format_a_percent_ze_znakiem_procentu():
    """Format główny — wartości przychodzą jako "55%"."""
    pw, pr, pp, bt, o25 = _bzz_parse_prob(
        {"percent": {"home": "55%", "draw": "25%", "away": "20%"}})

    assert (pw, pr, pp) == (55.0, 25.0, 20.0)


def test_format_a_alias_percentages():
    wynik = _bzz_parse_prob({"percentages": {"home": 55, "draw": 25, "away": 20}})

    assert wynik[:3] == (55.0, 25.0, 20.0)


def test_format_b_home_win_prob():
    wynik = _bzz_parse_prob({"home_win_prob": 0.55, "draw_prob": 0.25,
                             "away_win_prob": 0.20})

    assert wynik[:3] == (55.0, 25.0, 20.0)


def test_format_c_home_draw_away():
    wynik = _bzz_parse_prob({"home": 55, "draw": 25, "away": 20})

    assert wynik[:3] == (55.0, 25.0, 20.0)


def test_format_d_zagniezdzony():
    wynik = _bzz_parse_prob({"predictions": {"home": 55, "draw": 25, "away": 20}})

    assert wynik[:3] == (55.0, 25.0, 20.0)


def test_format_d_alias_prediction():
    wynik = _bzz_parse_prob({"prediction": {"home": 55, "draw": 25, "away": 20}})

    assert wynik[:3] == (55.0, 25.0, 20.0)


def test_format_e_prob_home_win():
    """Aktualny format /predictions/."""
    wynik = _bzz_parse_prob({"prob_home_win": 55, "prob_draw": 25,
                             "prob_away_win": 20, "prob_btts_yes": 60,
                             "prob_over_25": 48})

    assert wynik == (55.0, 25.0, 20.0, 60.0, 48.0)


# ── granica ułamek / procent ────────────────────────────────────────────────

def test_ulamek_zamieniany_na_procent():
    assert _bzz_parse_prob({"home": 0.55, "draw": 0.25, "away": 0.20})[:3] == (55.0, 25.0, 20.0)


def test_jedynka_to_jeden_procent_nie_sto():
    """Warunek jest ŚCIŚLE `< 1.0`. Przy `<= 1.0` wartość 1.0 urosłaby do 100%
    i zamieniła skrajnie mało prawdopodobny typ w pewniaka."""
    wynik = _bzz_parse_prob({"home": 98.0, "draw": 1.0, "away": 1.0})

    assert wynik[1] == 1.0


def test_zero_nie_jest_ulamkiem():
    """`0 < f` — zero zostaje zerem, nie idzie przez mnożenie."""
    wynik = _bzz_parse_prob({"home": 80, "draw": 20, "away": 0})

    assert wynik[2] == 0.0


# ── normalizacja ────────────────────────────────────────────────────────────

def test_prawdopodobienstwa_sumuja_sie_do_stu():
    pw, pr, pp, _, _ = _bzz_parse_prob({"home": 60, "draw": 30, "away": 30})

    assert pw + pr + pp == pytest.approx(100.0, abs=0.1)


def test_suma_ponad_sto_jest_skalowana():
    wynik = _bzz_parse_prob({"home": 120, "draw": 60, "away": 60})

    assert wynik[:3] == (50.0, 25.0, 25.0)


def test_btts_i_over_przyciete_do_zakresu():
    """Wartość spoza 0-100 to błąd źródła, nie powód do wywalenia się."""
    wynik = _bzz_parse_prob({"percent": {"home": 55, "draw": 25, "away": 20,
                                         "btts": 150, "over_2_5": -20}})

    assert wynik[3] == 100.0
    assert wynik[4] == 0.0


# ── odrzucanie śmieci ───────────────────────────────────────────────────────

@pytest.mark.parametrize("wejscie", [None, {}, [], "tekst", 42])
def test_smieci_daja_none(wejscie):
    assert _bzz_parse_prob(wejscie) is None


def test_nieznany_format_daje_none():
    assert _bzz_parse_prob({"cos_zupelnie_innego": 1}) is None


def test_suma_ponizej_progu_przechodzi_do_nastepnego_formatu():
    """Same zera w formacie A nie mogą przesłonić poprawnych danych w C."""
    wynik = _bzz_parse_prob({"percent": {"home": 0, "draw": 0, "away": 0},
                             "home": 55, "draw": 25, "away": 20})

    assert wynik[:3] == (55.0, 25.0, 20.0)


def test_wartosci_nieliczbowe_traktowane_jak_zero():
    assert _bzz_parse_prob({"home": "brak", "draw": "brak", "away": "brak"}) is None


# ── porownaj_z_poisson ──────────────────────────────────────────────────────

def test_brak_ml_to_brak_zgodnosci():
    wynik = BzzoiroClient.porownaj_z_poisson(50, 30, 20, None)

    assert wynik["zgodnosc"] is None
    assert "brak danych" in wynik["opis"]


def test_nieznany_format_ml_zglaszany_wprost():
    wynik = BzzoiroClient.porownaj_z_poisson(50, 30, 20, {"nieznane": 1})

    assert wynik["zgodnosc"] is None
    assert "nieznany format" in wynik["opis"]


def test_modele_zgodne():
    wynik = BzzoiroClient.porownaj_z_poisson(
        55, 25, 20, {"home": 58, "draw": 22, "away": 20})

    assert wynik["zgodnosc"] is True
    assert wynik["faw_pois"] == wynik["faw_ml"] == "1"


def test_modele_niezgodne():
    wynik = BzzoiroClient.porownaj_z_poisson(
        55, 25, 20, {"home": 20, "draw": 25, "away": 55})

    assert wynik["zgodnosc"] is False
    assert (wynik["faw_pois"], wynik["faw_ml"]) == ("1", "2")


def test_faworytem_moze_byc_remis():
    wynik = BzzoiroClient.porownaj_z_poisson(
        25, 50, 25, {"home": 25, "draw": 50, "away": 25})

    assert wynik["faw_pois"] == "X"


def test_alert_gdy_roznica_przekracza_prog():
    """Alert to sygnał "jeden z modeli się myli" — musi zapalać się na progu.

    Wartości ML są NORMALIZOWANE, więc różnicę trzeba liczyć na sumie 100:
    tu ml_1 = 55, Poisson 80 → różnica 25 > próg 20.
    """
    wynik = BzzoiroClient.porownaj_z_poisson(
        80, 10, 10, {"home": 55, "draw": 25, "away": 20})

    assert wynik["roznica_max"] == pytest.approx(80 - 55, abs=0.1)
    assert wynik["roznica_max"] > BZZOIRO_MAX_ROZN
    assert wynik["alert"] is True
    assert "ALERT" in wynik["opis"]


def test_brak_alertu_przy_malej_roznicy():
    wynik = BzzoiroClient.porownaj_z_poisson(
        55, 25, 20, {"home": 57, "draw": 24, "away": 19})

    assert wynik["alert"] is False
    assert "ALERT" not in wynik["opis"]


def test_blad_parsowania_nie_wywala_porownania():
    class _Zlosliwy(dict):
        def get(self, *a, **kw):
            raise TypeError("niespodzianka")

    wynik = BzzoiroClient.porownaj_z_poisson(50, 30, 20, _Zlosliwy({"x": 1}))

    assert wynik["zgodnosc"] is None
    assert "blad parsowania" in wynik["opis"]


# ── HTTP: waliduj / _get ────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status, dane=None):
        self.status_code = status
        self._dane = dane or {}

    def json(self):
        return self._dane


@pytest.fixture
def siec(monkeypatch):
    """Podstawia requests.get i wycisza backoff; zwraca uchwyt do sterowania."""
    stan = {"odpowiedzi": [], "wywolania": [], "spanie": []}

    def fake_get(url, **kw):
        stan["wywolania"].append((url, kw.get("params")))
        o = stan["odpowiedzi"].pop(0) if stan["odpowiedzi"] else _Resp(200, {})
        if isinstance(o, Exception):
            raise o
        return o

    monkeypatch.setattr(bz.requests, "get", fake_get)
    monkeypatch.setattr(bz.time, "sleep", lambda s: stan["spanie"].append(s))
    monkeypatch.setattr(bz, "_cache_get", lambda k: None)
    monkeypatch.setattr(bz, "_cache_set", lambda k, v: None)
    return stan


def test_waliduj_poprawny_klucz(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": [1, 2, 3]})]

    ok, opis = BzzoiroClient("klucz").waliduj()

    assert ok is True
    assert "3 lig" in opis


def test_waliduj_zly_klucz_bez_ponawiania(siec):
    """401 nie naprawi się po retry — ponawianie to tylko strata czasu."""
    siec["odpowiedzi"] = [_Resp(401)]

    ok, opis = BzzoiroClient("zly").waliduj()

    assert ok is False
    assert "401" in opis
    assert len(siec["wywolania"]) == 1


def test_waliduj_ponawia_przy_bledzie_serwera(siec):
    siec["odpowiedzi"] = [_Resp(500), _Resp(500), _Resp(200, {"results": []})]

    ok, _ = BzzoiroClient("klucz").waliduj()

    assert ok is True
    assert len(siec["wywolania"]) == 3


def test_waliduj_poddaje_sie_po_trzech_probach(siec):
    siec["odpowiedzi"] = [_Resp(500), _Resp(500), _Resp(500)]

    ok, opis = BzzoiroClient("klucz").waliduj()

    assert ok is False
    assert "500" in opis


def test_waliduj_ponawia_przy_bledzie_sieci(siec):
    siec["odpowiedzi"] = [bz.requests.RequestException("timeout"),
                          _Resp(200, {"results": []})]

    ok, _ = BzzoiroClient("klucz").waliduj()

    assert ok is True


def test_get_oddaje_z_cache_bez_zapytania(monkeypatch, siec):
    monkeypatch.setattr(bz, "_cache_get", lambda k: {"z": "cache"})

    assert BzzoiroClient("k")._get("/x") == {"z": "cache"}
    assert siec["wywolania"] == []


def test_get_ponawia_przy_przecizeniu(siec):
    siec["odpowiedzi"] = [_Resp(429), _Resp(200, {"ok": 1})]

    assert BzzoiroClient("k")._get("/x") == {"ok": 1}


def test_get_nie_ponawia_przy_bledzie_klienta(siec):
    """404 to nie chwilowa awaria — ponawianie niczego nie zmieni."""
    siec["odpowiedzi"] = [_Resp(404)]

    assert BzzoiroClient("k")._get("/x") is None
    assert len(siec["wywolania"]) == 1


# ── predykcje_tygodnia ──────────────────────────────────────────────────────

def _pred(**nadpisz) -> dict:
    ev = {"id": 7, "home_team": "Legia", "away_team": "Lech",
          "league": {"name": "Ekstraklasa"}, "event_date": "2026-08-02T20:30:00Z",
          "status": "notstarted", "odds_home": 2.1, "odds_draw": 3.4,
          "odds_away": 3.6, "odds_over_25": 1.9, "odds_under_25": 1.95,
          "odds_btts_yes": 1.8}
    ev.update(nadpisz.pop("event", {}))
    p = {"event": ev, "prob_home_win": 55, "prob_draw": 25, "prob_away_win": 20,
         "most_likely_score": "2-1"}
    p.update(nadpisz)
    return p


def test_predykcje_mapuja_pola_meczu(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": [_pred()]})]

    w = BzzoiroClient("k").predykcje_tygodnia()[0]

    assert (w["id"], w["gosp"], w["gosc"]) == (7, "Legia", "Lech")
    assert w["liga"] == "Ekstraklasa"
    assert (w["data"], w["godzina"]) == ("2026-08-02", "20:30")


def test_liga_jako_tekst_tez_obslugiwana(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": [_pred(event={"league": "Serie A"})]})]

    assert BzzoiroClient("k").predykcje_tygodnia()[0]["liga"] == "Serie A"


def test_najbardziej_prawdopodobny_wynik_rozbity_na_gole(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": [_pred(most_likely_score="0-3")]})]

    mls = BzzoiroClient("k").predykcje_tygodnia()[0]["pred_ml"]["most_likely_score"]

    assert mls == {"home": 0, "away": 3}


@pytest.mark.parametrize("zepsuty", ["bez-myslnika", "a-b"])
def test_zepsuty_wynik_ma_bezpieczna_wartosc(siec, zepsuty):
    """Śmieć w tym polu nie może wywrócić całego pobierania tygodnia."""
    siec["odpowiedzi"] = [_Resp(200, {"results": [_pred(most_likely_score=zepsuty)]})]

    mls = BzzoiroClient("k").predykcje_tygodnia()[0]["pred_ml"]["most_likely_score"]

    assert mls == {"home": 1, "away": 0}


@pytest.mark.parametrize("puste", [None, ""])
def test_brak_wyniku_daje_remis_a_nie_wygrana(siec, puste):
    """Puste pole idzie przez `or "1-1"`, więc daje REMIS — inna ścieżka niż
    śmieć nie do sparsowania. Domyślny wynik nie może faworyzować gospodarza."""
    siec["odpowiedzi"] = [_Resp(200, {"results": [_pred(most_likely_score=puste)]})]

    mls = BzzoiroClient("k").predykcje_tygodnia()[0]["pred_ml"]["most_likely_score"]

    assert mls == {"home": 1, "away": 1}


def test_brak_prawdopodobienstw_to_brak_pred_ml(siec):
    """Mecz bez ML ma mieć `pred_ml=None`, nie słownik zer udający predykcję."""
    p = _pred()
    del p["prob_home_win"]
    siec["odpowiedzi"] = [_Resp(200, {"results": [p]})]

    assert BzzoiroClient("k").predykcje_tygodnia()[0]["pred_ml"] is None


def test_kursy_zmapowane(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": [_pred()]})]

    odds = BzzoiroClient("k").predykcje_tygodnia()[0]["odds"]

    assert odds["home"] == 2.1
    assert odds["over_2_5"] == 1.9
    assert odds["btts"] == 1.8


def test_brak_kursow_to_none(siec):
    ev = {"odds_home": None}
    siec["odpowiedzi"] = [_Resp(200, {"results": [_pred(event=ev)]})]

    assert BzzoiroClient("k").predykcje_tygodnia()[0]["odds"] is None


def test_pusta_odpowiedz_to_pusta_lista(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": []})]

    assert BzzoiroClient("k").predykcje_tygodnia() == []


def test_awaria_api_to_pusta_lista(siec):
    siec["odpowiedzi"] = [_Resp(404)]

    assert BzzoiroClient("k").predykcje_tygodnia() == []


def test_filtr_ligi_trafia_do_zapytania(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": []})]

    BzzoiroClient("k").predykcje_tygodnia(liga_kod="PL")

    assert siec["wywolania"][0][1]["league"] == 1


def test_liga_bez_odpowiednika_nie_filtruje(siec):
    """Ekstraklasy nie ma w Bzzoiro — filtr po `None` zwróciłby zero meczów."""
    siec["odpowiedzi"] = [_Resp(200, {"results": []})]

    BzzoiroClient("k").predykcje_tygodnia(liga_kod="EKS")

    assert "league" not in siec["wywolania"][0][1]


def test_nieznany_kod_ligi_nie_filtruje(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": []})]

    BzzoiroClient("k").predykcje_tygodnia(liga_kod="XYZ")

    assert "league" not in siec["wywolania"][0][1]


def test_zakres_dat_zawsze_podany(siec):
    siec["odpowiedzi"] = [_Resp(200, {"results": []})]

    BzzoiroClient("k").predykcje_tygodnia()

    params = siec["wywolania"][0][1]
    assert params["date_from"] <= params["date_to"]
