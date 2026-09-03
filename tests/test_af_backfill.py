"""Backfill statystyk z API-Football: dopasowanie, budżet, wznawialność.

19 z 40 lig datasetu ma ZERO strzałów celnych (48.7% zbioru, ~68 000 meczów).
Kolumny `hst`/`ast` tam istnieją, ale są NaN, więc `form.sily_ligowe` przechodzi
guard obecności kolumn, po `dropna` dostaje pustkę i `WAGA_STRZALOW=0.7` jest
cicho ignorowana — λ leci z samych goli i nic nie pada.

FAIL-CLOSED jest tu zasadą nadrzędną. Mecz bez wpisu wraca do goli po cichu
i to jest stan normalny; mecz z CUDZYMI statystykami psuje λ tak, że nikt tego
nie zauważy. Dlatego każde dopasowanie musi przejść cztery niezależne warstwy:
mapa składu ligi, data ±1 dnia, zgodność WYNIKU, jednoznaczne przypisanie stron.

Dwie pułapki API zmierzone 2026-09-03 przed napisaniem tego kodu:

  * `/fixtures` NIE przyjmuje parametru `page` — odmowę oddaje jako **HTTP 200**
    z `results: 0` i `errors: {"page": "The Page field do not exist."}`.
    Stronicowanie przez `page` dałoby zero fixture'ów dla KAŻDEJ ligi i cicho
    nie zrobiło nic. Jedno zapytanie `?league=&season=` zwraca cały sezon.
  * Licznik `/status` ma opóźnienie: po ~61 zapytaniach pokazywał +5, chwilę
    później +43. Wiarygodny jest nagłówek `x-ratelimit-requests-remaining`
    na KAŻDEJ odpowiedzi — bramkowanie wyłącznie na `/status` przestrzeli limit.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.data import af_backfill as ab
from footstats.data import af_stats


# ─────────────────────────── parser statystyk ──────────────────────────────


class TestParsera:
    def test_czyta_strzaly_celne_wszystkie_i_xg(self) -> None:
        out = ab.statystyki_druzyny({
            "Shots on Goal": 6, "Total Shots": 14, "expected_goals": "1.87",
            "Ball Possession": "58%", "Corner Kicks": 7,
        })
        assert out == {"st_celne": 6.0, "st_wszystkie": 14.0, "xg": 1.87}

    def test_brak_typu_daje_none(self) -> None:
        out = ab.statystyki_druzyny({"Corner Kicks": 7})
        assert out["st_celne"] is None and out["xg"] is None

    def test_wartosc_none_nie_wywala(self) -> None:
        assert ab.statystyki_druzyny({"Shots on Goal": None})["st_celne"] is None

    def test_wartosc_nieliczbowa_traktowana_jak_brak(self) -> None:
        assert ab.statystyki_druzyny({"Shots on Goal": "brak"})["st_celne"] is None

    def test_wartosc_logiczna_nie_jest_liczba(self) -> None:
        """`bool` jest podklasą `int` — bez jawnego odsiania True stałoby się 1.0."""
        assert ab.statystyki_druzyny({"Shots on Goal": True})["st_celne"] is None


class TestSensownosci:
    @pytest.mark.parametrize(("celne", "wszystkie"), [(9.0, 5.0), (-1.0, 10.0), (60.0, 70.0)])
    def test_bezsensowne_liczby_odrzucone(self, celne: float, wszystkie: float) -> None:
        """Celnych nie może być więcej niż wszystkich ani 60 na mecz.

        `hst > hs` znaczy, że pola znaczą co innego, niż zakładamy — a wtedy
        lepiej nie mieć danych niż mieć przekręcone.
        """
        assert not ab.wiersz_sensowny({"hst": celne, "hs": wszystkie, "ast": 3.0, "as_": 8.0})

    def test_poprawny_wiersz_przechodzi(self) -> None:
        assert ab.wiersz_sensowny({"hst": 6.0, "hs": 14.0, "ast": 3.0, "as_": 9.0})

    def test_brak_strzalow_wszystkich_nie_blokuje_celnych(self) -> None:
        assert ab.wiersz_sensowny({"hst": 6.0, "hs": None, "ast": 3.0, "as_": None})

    def test_brak_celnych_odrzuca_wiersz(self) -> None:
        """Bez `hst`/`ast` wiersz nie niesie NIC, co czyta model."""
        assert not ab.wiersz_sensowny({"hst": None, "hs": 14.0, "ast": None, "as_": 9.0})


# ─────────────────────────── mapa składu ligi ──────────────────────────────


class TestMapySkladu:
    def test_dokladne_nazwy_trafiaja_do_mapy(self) -> None:
        mapa, raport = ab.dopasuj_sklad(["Legia Warszawa"], ["Legia Warszawa"])
        assert mapa == {"Legia Warszawa": "Legia Warszawa"}
        assert raport["dokladne"] == 1

    def test_dokladne_zdejmuje_kandydata_z_puli_rozmytej(self) -> None:
        """Wisła Płock ma swoje dokładne dopasowanie — nie może przegrać z Krakowem.

        To jest cały powód, dla którego mapa jest budowana PER LIGA. W puli ~20
        nazw obie Wisły mają swoje dokładne odpowiedniki i żadna nie wchodzi na
        etap rozmyty; globalnie `team_similarity` dałoby obu tyle samo.
        """
        mapa, _ = ab.dopasuj_sklad(["Wisla Plock", "Wisla Krakow"],
                                   ["Wisla Plock", "Wisla Krakow"])
        assert mapa["Wisla Plock"] == "Wisla Plock"
        assert mapa["Wisla Krakow"] == "Wisla Krakow"

    def test_dwie_nazwy_zrodla_na_ta_sama_druzyne_odrzucaja_obie(self) -> None:
        mapa, raport = ab.dopasuj_sklad(["Wisla", "Wisla SA"], ["Wisla Krakow"])
        assert mapa == {}
        assert raport["sporne"] >= 1

    def test_remis_nie_daje_dopasowania(self) -> None:
        mapa, _ = ab.dopasuj_sklad(["United"], ["Manchester United", "Newcastle United"])
        assert mapa == {}

    def test_brak_kandydata_powyzej_progu(self) -> None:
        mapa, raport = ab.dopasuj_sklad(["Sydney FC"], ["Legia Warszawa"])
        assert mapa == {}
        assert raport["brak"] == 1

    def test_puste_wejscia_nie_wywalaja(self) -> None:
        assert ab.dopasuj_sklad([], [])[0] == {}
        assert ab.dopasuj_sklad(["X"], [])[0] == {}

    def test_progi_sa_zachowawcze(self) -> None:
        assert ab.PROG >= 0.80
        assert ab.MARGINES >= 0.10

    def test_wynik_nie_zalezy_od_kolejnosci_wejscia(self) -> None:
        a, _ = ab.dopasuj_sklad(["Bayern Munchen"], ["Bayern Munich", "Hansa Rostock"])
        b, _ = ab.dopasuj_sklad(["Bayern Munchen"], ["Hansa Rostock", "Bayern Munich"])
        assert a == b


# ─────────────────────────── dopasowanie meczów ────────────────────────────


def _df_liga(wiersze: list[dict]) -> pd.DataFrame:
    baza = {"league": "TEST-Liga", "hg": 1.0, "ag": 0.0}
    df = pd.DataFrame([{**baza, **w} for w in wiersze])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _fixture(fid: int, data: str, dom: str, gosc: str, hg: int, ag: int) -> dict:
    return {
        "fixture": {"id": fid, "date": data},
        "teams": {"home": {"name": dom}, "away": {"name": gosc}},
        "goals": {"home": hg, "away": ag},
    }


class TestDopasowaniaMeczow:
    def test_dopasowuje_po_nazwach_dacie_i_wyniku(self) -> None:
        df = _df_liga([{"date": "2026-08-01", "home": "Legia", "away": "Lech",
                        "hg": 2.0, "ag": 1.0}])
        fx = [_fixture(1, "2026-08-01T18:00:00+00:00", "Legia", "Lech", 2, 1)]

        pary, raport = ab.dopasuj_mecze(df, fx)

        assert len(pary) == 1
        assert pary[0].af_fixture_id == 1
        assert raport["dopasowane"] == 1

    def test_data_przesunieta_o_dobe_wciaz_dopasowuje(self) -> None:
        """AF podaje kick-off w UTC, football-data datę lokalną.

        Mecz o 21:00 w Meksyku to 03:00 UTC następnego dnia — bez tolerancji
        stracilibyśmy całe strefy czasowe.
        """
        df = _df_liga([{"date": "2026-08-01", "home": "Legia", "away": "Lech",
                        "hg": 2.0, "ag": 1.0}])
        fx = [_fixture(1, "2026-08-02T03:00:00+00:00", "Legia", "Lech", 2, 1)]

        pary, _ = ab.dopasuj_mecze(df, fx)
        assert len(pary) == 1

    def test_niezgodny_wynik_odrzuca_mecz(self) -> None:
        """Weryfikacja wynikiem to klucz NIEZALEŻNY od nazw i za darmo.

        Zła para z tym samym wynikiem tego samego dnia jest praktycznie
        niemożliwa — to najtańsze zabezpieczenie w całym łańcuchu.
        """
        df = _df_liga([{"date": "2026-08-01", "home": "Legia", "away": "Lech",
                        "hg": 2.0, "ag": 1.0}])
        fx = [_fixture(1, "2026-08-01T18:00:00+00:00", "Legia", "Lech", 0, 0)]

        pary, raport = ab.dopasuj_mecze(df, fx)
        assert pary == []
        assert raport["wynik_niezgodny"] == 1

    def test_dwa_kandydaty_w_oknie_odrzucaja_mecz(self) -> None:
        df = _df_liga([{"date": "2026-08-01", "home": "Legia", "away": "Lech",
                        "hg": 2.0, "ag": 1.0}])
        fx = [_fixture(1, "2026-08-01T18:00:00+00:00", "Legia", "Lech", 2, 1),
              _fixture(2, "2026-08-02T18:00:00+00:00", "Legia", "Lech", 2, 1)]

        pary, raport = ab.dopasuj_mecze(df, fx)
        assert pary == []
        assert raport["wiele_kandydatow"] == 1

    def test_mecz_spoza_fixture_ow_liczony_jako_brak(self) -> None:
        df = _df_liga([{"date": "2020-08-01", "home": "Legia", "away": "Lech"}])
        fx = [_fixture(1, "2026-08-01T18:00:00+00:00", "Legia", "Lech", 1, 0)]

        pary, raport = ab.dopasuj_mecze(df, fx)
        assert pary == []
        assert raport["brak_w_af"] == 1

    def test_juz_pobrane_pomija_bez_zapytania(self) -> None:
        df = _df_liga([{"date": "2026-08-01", "home": "Legia", "away": "Lech",
                        "hg": 2.0, "ag": 1.0}])
        fx = [_fixture(1, "2026-08-01T18:00:00+00:00", "Legia", "Lech", 2, 1)]

        pary, raport = ab.dopasuj_mecze(
            df, fx, juz_pobrane={(pd.Timestamp("2026-08-01"), "Legia", "Lech")})
        assert pary == []
        assert raport["juz_mamy"] == 1


# ─────────────────────────── pobranie fixture'ów ───────────────────────────


class TestPobieraniaFixtures:
    def test_nie_wysyla_parametru_page(self) -> None:
        """`/fixtures` odrzuca `page` przez HTTP 200 z pustą listą — zero fixture'ów."""
        widziane: list[dict] = []

        class _Klient:
            def _get(self, endpoint, params=None, **kw):
                widziane.append(dict(params or {}))
                return {"response": [_fixture(1, "2026-08-01T18:00:00+00:00",
                                              "A", "B", 1, 0)], "errors": []}

        out = ab.fixtures_ligi_sezonu(_Klient(), 88, 2025)
        assert len(out) == 1
        assert "page" not in widziane[0], f"wyslano zabroniony parametr: {widziane[0]}"

    def test_errors_w_tresci_traktowane_jak_awaria(self) -> None:
        """HTTP 200 z `errors` to odmowa, nie „brak meczów tego sezonu"."""
        class _Klient:
            def _get(self, endpoint, params=None, **kw):
                return {"response": [], "errors": {"page": "The Page field do not exist."}}

        assert ab.fixtures_ligi_sezonu(_Klient(), 88, 2025) == []

    def test_blokada_konta_zatrzaskuje_bramke(self) -> None:
        from footstats.core import apisports_gate

        class _Klient:
            def _get(self, endpoint, params=None, **kw):
                return {"errors": {"access": "Your account is suspended"}, "response": []}

        assert ab.fixtures_ligi_sezonu(_Klient(), 88, 2025) == []
        assert not apisports_gate.wlaczone()

    def test_brak_odpowiedzi_daje_pusta_liste(self) -> None:
        class _Klient:
            def _get(self, endpoint, params=None, **kw):
                return None

        assert ab.fixtures_ligi_sezonu(_Klient(), 88, 2025) == []


# ─────────────────────────── pętla backfillu ───────────────────────────────


def _pary(n: int) -> list[ab.Para]:
    return [
        ab.Para(date=pd.Timestamp("2026-08-01") + pd.Timedelta(days=i),
                league="TEST-Liga", home=f"Dom{i}", away=f"Gosc{i}",
                af_fixture_id=1000 + i, af_home=f"Dom{i} FC", af_away=f"Gosc{i} FC")
        for i in range(n)
    ]


def _stat_ok(para: ab.Para) -> tuple[dict, int]:
    return ({
        para.af_home: {"Shots on Goal": 6, "Total Shots": 14, "expected_goals": "1.5"},
        para.af_away: {"Shots on Goal": 3, "Total Shots": 9, "expected_goals": "0.8"},
    }, 7000)


def _pobierz_ok(api_key, fixture_id):
    return _stat_ok(next(p for p in _pary(20) if p.af_fixture_id == fixture_id))


class TestWznawialnosci:
    def test_przerwanie_zostawia_to_co_pobrane(self, tmp_path) -> None:
        plik = tmp_path / "af_stats.parquet"
        licznik = {"n": 0}

        def _pobierz(api_key, fixture_id):
            licznik["n"] += 1
            if licznik["n"] > 3:
                raise KeyboardInterrupt
            return _pobierz_ok(api_key, fixture_id)

        with pytest.raises(KeyboardInterrupt):
            ab.backfill(_pary(10), pobierz=_pobierz, api_key="k",
                        sciezka=plik, zapis_co=1, budzet=100)

        assert len(af_stats.wczytaj_af_stats(plik)) == 3

    def test_wznowienie_nie_placi_za_to_co_juz_jest(self, tmp_path) -> None:
        plik = tmp_path / "af_stats.parquet"
        ab.backfill(_pary(3), pobierz=_pobierz_ok, api_key="k",
                    sciezka=plik, zapis_co=10, budzet=100)

        zapytania: list[int] = []

        def _pobierz(api_key, fixture_id):
            zapytania.append(fixture_id)
            return _pobierz_ok(api_key, fixture_id)

        ab.backfill(_pary(5), pobierz=_pobierz, api_key="k",
                    sciezka=plik, zapis_co=10, budzet=100)
        assert zapytania == [1003, 1004]

    def test_pusta_odpowiedz_zapisuje_slad_zeby_nie_placic_dwa_razy(self, tmp_path) -> None:
        """ENG-National League i FIN-Veikkausliiga nie mają w AF żadnych statystyk."""
        plik = tmp_path / "af_stats.parquet"
        ab.backfill(_pary(2), pobierz=lambda k, f: ({}, 7000), api_key="k",
                    sciezka=plik, zapis_co=10, budzet=100)

        assert set(af_stats.wczytaj_af_stats(plik)["status"]) == {"brak_statystyk"}

        zapytania: list[int] = []
        ab.backfill(_pary(2), pobierz=lambda k, f: (zapytania.append(f) or {}, 7000),
                    api_key="k", sciezka=plik, zapis_co=10, budzet=100)
        assert zapytania == []


class TestBudzetu:
    def test_wlasny_budzet_zatrzymuje_przebieg(self, tmp_path) -> None:
        plik = tmp_path / "af_stats.parquet"
        zapytania: list[int] = []

        def _pobierz(api_key, fixture_id):
            zapytania.append(fixture_id)
            return _pobierz_ok(api_key, fixture_id)

        wynik = ab.backfill(_pary(10), pobierz=_pobierz, api_key="k",
                            sciezka=plik, zapis_co=10, budzet=4)
        assert len(zapytania) == 4
        assert wynik["powod_stopu"] == "budzet_przebiegu"

    def test_naglowek_limitu_zatrzymuje_przed_rezerwa_potoku(self, tmp_path) -> None:
        """Potok produkcyjny (rozliczenia, składy, sędzia) dzieli ten sam limit.

        Wyczerpanie go pracą offline skończyłoby się HTTP 429 na porannym jobie,
        czyli awarią produkcji wywołaną backfillem.
        """
        plik = tmp_path / "af_stats.parquet"
        wynik = ab.backfill(_pary(5),
                            pobierz=lambda k, f: ({}, ab.REZERWA_POTOKU),
                            api_key="k", sciezka=plik, zapis_co=10, budzet=100)
        assert wynik["powod_stopu"] == "rezerwa_potoku"
        assert wynik["pobrane"] == 1, "stop ma nastapic PO odpowiedzi, ktora to zglosila"

    def test_brak_naglowka_nie_zatrzymuje_przebiegu(self, tmp_path) -> None:
        """Nieznane pozostało to nie to samo co zero — nie zgadujemy w dół."""
        plik = tmp_path / "af_stats.parquet"
        wynik = ab.backfill(_pary(3), pobierz=lambda k, f: ({}, None), api_key="k",
                            sciezka=plik, zapis_co=10, budzet=100)
        assert wynik["powod_stopu"] == "koniec"
        assert wynik["pobrane"] == 3


class TestBramki:
    def test_zamknieta_bramka_nie_wysyla_niczego(self, tmp_path, monkeypatch) -> None:
        from footstats.core import apisports_gate

        monkeypatch.setenv(apisports_gate.ENV_WYLACZNIK, "0")
        plik = tmp_path / "af_stats.parquet"

        def _nie_wolno(api_key, fixture_id):
            raise AssertionError("bramka zamknieta, a poszlo zapytanie")

        wynik = ab.backfill(_pary(3), pobierz=_nie_wolno, api_key="k",
                            sciezka=plik, zapis_co=10, budzet=100)
        assert wynik["powod_stopu"] == "bramka"


class TestZapisu:
    def test_strony_przypisane_po_nazwach_z_fixture(self, tmp_path) -> None:
        plik = tmp_path / "af_stats.parquet"
        ab.backfill(_pary(1), pobierz=_pobierz_ok, api_key="k",
                    sciezka=plik, zapis_co=1, budzet=100)

        w = af_stats.wczytaj_af_stats(plik).iloc[0]
        assert (w["hst"], w["ast"]) == (6.0, 3.0)
        assert (w["hs"], w["as_"]) == (14.0, 9.0)
        assert w["status"] == "ok"

    def test_nierozpoznane_strony_odrzucaja_wiersz(self, tmp_path) -> None:
        """Nie zgadujemy, która drużyna jest gospodarzem.

        Pomyłka odwróciłaby atak z obroną w ratingach i nic by nie padło.
        """
        plik = tmp_path / "af_stats.parquet"
        ab.backfill(_pary(1),
                    pobierz=lambda k, f: ({"Ktos Inny": {"Shots on Goal": 6},
                                           "Ktos Jeszcze": {"Shots on Goal": 3}}, 7000),
                    api_key="k", sciezka=plik, zapis_co=1, budzet=100)

        assert set(af_stats.wczytaj_af_stats(plik)["status"]) == {"brak_statystyk"}

    def test_bezsensowne_liczby_nie_trafiaja_do_pliku(self, tmp_path) -> None:
        plik = tmp_path / "af_stats.parquet"
        p = _pary(1)[0]
        ab.backfill([p],
                    pobierz=lambda k, f: ({
                        p.af_home: {"Shots on Goal": 99, "Total Shots": 4},
                        p.af_away: {"Shots on Goal": 3, "Total Shots": 9},
                    }, 7000),
                    api_key="k", sciezka=plik, zapis_co=1, budzet=100)

        assert set(af_stats.wczytaj_af_stats(plik)["status"]) == {"brak_statystyk"}

    def test_zapisany_plik_scala_sie_z_datasetem(self, tmp_path) -> None:
        """Domknięcie łańcucha: to, co backfill zapisze, ma realnie wejść do ramki."""
        plik = tmp_path / "af_stats.parquet"
        pary = _pary(2)
        ab.backfill(pary, pobierz=_pobierz_ok, api_key="k",
                    sciezka=plik, zapis_co=1, budzet=100)

        df = pd.DataFrame([{"date": p.date, "league": p.league, "home": p.home,
                            "away": p.away, "hg": 1.0, "ag": 0.0,
                            "hs": None, "as_": None, "hst": None, "ast": None}
                           for p in pary])
        scalone = af_stats.scal_statystyki(df, af_stats.wczytaj_af_stats(plik))
        assert list(scalone["hst"]) == [6.0, 6.0]
        assert list(scalone["ast"]) == [3.0, 3.0]


# ────────────────── luki wykryte mutacjami (2026-09-03) ────────────────────


def test_jedna_strona_bez_strzalow_odrzuca_wiersz() -> None:
    """Komplet znaczy OBIE strony. Rating liczy sie z pary, nie z polowy meczu.

    Wiersz z `hst` i bez `ast` dalby drużynie gospodarza ocenę ze strzałów,
    a gościowi z samych goli — dwie różne miary w jednej tabeli ligowej.
    """
    assert not ab.wiersz_sensowny({"hst": 6.0, "hs": 14.0, "ast": None, "as_": 9.0})
    assert not ab.wiersz_sensowny({"hst": None, "hs": 14.0, "ast": 3.0, "as_": 9.0})


def test_rowne_podobienstwo_dwoch_klubow_nie_daje_dopasowania() -> None:
    """Dwie Wisly punktuja identycznie (0.800 obie) — wybor bylby rzutem moneta.

    Zmierzone: `team_similarity` daje "Wisla" wobec "Wisla Plock" i "Wisla Krakow"
    dokladnie tyle samo. Bez marginesu przewagi wygralaby ta, ktora akurat jest
    pierwsza na liscie — a statystyki wladowalyby sie w mecze innego klubu.
    """
    mapa, raport = ab.dopasuj_sklad(["Wisla"], ["Wisla Plock", "Wisla Krakow"])
    assert mapa == {}, f"rozstrzygniety remis: {mapa}"
    assert raport["remis"] == 1


def test_przewaga_powyzej_marginesu_daje_dopasowanie() -> None:
    """Kontrola od drugiej strony: margines nie moze blokowac WSZYSTKIEGO.

    Bez tego testu `MARGINES = 1.0` (nic nigdy nie przechodzi) byloby zielone,
    a backfill nie dopasowalby ani jednej nazwy wymagajacej dopasowania rozmytego.
    """
    mapa, raport = ab.dopasuj_sklad(
        ["Borussia Dortmund BVB"], ["Borussia Dortmund", "Bayern Munich"])
    assert mapa == {"Borussia Dortmund BVB": "Borussia Dortmund"}
    assert raport["rozmyte"] == 1, (
        "para poszla sciezka DOKLADNA — test nie sprawdza wtedy marginesu"
    )


# ────────────────── mapa lig i produkcyjny pobieracz ───────────────────────


class TestMapyLig:
    def test_wczytuje_realna_mape_z_repo(self) -> None:
        mapa = ab.wczytaj_mape_lig()
        assert mapa, "mapa lig pusta — backfill nie mialby czego pobierac"
        assert "POL-Ekstraklasa" in mapa

    def test_klucze_komentarzy_nie_wchodza_do_mapy(self) -> None:
        """`_komentarz` i `_bez_statystyk_w_af` to metadane, nie ligi."""
        assert not [k for k in ab.wczytaj_mape_lig() if k.startswith("_")]

    def test_brak_pliku_daje_pusta_mape_a_nie_wyjatek(self, tmp_path) -> None:
        assert ab.wczytaj_mape_lig(tmp_path / "nie_ma.json") == {}

    def test_uszkodzony_plik_daje_pusta_mape(self, tmp_path, caplog) -> None:
        """Nieczytelna mapa MUSI byc slyszalna — cicho znaczy backfill bez lig."""
        import logging

        plik = tmp_path / "af_league_ids.json"
        plik.write_text("{to nie jest json", encoding="utf-8")
        with caplog.at_level(logging.ERROR):
            assert ab.wczytaj_mape_lig(plik) == {}
        assert "af_league_ids" in caplog.text


class TestPobieraczaProdukcyjnego:
    def test_zwraca_statystyki_i_pozostalo_z_naglowka(self, monkeypatch) -> None:
        from footstats.scrapers import results_updater as ru

        class _Odp:
            status_code = 200
            headers = {"x-ratelimit-requests-remaining": "6421"}

            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {"response": [
                    {"team": {"name": "Legia"},
                     "statistics": [{"type": "Shots on Goal", "value": 6}]},
                ]}

        wywolania: list[str] = []
        monkeypatch.setattr(ru.requests, "get",
                            lambda url, **kw: wywolania.append(url) or _Odp())

        stat, pozostalo = ab.pobierz_statystyki("klucz", 123)

        assert stat["Legia"]["Shots on Goal"] == 6
        assert pozostalo == 6421
        assert len(wywolania) == 1, "backfill nie moze doklejac /fixtures/events"
        assert "statistics" in wywolania[0]

    def test_brak_naglowka_daje_none_a_nie_zero(self, monkeypatch) -> None:
        """Nieznane pozostalo to nie to samo co wyczerpany limit."""
        from footstats.scrapers import results_updater as ru

        class _Odp:
            status_code = 200
            headers: dict = {}

            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {"response": []}

        monkeypatch.setattr(ru.requests, "get", lambda url, **kw: _Odp())
        assert ab.pobierz_statystyki("klucz", 1)[1] is None

    def test_zamknieta_bramka_nie_wysyla_zapytania(self, monkeypatch) -> None:
        from footstats.core import apisports_gate
        from footstats.scrapers import results_updater as ru

        monkeypatch.setenv(apisports_gate.ENV_WYLACZNIK, "0")

        def _nie_wolno(*a, **k):
            raise AssertionError("zamknieta bramka, a poszlo zapytanie")

        monkeypatch.setattr(ru.requests, "get", _nie_wolno)
        # None, nie {}: zamknieta bramka znaczy "NIE ZAPYTALISMY", a nie
        # "API odpowiedzialo, ze statystyk nie ma". Gdyby zwracala {}, backfill
        # zapisalby trwaly slad `brak_statystyk` dla kazdego meczu przy
        # zawieszonym koncie — i po odwieszeniu nikt by ich juz nie pobral.
        assert ab.pobierz_statystyki("klucz", 1) == (None, None)


def test_rozliczenia_dalej_dostaja_zdarzenia() -> None:
    """Kontrakt sciezki rozliczen nie moze sie zmienic przez wydzielenie rdzenia.

    `_fetch_match_stats` karmi rynki polowkowe timeline'em zdarzen. Backfill go
    nie potrzebuje, ale rozliczenia tak — i to one chodza codziennie na produkcji.
    """
    import inspect

    from footstats.scrapers import results_updater as ru

    zrodlo = inspect.getsource(ru._fetch_match_stats)
    assert "_fetch_statystyki_surowe" in zrodlo
    assert "_fetch_match_events" in zrodlo
    assert '"_events"' in zrodlo


def test_nieczytelny_wynik_liczony_osobno_od_niezgodnego() -> None:
    """Dwa rozne stany zrodla, dwa liczniki.

    "AF podal INNY rezultat" znaczy zle dopasowanie meczu. "AF nie podal
    rezultatu wcale" znaczy dziure w danych dostawcy. Wspolny worek zamazalby
    roznice, a to wlasnie proporcja tych dwoch mowi, czy szukac bledu u siebie,
    czy u niego. Liczymy zamiast logowac per mecz — przy kilkuset meczach log
    bylby szumem.
    """
    df = _df_liga([{"date": "2026-08-01", "home": "Legia", "away": "Lech",
                    "hg": 2.0, "ag": 1.0}])
    zepsuty = _fixture(1, "2026-08-01T18:00:00+00:00", "Legia", "Lech", 2, 1)
    zepsuty["goals"] = {"home": None, "away": None}

    pary, raport = ab.dopasuj_mecze(df, [zepsuty])

    assert pary == []
    assert raport["wynik_nieczytelny"] == 1
    assert raport["wynik_niezgodny"] == 0


# ────────────── przejsciowy blad != trwaly brak statystyk ──────────────────


class TestBleduPobrania:
    def test_nieudane_zapytanie_nie_zapisuje_trwalego_sladu(self, tmp_path) -> None:
        """`None` znaczy "nie udalo sie zapytac", `{}` znaczy "API: nie ma".

        Slad `brak_statystyk` jest TRWALY — kolejny przebieg pomija taki mecz bez
        zapytania, zeby nie placic drugi raz. Gdyby przejsciowe HTTP 429 albo
        zerwane polaczenie zapisywalo sie tak samo jak pusta odpowiedz, jeden zly
        kwadrans zatrulby dane na stale, a nastepny przebieg wygladalby na
        kompletny.
        """
        plik = tmp_path / "af_stats.parquet"
        wynik = ab.backfill(_pary(3), pobierz=lambda k, f: (None, 7000), api_key="k",
                            sciezka=plik, zapis_co=1, budzet=100)

        assert wynik["blad_pobrania"] == 3
        assert wynik["ok"] == 0 and wynik["bez_statystyk"] == 0
        assert af_stats.wczytaj_af_stats(plik).empty, (
            "nieudane zapytanie zostawilo slad — te mecze nie beda juz ponowione"
        )

    def test_po_bledzie_mecz_wraca_przy_wznowieniu(self, tmp_path) -> None:
        plik = tmp_path / "af_stats.parquet"
        ab.backfill(_pary(2), pobierz=lambda k, f: (None, 7000), api_key="k",
                    sciezka=plik, zapis_co=1, budzet=100)

        zapytania: list[int] = []

        def _pobierz(api_key, fixture_id):
            zapytania.append(fixture_id)
            return _pobierz_ok(api_key, fixture_id)

        ab.backfill(_pary(2), pobierz=_pobierz, api_key="k",
                    sciezka=plik, zapis_co=1, budzet=100)
        assert zapytania == [1000, 1001], "mecz po bledzie nie zostal ponowiony"

    def test_seria_bledow_konczy_przebieg(self, tmp_path) -> None:
        """Dziesiec bledow pod rzad znaczy trwala awarie, nie wpadke sieci.

        Bez tego backfill waliby w padniete API az do wyczerpania budzetu,
        nie przynoszac ani jednego wiersza.
        """
        plik = tmp_path / "af_stats.parquet"
        zapytania: list[int] = []

        def _pobierz(api_key, fixture_id):
            zapytania.append(fixture_id)
            return None, 7000

        wynik = ab.backfill(_pary(40), pobierz=_pobierz, api_key="k",
                            sciezka=plik, zapis_co=10, budzet=100)
        assert wynik["powod_stopu"] == "bledy_pobrania"
        assert len(zapytania) == ab.MAKS_BLEDOW_POD_RZAD

    def test_udane_zapytanie_zeruje_licznik_bledow(self, tmp_path) -> None:
        """Pojedyncze wpadki rozsiane po przebiegu nie moga go ubic."""
        plik = tmp_path / "af_stats.parquet"
        licznik = {"n": 0}

        def _pobierz(api_key, fixture_id):
            licznik["n"] += 1
            if licznik["n"] % 2:
                return None, 7000
            return _pobierz_ok(api_key, fixture_id)

        wynik = ab.backfill(_pary(20), pobierz=_pobierz, api_key="k",
                            sciezka=plik, zapis_co=5, budzet=100)
        assert wynik["powod_stopu"] == "koniec"
        assert wynik["ok"] == 10


def test_zapisany_plik_ma_liczbowe_kolumny_strzalow(tmp_path) -> None:
    """Typy w pliku musza przezyc pierwszy zapis do PUSTEGO poprzednika.

    `af_stats._pusta_ramka` ma wszystkie kolumny jako `object`. Doklejenie jej
    do swiezych danych przez `concat` psuje typy — pandas ostrzega o tym
    `FutureWarning`, a docelowo `hst`/`ast` zapisalyby sie jako tekst. Model
    czyta je liczbowo, wiec byloby to ciche uszkodzenie danych, za ktore
    zaplacilismy requestami.
    """
    import pandas as _pd

    plik = tmp_path / "af_stats.parquet"
    ab.backfill(_pary(2), pobierz=_pobierz_ok, api_key="k",
                sciezka=plik, zapis_co=1, budzet=100)

    zapisane = af_stats.wczytaj_af_stats(plik)
    for kol in ("hs", "as_", "hst", "ast"):
        assert _pd.api.types.is_numeric_dtype(zapisane[kol]), (
            f"{kol} zapisane jako {zapisane[kol].dtype}, nie liczba"
        )
