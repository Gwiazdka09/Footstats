"""Świeżość danych historycznych — dataset NIE może zamarzać na starym sezonie.

DLACZEGO TO KRYTYCZNE:
`full_dataset.parquet` karmi `quick_picks` (Poisson-DC), `lambda_optimizer`
i `walkforward` — czyli model, który realnie typuje na produkcji. Gdy plik
kończy się na poprzednim sezonie, model przewiduje mecze drużyn, których
aktualnej formy, transferów ani beniaminków nigdy nie widział.

Tak było 2026-08-07: dataset urywał się 2026-05-24, bo
  * `FDCO_SEASONS` była listą-literałem bez kodu sezonu 2026/27, oraz
  * cache per sezon nie miał ŻADNEGO TTL, więc plik trwającego sezonu
    pobrany raz w kwietniu zostawał na dysku na zawsze.
Oba błędy są ciche — nic nie pada, dane po prostu się nie ruszają.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from footstats.data import historical_loader as hl


# ─────────────────────── kod sezonu ────────────────────────────────────────

@pytest.mark.parametrize(
    ("dzien", "oczekiwany"),
    [
        (date(2026, 8, 7),  "2627"),   # środek lata → nowy sezon już się liczy
        (date(2026, 7, 1),  "2627"),   # granica: lipiec to już nowy rocznik
        (date(2026, 6, 30), "2526"),   # granica: czerwiec to jeszcze stary
        (date(2026, 5, 24), "2526"),   # ostatnia kolejka starego sezonu
        (date(2027, 1, 15), "2627"),   # runda wiosenna nadal w tym samym sezonie
        (date(2009, 9, 1),  "0910"),   # zero-padding jednocyfrowych lat
        (date(2000, 3, 1),  "9900"),   # przełom stuleci nie łamie modulo
    ],
)
def test_kod_sezonu_dla_daty(dzien: date, oczekiwany: str) -> None:
    assert hl.kod_sezonu(dzien) == oczekiwany


def test_kod_sezonu_bez_argumentu_uzywa_dzisiaj() -> None:
    assert hl.kod_sezonu() == hl.kod_sezonu(date.today())


def test_ostatnie_sezony_zaczyna_od_biezacego_i_cofa_sie() -> None:
    sezony = hl.ostatnie_sezony(ile=3, dzien=date(2026, 8, 7))
    assert sezony == ["2627", "2526", "2425"]


def test_okno_trzyma_stala_liczbe_pelnych_sezonow() -> None:
    """Start nowego sezonu nie może wypychać sezonu rozegranego z okna.

    Regresja: przy oknie 10 sezonów łącznie refresh 07.08.2026 dołożył 34 mecze
    nowego sezonu i wyrzucił 2566 meczów sezonu 2016/17 — czysta strata.
    """
    pelne_w_sezonie = hl.ostatnie_sezony(dzien=date(2026, 8, 7))[1:]
    pelne_w_przerwie = hl.ostatnie_sezony(dzien=date(2026, 6, 30))
    assert pelne_w_sezonie == pelne_w_przerwie[: len(pelne_w_sezonie)]
    assert len(pelne_w_sezonie) == hl.LICZBA_SEZONOW - 1


def test_ostatnie_sezony_bez_duplikatow() -> None:
    sezony = hl.ostatnie_sezony(ile=10, dzien=date(2026, 8, 7))
    assert len(set(sezony)) == len(sezony)


def test_lista_sezonow_zawiera_biezacy_sezon() -> None:
    """Regresja: literał `FDCO_SEASONS` kończył się na "2526" w sierpniu 2026.

    Test liczy oczekiwany kod z dzisiejszej daty, więc nie zgnije za rok —
    sam zacznie wymagać kolejnego sezonu.
    """
    assert hl.kod_sezonu() in hl.ostatnie_sezony()


# ─────────────────────── TTL cache'u sezonowego ────────────────────────────

def _pusty_wynik() -> pd.DataFrame:
    return pd.DataFrame({
        "date": [pd.Timestamp("2026-08-02")],
        "league": ["SCO-Premiership"],
        "home": ["Aberdeen"],
        "away": ["Hearts"],
        "hg": [2.0],
        "ag": [1.0],
    })


def test_biezacy_sezon_odswieza_stary_cache(tmp_path, monkeypatch) -> None:
    """Plik trwającego sezonu starszy niż TTL musi zostać pobrany ponownie."""
    biezacy = hl.kod_sezonu()
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)

    cache_f = tmp_path / f"fdco_SC0_{biezacy}.parquet"
    _pusty_wynik().to_parquet(cache_f, index=False)
    stary = pd.Timestamp.now() - pd.Timedelta(hours=hl.TTL_BIEZACY_SEZON_H + 1)
    import os
    os.utime(cache_f, (stary.timestamp(), stary.timestamp()))

    wolania: list[tuple[str, str]] = []

    def fake_download(lg: str, s: str):
        wolania.append((lg, s))
        return _pusty_wynik()

    monkeypatch.setattr(hl, "_download_fdco_season", fake_download)
    hl.download_fdco_seasons(leagues=["SC0"], seasons=[biezacy])

    assert wolania == [("SC0", biezacy)], "przeterminowany cache biezacego sezonu nie odswiezony"


def test_biezacy_sezon_swiezy_cache_nie_pobiera(tmp_path, monkeypatch) -> None:
    """W granicach TTL nie ma po co męczyć football-data.co.uk."""
    biezacy = hl.kod_sezonu()
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    _pusty_wynik().to_parquet(tmp_path / f"fdco_SC0_{biezacy}.parquet", index=False)

    def fake_download(lg: str, s: str):
        raise AssertionError("nie powinno byc pobierania dla swiezego cache")

    monkeypatch.setattr(hl, "_download_fdco_season", fake_download)
    df = hl.download_fdco_seasons(leagues=["SC0"], seasons=[biezacy])
    assert len(df) == 1


def test_cache_zamknietego_sezonu_pobrany_W_TRAKCIE_jest_odswiezany(tmp_path, monkeypatch) -> None:
    """Sezon zamknięty ≠ komplet meczów, gdy plik pobrano w trakcie jego trwania.

    Bug znaleziony 2026-08-08: reguła „niebieżący sezon jest niezmienny"
    zamrażała pliki zapisane w kwietniu, gdy sezon 2025/26 jeszcze się toczył.
    Trzy ligi urwały się na 2026-03-22, tracąc ~2 miesiące, które u źródła są:
    Premier League 63 dni, Bundesliga 55, Eredivisie 56.

    Cache sezonu zamkniętego jest wiarygodny tylko wtedy, gdy powstał PO jego
    zakończeniu — stąd próg na lipcu roku, w którym sezon się kończył.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    cache_f = tmp_path / "fdco_D1_2526.parquet"
    _pusty_wynik().to_parquet(cache_f, index=False)
    # Kwiecień 2026 — sezon 2025/26 był wtedy w trakcie.
    w_trakcie = pd.Timestamp("2026-04-05")
    import os
    os.utime(cache_f, (w_trakcie.timestamp(), w_trakcie.timestamp()))

    wolania: list = []
    monkeypatch.setattr(hl, "_download_fdco_season",
                        lambda lg, s: (wolania.append((lg, s)), _pusty_wynik())[1])
    hl.download_fdco_seasons(leagues=["D1"], seasons=["2526"])
    assert wolania == [("D1", "2526")], "niekompletny cache sezonu nie zostal odswiezony"


def test_cache_pobrany_PO_sezonie_zostaje(tmp_path, monkeypatch) -> None:
    """Plik zapisany po zakończeniu rozgrywek jest już kompletny — nie ruszamy."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    cache_f = tmp_path / "fdco_D1_2526.parquet"
    _pusty_wynik().to_parquet(cache_f, index=False)
    po_sezonie = pd.Timestamp("2026-07-15")
    import os
    os.utime(cache_f, (po_sezonie.timestamp(), po_sezonie.timestamp()))

    monkeypatch.setattr(hl, "_download_fdco_season",
                        lambda lg, s: pytest.fail("kompletny cache pobrany ponownie"))
    assert len(hl.download_fdco_seasons(leagues=["D1"], seasons=["2526"])) == 1


def test_zamkniety_sezon_nie_wygasa(tmp_path, monkeypatch) -> None:
    """Sezon rozegrany do końca już się nie zmieni — cache ma być wieczny.

    Inaczej każde uruchomienie ciągnęłoby 80 plików CSV bez powodu.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    cache_f = tmp_path / "fdco_SC0_1617.parquet"
    _pusty_wynik().to_parquet(cache_f, index=False)
    prehistoria = pd.Timestamp.now() - pd.Timedelta(days=900)
    import os
    os.utime(cache_f, (prehistoria.timestamp(), prehistoria.timestamp()))

    def fake_download(lg: str, s: str):
        raise AssertionError("zamkniety sezon nie moze byc pobierany ponownie")

    monkeypatch.setattr(hl, "_download_fdco_season", fake_download)
    assert len(hl.download_fdco_seasons(leagues=["SC0"], seasons=["1617"])) == 1


def test_brak_pliku_u_zrodla_nie_wywraca_przebiegu(tmp_path, monkeypatch) -> None:
    """Liga, której sezon jeszcze nie ruszył, zwraca 404 → None.

    Realny przypadek 07.08.2026: Premier League nie miała jeszcze pliku 2627,
    a La Liga i Szkocja już tak. Jedna dziura nie może zabrać reszty.
    """
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    biezacy = hl.kod_sezonu()

    def fake_download(lg: str, s: str):
        return None if lg == "E0" else _pusty_wynik()

    monkeypatch.setattr(hl, "_download_fdco_season", fake_download)
    df = hl.download_fdco_seasons(leagues=["E0", "SC0"], seasons=[biezacy])
    assert len(df) == 1
    assert not (tmp_path / f"fdco_E0_{biezacy}.parquet").exists(), "pustka nie moze trafic do cache"


# ─────────────────────── domyślny zakres download_all ──────────────────────
#
# `full_dataset.parquet` na dysku zawiera 8 lig sezonowych + POL + AUT i ANI
# JEDNEGO wiersza z xgabora. Domyślne argumenty `download_all` mówiły co innego
# (`["N1"]`, `["POL"]`, `include_xgabora=True`), więc odświeżenie danych
# wywołaniem bez argumentów — czyli dokładnie tak, jak podpowiada docstring —
# ścięłoby dataset do dwóch lig i dołożyło źródło o innym nazewnictwie lig
# ("E0" zamiast "ENG-Premier League"), przez co ten sam mecz istniałby pod
# dwiema nazwami. Te testy pilnują, żeby refresh odtwarzał to, co jest.

def _przechwyc(monkeypatch) -> dict:
    zapis: dict = {}

    def fake_seasons(leagues=None, seasons=None):
        zapis["leagues"] = leagues
        zapis["seasons"] = seasons
        return pd.DataFrame()

    def fake_new(countries=None):
        zapis["countries"] = countries
        return pd.DataFrame()

    def fake_xgabora():
        zapis["xgabora"] = True
        return pd.DataFrame()

    monkeypatch.setattr(hl, "download_fdco_seasons", fake_seasons)
    monkeypatch.setattr(hl, "download_fdco_new", fake_new)
    monkeypatch.setattr(hl, "download_xgabora", fake_xgabora)
    return zapis


def test_download_all_domyslnie_bierze_wszystkie_ligi_sezonowe(monkeypatch) -> None:
    zapis = _przechwyc(monkeypatch)
    hl.download_all()
    assert set(zapis["leagues"]) == set(hl.FDCO_LEAGUES), "refresh scialby dataset do jednej ligi"


def test_download_all_domyslnie_bierze_oba_kraje_nowego_formatu(monkeypatch) -> None:
    zapis = _przechwyc(monkeypatch)
    hl.download_all()
    assert set(zapis["countries"]) == set(hl.FDCO_NEW_LEAGUES), "AUT wypadlby z datasetu"


def test_download_all_domyslnie_pomija_xgabora(monkeypatch) -> None:
    """xgabora nazywa ligi kodami ("E0"), nasz dataset pełnymi nazwami.

    Wmieszanie go bez mapowania nazw daje ten sam mecz dwa razy, pod dwiema
    ligami — a `quick_picks` filtruje historię właśnie po `league`.
    """
    zapis = _przechwyc(monkeypatch)
    hl.download_all()
    assert "xgabora" not in zapis


def test_download_all_na_zadanie_nadal_dociaga_xgabora(monkeypatch) -> None:
    zapis = _przechwyc(monkeypatch)
    hl.download_all(include_xgabora=True)
    assert zapis.get("xgabora") is True
