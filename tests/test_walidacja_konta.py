"""Walidacja loginu i miesiąca urodzenia — jedna reguła dla wszystkich wejść.

Do 10.09.2026 trzy modele (rejestracja, zmiana loginu, konto zakładane przez
admina) miały każdy WŁASNE „min. 3 znaki” i nic poza tym. Reguła żyje teraz
w jednym module, a testy endpointów sprawdzają, że każde wejście jej używa.
"""
from __future__ import annotations

from datetime import date

import pytest

from footstats.api.walidacja_konta import (
    KOMUNIKAT_NIEPELNOLETNI,
    sprawdz_login,
    sprawdz_miesiac_urodzenia,
)

_DZIS = date(2026, 9, 10)


# ── login ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nazwa", [
    "Jakub",
    "kibic_legii",
    "Łukasz.K",
    "gracz-99",
    "abc",
    "a" * 24,
    # Pułapka Scunthorpe: klub z League Two, nazwa zawiera wulgaryzm EN.
    "ScunthorpeFan",
    # Pułapka „badminton” zawiera „admin” — zastrzeżony jest tylko PREFIKS.
    "badmintonfan",
    # FC Slutsk (Białoruś) — dlatego „slut” nie jest na liście.
    "Slutsk2024",
])
def test_poprawne_nazwy_przechodza(nazwa):
    assert sprawdz_login(nazwa) == nazwa


def test_spacje_na_brzegach_sa_obcinane():
    assert sprawdz_login("  Jakub  ") == "Jakub"


@pytest.mark.parametrize("nazwa", ["ab", "a" * 25, ""])
def test_dlugosc_poza_zakresem(nazwa):
    with pytest.raises(ValueError, match="3.*24"):
        sprawdz_login(nazwa)


@pytest.mark.parametrize("nazwa", ["ja kub", "_start", ".kropka", "emoji😀", "a/b", "x@y.pl"])
def test_niedozwolone_znaki(nazwa):
    with pytest.raises(ValueError, match="znak"):
        sprawdz_login(nazwa)


@pytest.mark.parametrize("nazwa", [
    "kurwa",
    "KuRw4",          # leet + wielkość liter
    "k.u.r.w.a",      # separatory między literami
    "kuuurwa",        # powtórzone litery
    "ch_uj123",
    "pierd0lony",
    "fuuuck",
    "5h1t",
    "jebac_legie",
    "sk.urw1el",
])
def test_wulgaryzmy_odrzucone(nazwa):
    with pytest.raises(ValueError, match="niedozwolone"):
        sprawdz_login(nazwa)


@pytest.mark.parametrize("nazwa", [
    "admin", "Admin2", "administrator", "moderator_pl",
    "footstats_official", "Oficjalny.FootStats", "system", "root",
    "deleted_user_5",
])
def test_nazwy_zastrzezone(nazwa):
    with pytest.raises(ValueError, match="zastrzeżon"):
        sprawdz_login(nazwa)


# ── miesiąc urodzenia ───────────────────────────────────────────────────────

def test_dokladnie_18_lat_temu_ten_sam_miesiac_odrzucony():
    """Dnia nie znamy — urodzony we wrześniu 2008 mógł skończyć 18 lat
    wczoraj albo za trzy tygodnie. Wątpliwość rozstrzygamy na NIE."""
    with pytest.raises(ValueError) as e:
        sprawdz_miesiac_urodzenia("2008-09", _DZIS)
    assert str(e.value) == KOMUNIKAT_NIEPELNOLETNI


def test_miesiac_wczesniej_przechodzi():
    assert sprawdz_miesiac_urodzenia("2008-08", _DZIS) == "2008-08"


def test_dorosly_z_obcietymi_spacjami():
    assert sprawdz_miesiac_urodzenia(" 1990-05 ", _DZIS) == "1990-05"


@pytest.mark.parametrize("wartosc", ["2010-01", "2026-09"])
def test_niepelnoletni_odrzucony(wartosc):
    with pytest.raises(ValueError, match="18"):
        sprawdz_miesiac_urodzenia(wartosc, _DZIS)


@pytest.mark.parametrize("wartosc", ["", "1990", "1990-5", "05-1990", "1990-13", "1990-00",
                                     "1899-12", "2026-10", "abcd-ef"])
def test_nieprawidlowy_format_lub_zakres(wartosc):
    with pytest.raises(ValueError, match="(?i)miesiąc|nieprawidłow"):
        sprawdz_miesiac_urodzenia(wartosc, _DZIS)
