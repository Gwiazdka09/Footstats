"""test_weekly_picks_skan.py — trzywarstwowy skan `pewniaczki_tygodnia`.

PO CO: to najwiekszy nieprzetestowany kawalek modulu (linie 151-353). Trzy
warstwy o roznym koszcie i roznym priorytecie:

    1. Bzzoiro ML   — wszystkie ligi, 1 zapytanie, najtansze
    2. Poisson      — biezaca liga, 0 zapytan, NADPISUJE ML (wieksza wiarygodnosc)
    3. Inne ligi FDB — 1 zapytanie NA LIGE, ML only, NIE nadpisuje

Trzy rzeczy tu boli najbardziej, gdy sie zepsuja po cichu:
  * gdyby warstwa 3 nadpisywala warstwe 2, stracilibysmy pelna analize Poissona
    na rzecz samego ML — i nikt by nie zauwazyl, bo typ nadal by byl,
  * gdyby sortowanie przestalo stawiac Poisson przed ML, user dostawalby
    na gorze raportu slabsze predykcje,
  * okno czasowe: mecz sprzed tygodnia albo za miesiac nie moze wejsc do kuponu.

`time.sleep` (rate limit FDB 10 req/min) jest podstawiony — inaczej test
czekalby realne sekundy na kazda lige.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

import footstats.core.weekly_picks as wp


def _data(offset_dni: int = 1) -> str:
    return (datetime.now().date() + timedelta(days=offset_dni)).strftime("%Y-%m-%d")


# ── atrapy systemow analitycznych ───────────────────────────────────────────

class _System:
    """Uniwersalna atrapa: kazda metoda zwraca neutralny slownik."""

    def __init__(self, **stale):
        self._stale = stale
        self.wywolania: list = []

    def analiza(self, *a, **k):
        self.wywolania.append(a)
        return dict(self._stale)

    def klasyfikuj(self, *a, **k):
        return {"typ": "LIGA", "etykieta_pdf": "[LIGA]"}


class _FDB:
    """Atrapa klienta football-data.org."""

    def __init__(self, ligi=None, nadchodzace=None, blad=False):
        self._ligi = ligi or []
        self._nad = nadchodzace
        self._blad = blad
        self.pobrane: list[str] = []

    def pobierz_ligi_free(self):
        return self._ligi

    def nadchodzace(self, kod, n):
        self.pobrane.append(kod)
        if self._blad:
            raise OSError("FDB padlo")
        return self._nad


class _Bzzoiro:
    def __init__(self, zdarzenia=None, valid=True, blad=False):
        self._zdarzenia = zdarzenia or []
        self._valid = valid
        self._blad = blad
        self.wywolania = 0

    def predykcje_tygodnia(self):
        self.wywolania += 1
        if self._blad:
            raise RuntimeError("Bzzoiro 503")
        return self._zdarzenia


def _ev(gosp="Legia", gosc="Lech", offset=1, liga="Ekstraklasa", **kw) -> dict:
    return {"gosp": gosp, "gosc": gosc, "data": _data(offset), "godzina": "18:00",
            "liga": liga, "pred_ml": {"x": 1}, "odds": {"home": 1.9}, **kw}


def _df_nad(*mecze) -> pd.DataFrame:
    """(gospodarz, goscie, offset_dni) -> DataFrame nadchodzacych."""
    return pd.DataFrame([
        {"gospodarz": g, "goscie": a, "data": _data(off),
         "data_full": _data(off) + "T18:00:00", "godzina": "18:00",
         "stage": "REGULAR_SEASON", "first_leg_g": None, "first_leg_a": None}
        for g, a, off in mecze
    ])


@pytest.fixture
def skan(monkeypatch):
    """Podstawia predykcje, cross-walidacje i sleep. Zwraca sterowanie."""
    stan = {
        "poisson": {"p_wygrana": 80.0, "p_remis": 12.0, "p_przegrana": 8.0,
                    "btts": 45.0, "over25": 50.0, "under25": 50.0,
                    "lambda_g": 2.1, "lambda_a": 0.8},
        "ml": (78.0, 12.0, 10.0, 45.0, 50.0),
        "wywolania_poisson": [],
    }

    def _predict(g, a, *args, **kw):
        stan["wywolania_poisson"].append((g, a))
        return dict(stan["poisson"]) if stan["poisson"] else None

    monkeypatch.setattr(wp, "predict_match", _predict)
    monkeypatch.setattr(wp, "_bzz_parse_prob", lambda p: stan["ml"])
    monkeypatch.setattr(wp.BzzoiroClient, "porownaj_z_poisson",
                        staticmethod(lambda *a, **k: {"ml_1": 70.0, "alert": False}))
    monkeypatch.setattr("time.sleep", lambda s: None)
    return stan


def _uruchom(skan_fixture=None, *, df_nad=None, bzzoiro=None, api_fdb=None,
             skanuj_inne=True, prog=75.0) -> list:
    systemy = {
        "importance_idx": _System(bonus_atak=1.0, status="NORMAL", komentarz=""),
        "heurystyka_eng": _System(mnoznik_atak=1.0, mnoznik_obr=1.0, ikony=""),
        "h2h_sys": _System(mnoznik_atak=1.0, mnoznik_szans=1.0, ikona="", n_h2h=0),
        "fortress_sys": _System(bonus_obrona=1.0, fortress=False, ikona=""),
        "dw_sys": _System(podroznik=False, bonus_wyjazd=1.0, ikona=""),
        "klasyfikator": _System(),
    }
    return wp.pewniaczki_tygodnia(
        api_fdb=api_fdb,
        df_wyk_biezaca=pd.DataFrame([{"gospodarz": "Legia", "goscie": "Lech",
                                      "gole_g": 2, "gole_a": 1}]),
        df_nad_biezaca=df_nad,
        nazwa_biezacej="Ekstraklasa",
        bzzoiro=bzzoiro,
        skanuj_inne_ligi=skanuj_inne,
        prog=prog,
        **systemy,
    )


# ── warstwa 1: Bzzoiro ML ───────────────────────────────────────────────────

def test_bez_bzzoiro_i_bez_ligi_zwraca_pusto(skan):
    assert _uruchom(skan, skanuj_inne=False) == []


def test_bzzoiro_nieaktywny_nie_jest_odpytywany(skan):
    bzz = _Bzzoiro([_ev()], valid=False)
    _uruchom(skan, bzzoiro=bzz, skanuj_inne=False)
    assert bzz.wywolania == 0, "odpytano nieaktywnego klienta"


def test_bzzoiro_daje_typy_ml(skan):
    wynik = _uruchom(skan, bzzoiro=_Bzzoiro([_ev()]), skanuj_inne=False)
    assert len(wynik) == 1
    assert wynik[0]["metoda"] == "ML"
    assert wynik[0]["gospodarz"] == "Legia"


def test_jedno_zapytanie_na_wszystkie_ligi(skan):
    """Sedno oszczedzania: 400+ meczow z 22 lig w JEDNYM zapytaniu."""
    bzz = _Bzzoiro([_ev(gosp=f"D{i}", gosc="X") for i in range(20)])
    _uruchom(skan, bzzoiro=bzz, skanuj_inne=False)
    assert bzz.wywolania == 1


def test_awaria_bzzoiro_nie_przerywa_skanu(skan, capsys):
    wynik = _uruchom(skan, bzzoiro=_Bzzoiro(blad=True),
                     df_nad=_df_nad(("Legia", "Lech", 1)), skanuj_inne=False)
    assert "Bzzoiro blad" in capsys.readouterr().out
    assert len(wynik) == 1, "Poisson nie policzyl sie po awarii Bzzoiro"


@pytest.mark.parametrize("brak", ["gosp", "gosc", "data"])
def test_niepelne_zdarzenie_pomijane(skan, brak):
    ev = _ev()
    ev[brak] = ""
    assert _uruchom(skan, bzzoiro=_Bzzoiro([ev]), skanuj_inne=False) == []


def test_zla_data_pomijana(skan):
    ev = _ev()
    ev["data"] = "nie-data"
    assert _uruchom(skan, bzzoiro=_Bzzoiro([ev]), skanuj_inne=False) == []


# ── okno czasowe ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("offset", [-1, -30])
def test_mecz_z_przeszlosci_odrzucany(skan, offset):
    assert _uruchom(skan, bzzoiro=_Bzzoiro([_ev(offset=offset)]),
                    skanuj_inne=False) == []


def test_mecz_poza_horyzontem_odrzucany(skan):
    daleko = wp.PEWNIACZEK_DNI + 5
    assert _uruchom(skan, bzzoiro=_Bzzoiro([_ev(offset=daleko)]),
                    skanuj_inne=False) == []


def test_mecz_dzisiejszy_przechodzi(skan):
    assert len(_uruchom(skan, bzzoiro=_Bzzoiro([_ev(offset=0)]),
                        skanuj_inne=False)) == 1


def test_mecz_na_granicy_horyzontu_przechodzi(skan):
    assert len(_uruchom(skan, bzzoiro=_Bzzoiro([_ev(offset=wp.PEWNIACZEK_DNI)]),
                        skanuj_inne=False)) == 1


# ── warstwa 2: Poisson biezacej ligi ────────────────────────────────────────

def test_poisson_liczy_mecze_biezacej_ligi(skan):
    wynik = _uruchom(skan, df_nad=_df_nad(("Legia", "Lech", 1)), skanuj_inne=False)
    assert len(wynik) == 1
    assert wynik[0]["metoda"] == "POISSON"
    assert wynik[0]["liga"] == "Ekstraklasa"


def test_poisson_nadpisuje_ml_dla_tego_samego_meczu(skan):
    """SEDNO priorytetu: pelna analiza wygrywa z samym ML."""
    wynik = _uruchom(skan, bzzoiro=_Bzzoiro([_ev("Legia", "Lech", 1)]),
                     df_nad=_df_nad(("Legia", "Lech", 1)), skanuj_inne=False)
    assert len(wynik) == 1, "mecz zdublowany zamiast nadpisany"
    assert wynik[0]["metoda"] == "POISSON"


def test_cross_walidacja_gdy_jest_ml(skan):
    wynik = _uruchom(skan, bzzoiro=_Bzzoiro([_ev("Legia", "Lech", 1)]),
                     df_nad=_df_nad(("Legia", "Lech", 1)), skanuj_inne=False)
    assert wynik[0]["bzz_info"] is not None
    assert wynik[0]["bzz_info"]["cross"]["ml_1"] == 70.0


def test_brak_ml_to_brak_cross_walidacji(skan):
    wynik = _uruchom(skan, df_nad=_df_nad(("Legia", "Lech", 1)), skanuj_inne=False)
    assert wynik[0]["bzz_info"] is None


def test_za_malo_historii_pomija_mecz(skan):
    skan["poisson"] = None
    assert _uruchom(skan, df_nad=_df_nad(("Legia", "Lech", 1)), skanuj_inne=False) == []


def test_typy_ponizej_progu_pomijane(skan):
    assert _uruchom(skan, df_nad=_df_nad(("Legia", "Lech", 1)),
                    skanuj_inne=False, prog=99.0) == []


def test_puste_nazwy_druzyn_pomijane(skan):
    df = _df_nad(("Legia", "Lech", 1))
    df.loc[0, "gospodarz"] = None
    assert _uruchom(skan, df_nad=df, skanuj_inne=False) == []


def test_cache_dom_wyjazd_nie_liczy_dwa_razy(skan):
    """dw_sys.analiza dla tego samego goscia ma sie policzyc RAZ."""
    systemy_dw = _System(podroznik=False, bonus_wyjazd=1.0, ikona="")
    wp.pewniaczki_tygodnia(
        api_fdb=None,
        df_wyk_biezaca=pd.DataFrame([{"gospodarz": "A", "goscie": "B",
                                      "gole_g": 1, "gole_a": 0}]),
        df_nad_biezaca=_df_nad(("Legia", "Lech", 1), ("Wisła", "Lech", 2)),
        nazwa_biezacej="Ekstraklasa",
        importance_idx=_System(bonus_atak=1.0, status="NORMAL", komentarz=""),
        heurystyka_eng=_System(mnoznik_atak=1.0, mnoznik_obr=1.0, ikony=""),
        h2h_sys=_System(mnoznik_atak=1.0, mnoznik_szans=1.0, ikona="", n_h2h=0),
        fortress_sys=_System(bonus_obrona=1.0, fortress=False, ikona=""),
        dw_sys=systemy_dw,
        klasyfikator=_System(),
        skanuj_inne_ligi=False,
    )
    assert len(systemy_dw.wywolania) == 1, "Lech policzony dwa razy mimo cache"


# ── warstwa 3: inne ligi FDB ────────────────────────────────────────────────

def test_inne_ligi_pomijane_gdy_wylaczone(skan):
    fdb = _FDB(ligi=[{"nazwa": "La Liga", "kod": "PD"}])
    _uruchom(skan, api_fdb=fdb, skanuj_inne=False)
    assert fdb.pobrane == []


def test_inna_liga_wymaga_ml_z_bzzoiro(skan):
    """Bez historii i bez ML nie ma czym liczyc — mecz wypada."""
    fdb = _FDB(ligi=[{"nazwa": "La Liga", "kod": "PD"}],
               nadchodzace=_df_nad(("Real", "Getafe", 1)))
    assert _uruchom(skan, api_fdb=fdb) == []


def test_inna_liga_z_ml_daje_typ(skan):
    fdb = _FDB(ligi=[{"nazwa": "La Liga", "kod": "PD"}],
               nadchodzace=_df_nad(("Real", "Getafe", 1)))
    wynik = _uruchom(skan, api_fdb=fdb, bzzoiro=_Bzzoiro([_ev("Real", "Getafe", 1)]))

    assert len(wynik) == 1
    assert wynik[0]["metoda"] == "ML"


def test_warstwa_3_nie_nadpisuje_poissona(skan):
    """KRYTYCZNE: tansza warstwa nie moze skasowac pelnej analizy."""
    fdb = _FDB(ligi=[{"nazwa": "La Liga", "kod": "PD"}],
               nadchodzace=_df_nad(("Legia", "Lech", 1)))
    wynik = _uruchom(skan, api_fdb=fdb,
                     bzzoiro=_Bzzoiro([_ev("Legia", "Lech", 1)]),
                     df_nad=_df_nad(("Legia", "Lech", 1)))

    assert len(wynik) == 1
    assert wynik[0]["metoda"] == "POISSON", "warstwa 3 nadpisala Poissona"
    assert wynik[0]["liga"] == "Ekstraklasa"


def test_biezaca_liga_wykluczona_z_listy_innych(skan):
    fdb = _FDB(ligi=[{"nazwa": "Ekstraklasa", "kod": "PL"},
                     {"nazwa": "La Liga", "kod": "PD"}])
    _uruchom(skan, api_fdb=fdb)
    assert "PL" not in fdb.pobrane, "biezaca liga pobrana drugi raz"


def test_awaria_pobierania_ligi_nie_przerywa_petli(skan):
    fdb = _FDB(ligi=[{"nazwa": "La Liga", "kod": "PD"}], blad=True)
    assert _uruchom(skan, api_fdb=fdb) == []      # nie rzuca


# ── sortowanie ──────────────────────────────────────────────────────────────

def test_poisson_przed_ml(skan):
    """Poisson ma wieksza wiarygodnosc — musi byc na gorze raportu."""
    fdb = _FDB(ligi=[{"nazwa": "La Liga", "kod": "PD"}],
               nadchodzace=_df_nad(("Real", "Getafe", 1)))
    wynik = _uruchom(skan, api_fdb=fdb,
                     bzzoiro=_Bzzoiro([_ev("Real", "Getafe", 1)]),
                     df_nad=_df_nad(("Legia", "Lech", 1)))

    assert [w["metoda"] for w in wynik] == ["POISSON", "ML"]


def test_wyzsza_szansa_wyzej_w_ramach_metody(skan):
    bzz = _Bzzoiro([_ev("A", "B", 1), _ev("C", "D", 1)])
    wynik = _uruchom(skan, bzzoiro=bzz, skanuj_inne=False)

    szanse = [max(v for _, v in w["typy"]) for w in wynik]
    assert szanse == sorted(szanse, reverse=True)
