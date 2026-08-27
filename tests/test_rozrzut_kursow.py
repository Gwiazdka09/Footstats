"""Czyste funkcje pilotu rozrzutu kursow — devig, referencja, edge."""
import pytest

from footstats.core.rozrzut_kursow import (
    KSIAZKI_REFERENCYJNE,
    cena_referencyjna,
    devig_proporcjonalny,
    edge_bukmacherow,
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
    kwoty = {
        "sport888": {"Over": 1.80, "Under": 1.90},
        "williamhill": {"Over": 1.90, "Under": 1.80},
        "betsson": {"Over": 1.85, "Under": 1.85},
    }
    nazwa, p = cena_referencyjna(kwoty)
    assert nazwa == "mediana"
    assert sum(p.values()) == pytest.approx(1.0)


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
    kwoty = {"a": {"H": 4.50}, "b": {"H": 5.30}, "c": {"H": 4.90}}
    r = rozrzut(kwoty, "H")
    assert r["min"] == pytest.approx(4.50)
    assert r["max"] == pytest.approx(5.30)
    assert r["mediana"] == pytest.approx(4.90)
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
