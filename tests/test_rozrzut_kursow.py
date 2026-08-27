"""Czyste funkcje pilotu rozrzutu kursow — devig, referencja, edge."""
import pytest

from footstats.core.rozrzut_kursow import (
    KSIAZKI_REFERENCYJNE,
    WYNIKI_RYNKU,
    cena_referencyjna,
    devig_proporcjonalny,
    edge_bukmacherow,
    ksiazki_kompletne,
    rozrzut,
)


def test_devig_sumuje_sie_do_jednosci():
    p = devig_proporcjonalny({"H": 1.69, "D": 4.21, "A": 4.81})
    assert sum(p.values()) == pytest.approx(1.0)


def test_devig_zdejmuje_marze_wiec_kazde_p_mniejsze_niz_surowe():
    ceny = {"H": 1.69, "D": 4.21, "A": 4.81}
    p = devig_proporcjonalny(ceny)
    for k, kurs in ceny.items():
        assert p[k] < 1.0 / kurs


def test_devig_rynku_bez_marzy_zwraca_surowe_prawdopodobienstwa():
    """Kursy 2.0/2.0 to overround zero — devig nie ma czego zdejmowac."""
    p = devig_proporcjonalny({"Over": 2.0, "Under": 2.0})
    assert p["Over"] == pytest.approx(0.5)


def test_devig_pusty_lub_bledny_zwraca_pusty_slownik():
    assert devig_proporcjonalny({}) == {}
    assert devig_proporcjonalny({"H": 0.0, "A": 1.0}) == {}


def test_referencja_wybiera_pinnacle_gdy_jest():
    """Pinnacle wygrywa nawet gdy w kwotach jest inna ksiazka referencyjna —
    to sprawdza kolejnosc lancucha, nie tylko przewage nad ksiazka zwykla."""
    kwoty = {
        "mybookieag": {"Over": 1.80, "Under": 1.91},
        "betfair_ex_eu": {"Over": 1.84, "Under": 2.01},
        "pinnacle": {"Over": 1.79, "Under": 2.05},
    }
    nazwa, p = cena_referencyjna(kwoty)
    assert nazwa == "pinnacle"
    assert sum(p.values()) == pytest.approx(1.0)


def test_referencja_schodzi_na_gielde_gdy_brak_pinnacle():
    """W chinskiej i J1 Pinnacle moze nie kwotowac — lancuch musi zejsc nizej."""
    kwoty = {
        "mybookieag": {"Over": 1.80, "Under": 1.91},
        "betfair_ex_eu": {"Over": 1.85, "Under": 2.00},
    }
    nazwa, _ = cena_referencyjna(kwoty)
    assert nazwa == "betfair_ex_eu"


def test_referencja_bez_zadnej_ksiazki_referencyjnej_daje_mediane():
    """Fixture NIESYMETRYCZNA: mediana Over 1.85, srednia 1.90. Poprzednia wersja
    miala symetryczne ceny i asercje `sum(p) == 1`, ktora jest prawdziwa
    z konstrukcji devigu — czyli nie sprawdzala nic. Teraz asercja jest
    na WARTOSC, wiec podmiana `median` na srednia daje czerwien."""
    kwoty = {
        "sport888": {"Over": 1.80, "Under": 2.10},
        "williamhill": {"Over": 1.85, "Under": 2.00},
        "betsson": {"Over": 2.05, "Under": 1.80},
    }
    nazwa, p = cena_referencyjna(kwoty)
    assert nazwa == "mediana"
    # mediana Over = 1.85, mediana Under = 2.00 -> overround 1.0405
    assert p["Over"] == pytest.approx((1 / 1.85) / (1 / 1.85 + 1 / 2.00))
    assert p["Over"] == pytest.approx(0.519481, abs=1e-5)


def test_referencja_pomija_ksiazke_z_niepelnym_rynkiem():
    """Ksiazka kwotujaca tylko Over nie pozwala policzyc devigu — nie moze byc
    referencja, bo 'suma odwrotnosci' bylaby liczona z jednego wyniku i devig
    zwrocilby p=1.0 dla Over, czyli cene uczciwa 1.00."""
    kwoty = {
        "pinnacle": {"Over": 1.79},
        "matchbook": {"Over": 1.85, "Under": 2.00},
    }
    nazwa, _ = cena_referencyjna(kwoty)
    assert nazwa == "matchbook"


def test_referencja_pustych_kwot_zwraca_none():
    assert cena_referencyjna({}) is None


def test_edge_dodatni_gdy_kurs_powyzej_ceny_uczciwej():
    p_uczciwe = {"Over": 0.50, "Under": 0.50}
    kwoty = {"soft": {"Over": 2.20, "Under": 1.80}}
    wynik = {(w["bookmaker"], w["outcome"]): w["edge"] for w in edge_bukmacherow(kwoty, p_uczciwe)}
    assert wynik[("soft", "Over")] == pytest.approx(0.10)
    assert wynik[("soft", "Under")] == pytest.approx(-0.10)


def test_edge_pomija_outcome_bez_ceny_uczciwej():
    """Bukmacher moze kwotowac rynek, ktorego referencja nie ma — bez ceny
    uczciwej nie ma z czym porownac i wiersz musi zniknac, nie dostac edge=0."""
    wyniki = edge_bukmacherow({"soft": {"Over": 2.0, "Egzotyk": 5.0}}, {"Over": 0.5})
    assert [w["outcome"] for w in wyniki] == ["Over"]


def test_rozrzut_liczy_min_max_i_rozpietosc():
    """Fixture NIESYMETRYCZNA celowo: mediana 4.60 != srednia 4.80. Przy zestawie
    {4.50, 5.30, 4.90} obie wychodzily 4.90 i podmiana `median` na srednia
    arytmetyczna przechodzila na zielono — test nie sprawdzal wtedy niczego."""
    kwoty = {"a": {"H": 4.50}, "b": {"H": 5.30}, "c": {"H": 4.60}}
    r = rozrzut(kwoty, "H")
    assert r["min"] == pytest.approx(4.50)
    assert r["max"] == pytest.approx(5.30)
    assert r["mediana"] == pytest.approx(4.60)
    assert r["mediana"] != pytest.approx(sum([4.50, 5.30, 4.60]) / 3)
    assert r["rozpietosc_pct"] == pytest.approx(100.0 * (5.30 / 4.50 - 1))
    assert r["ksiazek"] == 3


def test_rozrzut_jednej_ksiazki_daje_zero_rozpietosci():
    """Dwie ksiazki to nie jest rozrzut — rynek roznych mial ich dokladnie dwie.
    Raport musi umiec pokazac, ze nie ma miedzy czym szukac."""
    r = rozrzut({"a": {"H": 4.50}}, "H")
    assert r["ksiazek"] == 1
    assert r["rozpietosc_pct"] == pytest.approx(0.0)


def test_rozrzut_nieznanego_outcome_zwraca_none():
    assert rozrzut({"a": {"H": 4.5}}, "NIE_MA") is None


def test_lancuch_referencyjny_ma_ustalona_kolejnosc():
    """Kolejnosc decyduje o wyniku pomiaru, wiec jest czescia kontraktu."""
    assert KSIAZKI_REFERENCYJNE == ("pinnacle", "betfair_ex_eu", "matchbook")


# --- kompletnosc rynku: najgrozniejsza klasa bledu w tym module -------------

def test_ksiazka_dwa_z_trzech_w_1x2_nie_moze_byc_referencja():
    """REGRES, ktory zawyzalby KAZDY edge. `_MIN_WYNIKOW = 2` uznawalo ksiazke
    kwotujaca 2 z 3 wynikow 1X2 za kompletna. Devig normalizowal wtedy do 1 zbyt
    malo skladnikow, wiec cena uczciwa wychodzila za niska.

    Zmierzone na realnej migawce z 27.08: Pinnacle bez `Draw` dawal cene uczciwa
    Crystal Palace 3.85 zamiast 4.99, czyli edge betfaira +37.8% zamiast +6.24%.
    Prog zabicia pilota to +2%, wiec ten blad nie wygladalby na blad, tylko na
    odkrycie."""
    kwoty = {
        "pinnacle": {"Crystal Palace": 4.81, "Manchester City": 1.69},  # brak Draw
        "betfair_ex_eu": {"Crystal Palace": 5.30, "Draw": 4.20, "Manchester City": 1.72},
    }
    nazwa, p = cena_referencyjna(kwoty, oczekiwane_wyniki=WYNIKI_RYNKU["h2h"])
    assert nazwa == "betfair_ex_eu", "niepelny Pinnacle nie moze byc referencja"
    cena_uczciwa = 1.0 / p["Crystal Palace"]
    assert cena_uczciwa == pytest.approx(5.3433, abs=1e-3)
    edge = {w["outcome"]: w["edge"] for w in edge_bukmacherow(kwoty, p)
            if w["bookmaker"] == "betfair_ex_eu"}
    assert edge["Crystal Palace"] == pytest.approx(-0.0081, abs=1e-3)
    assert edge["Crystal Palace"] < 0.02, "edge nie moze przekroczyc progu pilota"


def test_rynek_pelny_daje_te_sama_liczbe_co_spec():
    """Kontrola pozytywna: na pelnym rynku wynik musi zostac taki, jak w specu."""
    kwoty = {
        "pinnacle": {"Crystal Palace": 4.81, "Draw": 4.21, "Manchester City": 1.69},
        "betfair_ex_eu": {"Crystal Palace": 5.30, "Draw": 4.20, "Manchester City": 1.72},
    }
    nazwa, p = cena_referencyjna(kwoty, oczekiwane_wyniki=WYNIKI_RYNKU["h2h"])
    assert nazwa == "pinnacle"
    assert 1.0 / p["Crystal Palace"] == pytest.approx(4.9887, abs=1e-3)
    edge = {w["outcome"]: w["edge"] for w in edge_bukmacherow(kwoty, p)
            if w["bookmaker"] == "betfair_ex_eu"}
    assert edge["Crystal Palace"] == pytest.approx(0.0624, abs=1e-3)


def test_wynik_brakujacy_u_wszystkich_ksiazek_daje_brak_referencji():
    """Jedyny przypadek, ktorego NIE da sie wykryc porownaniem ksiazek miedzy soba:
    gdy `Draw` wypadl u wszystkich, unia wynikow tez sie kurczy i kazda ksiazka
    wyglada na kompletna. Dlatego `oczekiwane_wyniki` jest konieczne, a brak
    referencji jest WYNIKIEM — lepiej nie podac ceny niz podac policzona z dziury."""
    kwoty = {
        "pinnacle": {"Crystal Palace": 4.60, "Manchester City": 1.70},
        "williamhill": {"Crystal Palace": 4.70, "Manchester City": 1.68},
    }
    assert cena_referencyjna(kwoty, oczekiwane_wyniki=WYNIKI_RYNKU["h2h"]) is None
    # Bez parametru tryb unii tego NIE wykrywa — udokumentowane ograniczenie.
    assert cena_referencyjna(kwoty) is not None


def test_bez_parametru_tryb_unii_lapie_luke_pojedynczej_ksiazki():
    kwoty = {
        "pinnacle": {"Over": 1.79},
        "matchbook": {"Over": 1.85, "Under": 2.00},
    }
    assert ksiazki_kompletne(kwoty) == {"matchbook": {"Over": 1.85, "Under": 2.00}}


def test_mediana_liczona_tylko_po_ksiazkach_kompletnych():
    """Mieszanie ksiazek o roznych zestawach wynikow tworzy rynek, ktorego nie
    kwotuje nikt: mediana Over z dwoch cen, Under z jednej, a devig robi z tego
    cene uczciwa."""
    kwoty = {
        "sport888": {"Over": 1.50},                    # niepelna, ma wypasc
        "williamhill": {"Over": 1.95, "Under": 1.95},
        "betsson": {"Over": 1.95, "Under": 1.95},
    }
    nazwa, p = cena_referencyjna(kwoty)
    assert nazwa == "mediana"
    assert p["Over"] == pytest.approx(0.5), "cena 1.50 z niepelnej ksiazki przeciekla"


def test_wyniki_rynku_pokrywaja_oba_rynki_pilota():
    assert WYNIKI_RYNKU == {"h2h": 3, "totals": 2}


def test_edge_odrzuca_kurs_nie_wiekszy_od_jedynki():
    """Jedyna bariera przed wpuszczeniem uszkodzonego kwotowania do wyniku
    pomiaru. Kurs 1.0 znaczy 'zwrot stawki', nie kwotowanie."""
    wyniki = edge_bukmacherow({"soft": {"Over": 1.0, "Under": 2.20}}, {"Over": 0.5, "Under": 0.5})
    assert [w["outcome"] for w in wyniki] == ["Under"]

