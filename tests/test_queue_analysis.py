"""test_queue_analysis.py — analiza całej kolejki meczów.

PO CO: `analiza_kolejki` spina wszystkie systemy analityczne (ważność meczu,
zmęczenie, H2H, twierdza, klasyfikator) i przepuszcza przez nie każdy nadchodzący
mecz. Moduł miał 0% pokrycia, a jest wołany z `cli.py`.

Dwie rzeczy warte pilnowania:

  * PAUZY MIĘDZY ZAPYTANIAMI. Plan darmowy to 10 zapytań na minutę, a każdy mecz
    zjada dwa wywołania H2H. Bez `sleep` analiza kolejki dostaje 429 w połowie
    listy — i zwraca komplet o połowę krótszy, nie zgłaszając niczego.
  * MECZ BEZ PREDYKCJI NIE WCHODZI DO WYNIKU. `predict_match` zwraca None, gdy
    brakuje historii; taki mecz trafia do tabeli jako „brak danych", ale nie może
    trafić na listę zwracaną dalej — inaczej pusta predykcja poleciałaby do
    scoringu jako pełnoprawny kandydat.

Mecze TBD (nazwa „-") są pomijane przed jakimkolwiek zapytaniem — to oszczędza
limit na czymś, czego i tak nie da się policzyć.
"""
from __future__ import annotations

import pandas as pd
import pytest

import footstats.core.queue_analysis as qa


class _System:
    """Atrapa systemu analitycznego — oddaje stały wynik, notuje wywołania."""

    def __init__(self, wynik: dict):
        self._wynik = wynik
        self.wywolania: list[tuple] = []

    def analiza(self, *args):
        self.wywolania.append(args)
        return dict(self._wynik)


class _Klasyfikator:
    def __init__(self, etykieta="[PUCHAR 1/2]"):
        self._et = etykieta
        self.wywolania = 0

    def klasyfikuj(self, g, a, stage, data, flg, fla):
        self.wywolania += 1
        return {"typ": "PUCHAR", "rewanz": False, "single": False,
                "agg_g": None, "agg_a": None, "etykieta": self._et,
                "etykieta_pdf": self._et, "opis": ""}


def _mecze(*pary: tuple[str, str]) -> pd.DataFrame:
    return pd.DataFrame([
        {"data": f"2026-08-0{i+1}", "data_full": f"2026-08-0{i+1} 20:00",
         "gospodarz": g, "goscie": a, "stage": "REGULAR_SEASON",
         "first_leg_g": None, "first_leg_a": None}
        for i, (g, a) in enumerate(pary)
    ])


def _predykcja(**nadpisz) -> dict:
    p = {"p_wygrana": 55.0, "p_remis": 25.0, "p_przegrana": 20.0,
         "btts": 52.0, "over25": 60.0, "wynik_g": 2, "wynik_a": 1, "pewnosc": 70}
    p.update(nadpisz)
    return p


@pytest.fixture
def srodowisko(monkeypatch):
    """Podstawia systemy, predykcję i sleep; zwraca uchwyt do sterowania."""
    stan = {"predykcja": _predykcja(), "spanie": [], "predict_wywolania": []}

    def fake_predict(g, a, df, *args):
        stan["predict_wywolania"].append((g, a))
        p = stan["predykcja"]
        return dict(p) if p else None

    monkeypatch.setattr(qa, "predict_match", fake_predict)
    monkeypatch.setattr(qa.time, "sleep", lambda s: stan["spanie"].append(s))
    monkeypatch.setattr(qa.console, "print", lambda *a, **k: None)

    stan["imp"] = _System({"label_plain": "WAZNY", "ikony": ""})
    stan["heur"] = _System({"ikony": "😫"})
    stan["h2h"] = _System({"ikona": "⚔️"})
    stan["fort"] = _System({"ikona": "🏰"})
    return stan


def _uruchom(stan, df, klasyfikator=None):
    return qa.analiza_kolejki(
        df, pd.DataFrame(), stan["imp"], stan["heur"],
        stan["h2h"], stan["fort"], klasyfikator)


# ── brak wejścia ────────────────────────────────────────────────────────────

def test_brak_meczow_to_pusta_lista(srodowisko):
    assert _uruchom(srodowisko, pd.DataFrame()) == []


def test_none_zamiast_ramki_nie_wywala(srodowisko):
    assert _uruchom(srodowisko, None) == []


def test_brak_meczow_nie_pyta_systemow(srodowisko):
    _uruchom(srodowisko, pd.DataFrame())

    assert srodowisko["h2h"].wywolania == []


# ── analiza meczów ──────────────────────────────────────────────────────────

def test_mecz_z_predykcja_trafia_do_wyniku(srodowisko):
    wyniki = _uruchom(srodowisko, _mecze(("Legia", "Lech")))

    assert len(wyniki) == 1
    assert wyniki[0]["predykcja"]["p_wygrana"] == 55.0


def test_kazdy_mecz_analizowany(srodowisko):
    wyniki = _uruchom(srodowisko, _mecze(("Legia", "Lech"), ("Wisla", "Rakow")))

    assert len(wyniki) == 2
    assert srodowisko["predict_wywolania"] == [("Legia", "Lech"), ("Wisla", "Rakow")]


def test_brak_predykcji_nie_wchodzi_do_wyniku(srodowisko):
    """Pusta predykcja poleciałaby do scoringu jako pełnoprawny kandydat."""
    srodowisko["predykcja"] = None

    assert _uruchom(srodowisko, _mecze(("Legia", "Lech"))) == []


def test_wynik_niesie_oryginalny_mecz(srodowisko):
    """Dalsze kroki potrzebują daty i nazw, nie tylko liczb z modelu."""
    wyniki = _uruchom(srodowisko, _mecze(("Legia", "Lech")))

    assert wyniki[0]["mecz"]["gospodarz"] == "Legia"
    assert wyniki[0]["mecz"]["goscie"] == "Lech"


# ── mecze TBD ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("para", [("-", "Lech"), ("Legia", "-"), ("-", "-")])
def test_mecz_tbd_pomijany(srodowisko, para):
    assert _uruchom(srodowisko, _mecze(para)) == []


def test_mecz_tbd_nie_zjada_limitu(srodowisko):
    """Pominięcie PRZED zapytaniami oszczędza limit na czymś, czego i tak
    nie da się policzyć."""
    _uruchom(srodowisko, _mecze(("-", "-")))

    assert srodowisko["h2h"].wywolania == []
    assert srodowisko["predict_wywolania"] == []


def test_tbd_nie_blokuje_pozostalych(srodowisko):
    wyniki = _uruchom(srodowisko, _mecze(("-", "Lech"), ("Legia", "Lech")))

    assert len(wyniki) == 1


# ── ochrona limitu zapytań ─────────────────────────────────────────────────

def test_pauza_miedzy_zapytaniami_h2h(srodowisko):
    """Każdy mecz to DWA wywołania H2H — bez pauzy plan darmowy (10/min) pada."""
    _uruchom(srodowisko, _mecze(("Legia", "Lech")))

    assert len(srodowisko["spanie"]) >= 1


def test_brak_pauzy_po_ostatnim_meczu(srodowisko):
    """Czekanie po ostatnim meczu to czysta strata czasu."""
    jeden = len(_uruchom(srodowisko, _mecze(("A", "B"))) or []) or 0
    spanie_1 = list(srodowisko["spanie"])
    srodowisko["spanie"].clear()

    _uruchom(srodowisko, _mecze(("A", "B"), ("C", "D")))

    assert len(srodowisko["spanie"]) == len(spanie_1) * 2 + 1
    assert jeden == 1


def test_h2h_liczony_w_obie_strony(srodowisko):
    """Zemsta i patent to różne rzeczy zależnie od tego, kto jest gospodarzem."""
    _uruchom(srodowisko, _mecze(("Legia", "Lech")))

    pary = [(w[0], w[1]) for w in srodowisko["h2h"].wywolania]
    assert ("Legia", "Lech") in pary
    assert ("Lech", "Legia") in pary


def test_waznosc_liczona_dla_obu_druzyn(srodowisko):
    _uruchom(srodowisko, _mecze(("Legia", "Lech")))

    analizowane = {w[0] for w in srodowisko["imp"].wywolania}
    assert analizowane == {"Legia", "Lech"}


def test_twierdza_tylko_dla_gospodarza(srodowisko):
    """Przewaga własnego boiska dotyczy z definicji tylko gospodarza."""
    _uruchom(srodowisko, _mecze(("Legia", "Lech")))

    assert [w[0] for w in srodowisko["fort"].wywolania] == ["Legia"]


# ── klasyfikator meczu ─────────────────────────────────────────────────────

def test_klasyfikator_uzyty_gdy_podany(srodowisko):
    klas = _Klasyfikator()

    wyniki = _uruchom(srodowisko, _mecze(("Legia", "Lech")), klasyfikator=klas)

    assert klas.wywolania == 1
    assert wyniki[0]["klasyfikacja"]["typ"] == "PUCHAR"


def test_brak_klasyfikatora_daje_domyslna_lige(srodowisko):
    """Bez klasyfikatora mecz ma być traktowany jako ligowy, nie pucharowy."""
    wyniki = _uruchom(srodowisko, _mecze(("Legia", "Lech")))

    assert wyniki[0]["klasyfikacja"]["typ"] == "LIGA"
    assert wyniki[0]["klasyfikacja"]["rewanz"] is False


def test_klasyfikacja_dolaczona_do_kazdego_wyniku(srodowisko):
    wyniki = _uruchom(srodowisko, _mecze(("A", "B"), ("C", "D")),
                      klasyfikator=_Klasyfikator())

    assert all("klasyfikacja" in w for w in wyniki)


# ── warianty predykcji (kolorowanie tabeli nie może wywalić) ───────────────

@pytest.mark.parametrize("pewnosc", [95, 70, 30, 0])
def test_rozne_poziomy_pewnosci_nie_wywalaja(srodowisko, pewnosc):
    srodowisko["predykcja"] = _predykcja(pewnosc=pewnosc)

    assert len(_uruchom(srodowisko, _mecze(("Legia", "Lech")))) == 1


@pytest.mark.parametrize("pw,pr,pp", [(60, 20, 20), (20, 60, 20), (20, 20, 60)])
def test_kazdy_faworyt_obslugiwany(srodowisko, pw, pr, pp):
    srodowisko["predykcja"] = _predykcja(p_wygrana=pw, p_remis=pr, p_przegrana=pp)

    assert len(_uruchom(srodowisko, _mecze(("Legia", "Lech")))) == 1


@pytest.mark.parametrize("bt,o25", [(80, 80), (20, 20), (50, 50)])
def test_progi_btts_i_over_nie_wywalaja(srodowisko, bt, o25):
    srodowisko["predykcja"] = _predykcja(btts=bt, over25=o25)

    assert len(_uruchom(srodowisko, _mecze(("Legia", "Lech")))) == 1


def test_brak_pola_pewnosc_ma_wartosc_domyslna(srodowisko):
    p = _predykcja()
    del p["pewnosc"]
    srodowisko["predykcja"] = p

    assert len(_uruchom(srodowisko, _mecze(("Legia", "Lech")))) == 1
