"""Testy `af_stats.py` — osobny artefakt statystyk API-Football, scalany PRZY ODCZYCIE.

DLACZEGO osobny plik zamiast dopisywania kolumn do `full_dataset.parquet`:
`.github/workflows/dataset_refresh.yml` odpala `download_all()` co poniedziałek
na czystym runnerze GitHuba i `download_all()` NADPISUJE cały plik jednym
`df.to_parquet(out_f)` — każda kolumna dopisana tam wprost zginęłaby przy
pierwszym odświeżeniu. Za te dane płacimy ~11 000 requestami z dobowego limitu
7500, więc scalanie musi żyć w miejscu, którego refresh nie dotyka: przy
odczycie (`historical_loader.load_cached`), nie przy zapisie.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from footstats.data import af_stats
from footstats.data import historical_loader as hl

# ─────────────────────────── budowa danych testowych ───────────────────────


def _df_mecze(wiersze: list[dict]) -> pd.DataFrame:
    """Minimalny szkielet datasetu (jak `full_dataset.parquet`) do testów."""
    baza = {
        "date": None, "league": "TEST-Liga", "home": None, "away": None,
        "hg": 1.0, "ag": 1.0, "hs": np.nan, "as_": np.nan,
        "hst": np.nan, "ast": np.nan,
    }
    return pd.DataFrame([{**baza, **w} for w in wiersze])


def _af_wiersz(**kw) -> dict:
    """Jeden wiersz `af_stats.parquet` — pełny schemat `KOLUMNY_PLIKU`."""
    baza = {
        "date": None, "league": "TEST-Liga", "home": None, "away": None,
        "hs": np.nan, "as_": np.nan, "hst": np.nan, "ast": np.nan,
        "xg_home": np.nan, "xg_away": np.nan, "af_fixture_id": 0,
        "status": "FT", "pobrano": pd.Timestamp("2026-09-01"),
    }
    return {**baza, **kw}


# ─────────────────────────── stałe modułu ──────────────────────────────────


def test_sciezka_af_stats_w_tym_samym_katalogu_co_dataset() -> None:
    """Rozjazd katalogów byłby cichy: plik leżałby obok, a scalanie widziałoby pusto."""
    assert af_stats.SCIEZKA_AF_STATS.parent == hl.CACHE_DIR


def test_kolumny_promowane_to_dokladnie_cztery_pola_strzalow() -> None:
    assert af_stats.KOLUMNY_PROMOWANE == ("hs", "as_", "hst", "ast")


def test_xg_jest_w_pliku_ale_nie_wsrod_promowanych() -> None:
    """xG zostaje w pliku na przyszłość, ale nie ma w `src/` czytelnika kolumny
    xG z parquetu — kolumna bez czytelnika zostałaby prędzej czy później użyta
    bez pomiaru."""
    assert "xg_home" in af_stats.KOLUMNY_PLIKU
    assert "xg_away" in af_stats.KOLUMNY_PLIKU
    assert "xg_home" not in af_stats.KOLUMNY_PROMOWANE
    assert "xg_away" not in af_stats.KOLUMNY_PROMOWANE


# ─────────────────────────── wczytaj_af_stats ──────────────────────────────


def test_wczytaj_af_stats_brak_pliku_zwraca_puste_ze_schematem(tmp_path, monkeypatch) -> None:
    """Brak pliku to stan NORMALNY (świeży klon, obraz bez backfillu) — nie rzuca."""
    monkeypatch.setattr(af_stats, "SCIEZKA_AF_STATS", tmp_path / "af_stats.parquet")

    wynik = af_stats.wczytaj_af_stats()

    assert wynik.empty
    assert list(wynik.columns) == list(af_stats.KOLUMNY_PLIKU)


def test_wczytaj_af_stats_nieczytelny_plik_loguje_ostrzezenie(tmp_path, monkeypatch, caplog) -> None:
    """Uszkodzony plik jest INNY niż brak pliku — musi być słyszalny, nie połknięty."""
    plik = tmp_path / "af_stats.parquet"
    plik.write_bytes(b"to nie jest parquet")
    monkeypatch.setattr(af_stats, "SCIEZKA_AF_STATS", plik)

    with caplog.at_level(logging.WARNING):
        wynik = af_stats.wczytaj_af_stats()

    assert wynik.empty
    assert list(wynik.columns) == list(af_stats.KOLUMNY_PLIKU)
    assert str(plik) in caplog.text, "uszkodzony plik musi zostac zgloszony logiem"


# ─────────────────────────── zapisz_af_stats ───────────────────────────────


def test_zapisz_af_stats_jest_atomowy_brak_plikow_tmp(tmp_path, monkeypatch) -> None:
    """Backfill zapisuje przyrostowo — ubity proces w trakcie zapisu nie może
    zostawić pół-zapisanego pliku kosztem tysięcy opłaconych requestów."""
    monkeypatch.setattr(af_stats, "SCIEZKA_AF_STATS", tmp_path / "af_stats.parquet")
    df = pd.DataFrame([_af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B")])

    af_stats.zapisz_af_stats(df)

    assert af_stats.SCIEZKA_AF_STATS.exists()
    assert list(tmp_path.glob("*.tmp")) == [], "zapis zostawil plik tymczasowy"


def test_zapisz_a_potem_wczytaj_daje_te_same_dane(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(af_stats, "SCIEZKA_AF_STATS", tmp_path / "af_stats.parquet")
    df = pd.DataFrame([_af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B", hst=5.0)])

    af_stats.zapisz_af_stats(df)
    wynik = af_stats.wczytaj_af_stats()

    assert wynik.loc[0, "hst"] == 5.0


# ─────────────────────────── scal_statystyki ───────────────────────────────


def test_scal_statystyki_liczba_i_kolejnosc_wierszy_bez_zmian() -> None:
    """Model czyta ramkę POZYCYJNIE (`.tail(N)`) — kolejność jest częścią kontraktu."""
    df = _df_mecze([
        {"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"},
        {"date": pd.Timestamp("2026-01-02"), "home": "C", "away": "D"},
        {"date": pd.Timestamp("2026-01-03"), "home": "B", "away": "A"},
    ])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-02"), home="C", away="D", hst=6.0, ast=4.0),
    ])

    wynik = af_stats.scal_statystyki(df, af)

    assert len(wynik) == len(df)
    assert list(wynik["home"]) == list(df["home"])
    assert list(wynik["away"]) == list(df["away"])


def test_scal_statystyki_nie_nadpisuje_wartosci_z_football_data() -> None:
    df = _df_mecze([
        {"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B", "hst": 5.0, "ast": 3.0},
    ])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B", hst=99.0, ast=99.0),
    ])

    wynik = af_stats.scal_statystyki(df, af)

    assert wynik.loc[0, "hst"] == 5.0
    assert wynik.loc[0, "ast"] == 3.0


def test_scal_statystyki_dopelnia_nan_wartosciami_z_af() -> None:
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B",
                   hs=10.0, as_=8.0, hst=6.0, ast=4.0),
    ])

    wynik = af_stats.scal_statystyki(df, af)

    assert wynik.loc[0, "hst"] == 6.0
    assert wynik.loc[0, "ast"] == 4.0
    assert wynik.loc[0, "hs"] == 10.0
    assert wynik.loc[0, "as_"] == 8.0


def test_scal_statystyki_zadnych_kolumn_poza_promowanymi() -> None:
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B",
                   xg_home=1.8, xg_away=1.1, af_fixture_id=555),
    ])

    wynik = af_stats.scal_statystyki(df, af)

    assert set(wynik.columns) == set(df.columns), (
        "xG/af_fixture_id/status/pobrano nie moga wejsc do ramki modelu"
    )


def test_scal_statystyki_wejscie_niemutowane() -> None:
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    kopia = df.copy()
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B", hst=6.0, ast=4.0),
    ])

    af_stats.scal_statystyki(df, af)

    pd.testing.assert_frame_equal(df, kopia)


def test_scal_statystyki_klucz_normalizuje_date_do_doby() -> None:
    """AF podaje czasem datę meczu ze znacznikiem godziny, football-data samą datę."""
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01 20:45:00"), home="A", away="B",
                   hst=7.0, ast=2.0),
    ])

    wynik = af_stats.scal_statystyki(df, af)

    assert wynik.loc[0, "hst"] == 7.0
    assert wynik.loc[0, "ast"] == 2.0


def test_scal_statystyki_duplikat_klucza_w_af_rzuca_value_error() -> None:
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B",
                   hst=6.0, ast=4.0, af_fixture_id=1),
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B",
                   hst=7.0, ast=5.0, af_fixture_id=2),
    ])

    with pytest.raises(ValueError, match="powtorzonym kluczu"):
        af_stats.scal_statystyki(df, af)


def test_duplikat_klucza_zglasza_ktora_pare(  ) -> None:
    """Komunikat musi WSKAZAC winna pare, nie tylko powiedziec ze cos jest nie tak.

    Sam fakt wyjatku lapie juz `merge(validate="m:1")` — `pandas.errors.MergeError`
    dziedziczy po `ValueError`, wiec test na sam typ przechodzil takze wtedy, gdy
    nasze sprawdzenie bylo wylaczone. Wartoscia dodana jest tresc: bez nazw druzyn
    i daty nie da sie znalezc meczu, ktory rozjechal dopasowanie fixture'a.
    """
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "Legia", "away": "Lech"}])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="Legia", away="Lech", hst=6.0),
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="Legia", away="Lech", hst=7.0),
    ])

    with pytest.raises(ValueError) as e:
        af_stats.scal_statystyki(df, af)

    assert "Legia" in str(e.value), f"komunikat nie wskazuje winnej pary: {e.value}"


def test_scal_statystyki_zachowuje_indeks_wejscia() -> None:
    """`merge` gubi indeks. Ramka datasetu bywa WYCINKIEM z wlasnym indeksem.

    `poisson.predict_match` dostaje `df_mecze[maska].tail(N)`, czyli ramke
    z indeksem nieciaglym. Przenumerowanie od zera nie wywoluje bledu — po prostu
    kolejne operacje po indeksie trafiaja w inne wiersze.
    """
    df = _df_mecze([
        {"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"},
        {"date": pd.Timestamp("2026-01-02"), "home": "C", "away": "D"},
    ])
    df.index = pd.Index([17, 42])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-02"), home="C", away="D", hst=6.0, ast=4.0),
    ])

    wynik = af_stats.scal_statystyki(df, af)

    assert list(wynik.index) == [17, 42]
    assert wynik.loc[42, "hst"] == 6.0


def test_scal_statystyki_ignoruje_wiersze_brak_statystyk() -> None:
    """Placeholder po nieudanym backfillu nie może ani zwielokrotnić wierszy
    (duplikat klucza), ani zablokować późniejszego, prawdziwego wpisu dla
    tego samego meczu (np. po ponownym backfillu)."""
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B",
                   status="brak_statystyk"),
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B",
                   hst=6.0, ast=4.0, status="FT"),
    ])

    wynik = af_stats.scal_statystyki(df, af)

    assert wynik.loc[0, "hst"] == 6.0
    assert wynik.loc[0, "ast"] == 4.0


def test_scal_statystyki_pusty_af_zwraca_df_bez_zmian() -> None:
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    af = pd.DataFrame(columns=af_stats.KOLUMNY_PLIKU)

    wynik = af_stats.scal_statystyki(df, af)

    pd.testing.assert_frame_equal(wynik, df)


def test_scal_statystyki_brakujacy_plik_af_zwraca_df_bez_zmian(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(af_stats, "SCIEZKA_AF_STATS", tmp_path / "af_stats.parquet")
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])

    wynik = af_stats.scal_statystyki(df)  # af=None -> wczytaj_af_stats() -> puste

    pd.testing.assert_frame_equal(wynik, df)


def test_scal_statystyki_kolumny_wynikowe_pozostaja_liczbowe() -> None:
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    af = pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B",
                   hs=9.0, as_=7.0, hst=6.0, ast=4.0),
    ])

    wynik = af_stats.scal_statystyki(df, af)

    for kol in af_stats.KOLUMNY_PROMOWANE:
        assert pd.api.types.is_numeric_dtype(wynik[kol]), f"{kol} nie jest liczbowa"


# ─────────────────────────── raport_pokrycia ───────────────────────────────


def test_raport_pokrycia_liczy_ulamek_niepustych_wartosci() -> None:
    df = _df_mecze([
        {"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B", "hst": 5.0, "ast": 3.0},
        {"date": pd.Timestamp("2026-01-02"), "home": "C", "away": "D"},
    ])

    raport = af_stats.raport_pokrycia(df)

    assert raport["hst"] == pytest.approx(0.5)
    assert raport["ast"] == pytest.approx(0.5)


def test_raport_pokrycia_pustej_ramki_nie_dzieli_przez_zero() -> None:
    raport = af_stats.raport_pokrycia(pd.DataFrame(columns=af_stats.KOLUMNY_PLIKU))
    assert raport["hst"] == 0.0


# ─────────────────────────── load_cached ───────────────────────────────────


def _zapisz_dataset(tmp_path, monkeypatch, df: pd.DataFrame) -> None:
    """Podstawia katalog cache i kładzie tam `full_dataset.parquet`."""
    monkeypatch.setattr(hl, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(af_stats, "SCIEZKA_AF_STATS", tmp_path / "af_stats.parquet")
    df.to_parquet(tmp_path / "full_dataset.parquet", index=False)


def test_load_cached_scala_statystyki_z_af(tmp_path, monkeypatch) -> None:
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    _zapisz_dataset(tmp_path, monkeypatch, df)
    af_stats.zapisz_af_stats(pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B", hst=6.0, ast=4.0),
    ]))

    wynik = hl.load_cached()

    assert wynik.loc[0, "hst"] == 6.0


def test_load_cached_bez_pliku_af_nie_wywraca_odczytu(tmp_path, monkeypatch) -> None:
    """Brak backfillu to stan normalny — dataset ma się wczytać jak dotąd."""
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    _zapisz_dataset(tmp_path, monkeypatch, df)

    wynik = hl.load_cached()

    assert len(wynik) == 1
    assert pd.isna(wynik.loc[0, "hst"])


def test_load_cached_wylacznik_oddaje_surowy_parquet(tmp_path, monkeypatch) -> None:
    """Pomiar A/B potrzebuje ramienia BEZ statystyk z TEGO SAMEGO pliku.

    Dwa ramiona czytające dwa różne pliki różniłyby się nie tylko statystykami,
    a wtedy pomiar mierzy co innego, niż nazwa mu przypisuje.
    """
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    _zapisz_dataset(tmp_path, monkeypatch, df)
    af_stats.zapisz_af_stats(pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B", hst=6.0, ast=4.0),
    ]))

    assert pd.isna(hl.load_cached(z_af=False).loc[0, "hst"])
    assert hl.load_cached(z_af=True).loc[0, "hst"] == 6.0


def test_load_cached_loguje_pokrycie_strzalow(tmp_path, monkeypatch, caplog) -> None:
    """Bez tej liczby brak pliku w OBRAZIE wyglada jak liga, ktora strzalow nie ma."""
    df = _df_mecze([{"date": pd.Timestamp("2026-01-01"), "home": "A", "away": "B"}])
    _zapisz_dataset(tmp_path, monkeypatch, df)
    af_stats.zapisz_af_stats(pd.DataFrame([
        _af_wiersz(date=pd.Timestamp("2026-01-01"), home="A", away="B", hst=6.0, ast=4.0),
    ]))

    with caplog.at_level(logging.INFO, logger="footstats.data.historical_loader"):
        hl.load_cached()

    assert any("strzal" in r.message.lower() for r in caplog.records), (
        f"brak logu pokrycia; zapisano: {[r.message for r in caplog.records]}"
    )


# ────────────────── integracja: strzaly realnie zmieniaja lambda ────────────


def test_strzaly_z_af_zmieniaja_ratingi_ligowe() -> None:
    """Cel calego zadania: `form.py` ma przestac cicho wracac do samych goli.

    Dzis w 19 ligach kolumny `hst`/`ast` ISTNIEJA, ale sa NaN. Guard
    `{"hst","ast"} <= set(columns)` przechodzi, `_tabela_ratingow` robi `dropna`
    i wraca None — `WAGA_STRZALOW=0.7` jest ignorowana, a nic nie pada.
    Ten test pilnuje, ze po scaleniu juz tak nie jest.

    Kazda druzyna dostaje komplet meczow: `form.MIN_MECZOW_LIGOWYCH = 6` wyrzuca
    druzyny z krotsza historia, wiec zbyt maly zestaw dalby test zielony
    z niewlasciwego powodu — z pustej tabeli, nie z dzialajacego blendu.
    """
    from footstats.core.form import sily_ligowe
    from footstats.core.wf_harness import adapt_to_prod_schema

    # Trzy druzyny, kazda para po 8 razy w obie strony → 48 meczow, po 16 na druzyne.
    # Gole rozstrzygaja podobnie dla wszystkich, ROZNICUJA dopiero strzaly.
    uklady = [
        ("Mocny", "Slaby",  2, 1, 9, 2),
        ("Slaby", "Mocny",  1, 2, 2, 9),
        ("Mocny", "Sredni", 2, 1, 8, 4),
        ("Sredni", "Mocny", 1, 2, 4, 8),
        ("Sredni", "Slaby", 2, 1, 6, 3),
        ("Slaby", "Sredni", 1, 2, 3, 6),
    ]
    mecze, statystyki = [], []
    for i in range(8):
        for gosp, gosc, hg, ag, sg, sa in uklady:
            data = pd.Timestamp("2026-01-01") + pd.Timedelta(days=len(mecze))
            mecze.append({"date": data, "league": "TEST-Liga", "home": gosp, "away": gosc,
                          "hg": float(hg), "ag": float(ag),
                          "hs": np.nan, "as_": np.nan, "hst": np.nan, "ast": np.nan})
            statystyki.append(_af_wiersz(date=data, home=gosp, away=gosc,
                                         hs=float(sg * 2), as_=float(sa * 2),
                                         hst=float(sg), ast=float(sa)))

    df = pd.DataFrame(mecze)
    af = pd.DataFrame(statystyki)

    bez = sily_ligowe(adapt_to_prod_schema(df), waga_strzalow=0.7)
    ze = sily_ligowe(adapt_to_prod_schema(af_stats.scal_statystyki(df, af)),
                     waga_strzalow=0.7)

    assert bez is not None and ze is not None, "za malo meczow — tabela ligowa pusta"
    tab_bez, tab_ze = bez[0], ze[0]
    assert {"Mocny", "Sredni", "Slaby"} <= set(tab_ze), "druzyna wypadla z tabeli"

    assert tab_ze["Mocny"]["atak_dom"] != pytest.approx(tab_bez["Mocny"]["atak_dom"]), (
        "strzaly nie zmienily ratingu — blend z form.py dalej jest martwy"
    )
    assert tab_ze["Mocny"]["atak_dom"] > tab_ze["Slaby"]["atak_dom"], (
        "druzyna o lepszych strzalach ma slabszy atak niz gorsza"
    )
