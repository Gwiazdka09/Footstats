"""Walidacja danych konta: login i miesiąc urodzenia (weryfikacja 18+).

JEDNA reguła dla wszystkich wejść. Do 10.09.2026 rejestracja, zmiana loginu
i konto zakładane przez admina miały każde własne „min. 3 znaki” — trzy kopie
tej samej reguły, każda do poprawienia osobno (wzorzec, który w tym repo
wracał już kilka razy). Walidatory Pydantic w `auth.py` i `admin_users.py`
tylko wołają te funkcje.

Filtr wulgaryzmów jest celowo prosty (lista rdzeni + normalizacja leet),
nie moderacja treści: odcina oczywiste przypadki, a nie gwarantuje, że nic
nie przejdzie. Rdzenie dobrane pod NAZWY Z PIŁKI — stąd wyjątek dla
Scunthorpe i brak „slut” (FC Slutsk).
"""
from __future__ import annotations

import re
from datetime import date

LOGIN_MIN = 3
LOGIN_MAX = 24

# Litera/cyfra na początku, potem także _ . -  — bez spacji i znaków, które
# w nazwie wyświetlanej w rankingu udawałyby e-mail albo ścieżkę.
_LITERY = "0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż"
_LOGIN_RE = re.compile(rf"^[{_LITERY}][{_LITERY}_.\-]*$")

_BEZ_OGONKOW = str.maketrans("ąćęłńóśźż", "acelnoszz")
_LEET = str.maketrans({"0": "o", "3": "e", "4": "a", "5": "s", "7": "t",
                       "8": "b", "@": "a", "$": "s", "!": "i"})

# Rdzenie po normalizacji (bez ogonków, bez powtórzonych liter).
_WULGARYZMY: tuple[str, ...] = (
    # PL
    "kurw", "chuj", "huj", "pierdol", "spierd", "pizd", "jeba", "jebi", "jebn",
    "zjeb", "pojeb", "dziwk", "szmat", "cwel", "kutas", "cipk",
    # EN
    "fuck", "shit", "cunt", "bitch", "whore", "niga", "fagot", "ashole",
    "hitler", "porn",
)
# Słowa, które zawierają rdzeń, a są niewinne — wycinane przed sprawdzeniem.
_WYJATKI: tuple[str, ...] = ("scunthorpe",)

_ZASTRZEZONE_DOKLADNIE = frozenset({"root", "system", "support", "wsparcie", "pomoc",
                                    "null", "undefined", "anonim"})
_ZASTRZEZONE_PREFIKSY: tuple[str, ...] = ("admin", "moderator", "deleteduser")
_ZASTRZEZONE_WEWNATRZ: tuple[str, ...] = ("footstats",)

KOMUNIKAT_NIEPELNOLETNI = "Serwis jest wyłącznie dla osób, które ukończyły 18 lat."
_ROK_MIN = 1900
_MIESIECY_18_LAT = 18 * 12
_YM_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _normalizuj(tekst: str, jedynka: str = "i") -> str:
    """Małe litery, bez ogonków, leet → litery, bez separatorów, powtórzone
    litery zwinięte („kuuurwa” → „kurwa”, ale też „footstats” → „fotstats”)."""
    baza = tekst.lower().translate(_BEZ_OGONKOW).translate(_LEET).replace("1", jedynka)
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[^a-z]", "", baza))


def _warianty(nazwa: str) -> set[str]:
    """„1” w loginie bywa i „i”, i „l” — sprawdzamy oba odczyty."""
    return {_normalizuj(nazwa, "i"), _normalizuj(nazwa, "l")}


# Listy porównujemy w TEJ SAMEJ postaci co login — inaczej zwinięcie liter
# rozjeżdża się z zapisem na liście („root” vs „rot”).
_WULGARYZMY = tuple(_normalizuj(s) for s in _WULGARYZMY)
_WYJATKI = tuple(_normalizuj(s) for s in _WYJATKI)
_ZASTRZEZONE_DOKLADNIE = frozenset(_normalizuj(s) for s in _ZASTRZEZONE_DOKLADNIE)
_ZASTRZEZONE_PREFIKSY = tuple(_normalizuj(s) for s in _ZASTRZEZONE_PREFIKSY)
_ZASTRZEZONE_WEWNATRZ = tuple(_normalizuj(s) for s in _ZASTRZEZONE_WEWNATRZ)


def _ma_wulgaryzm(warianty: set[str]) -> bool:
    for w in warianty:
        for wyjatek in _WYJATKI:
            w = w.replace(wyjatek, "")
        if any(rdzen in w for rdzen in _WULGARYZMY):
            return True
    return False


def _zastrzezona(warianty: set[str]) -> bool:
    return any(
        w in _ZASTRZEZONE_DOKLADNIE
        or w.startswith(_ZASTRZEZONE_PREFIKSY)
        or any(z in w for z in _ZASTRZEZONE_WEWNATRZ)
        for w in warianty
    )


def sprawdz_login(wartosc: str) -> str:
    """Zwraca login po obcięciu spacji albo rzuca ValueError z komunikatem PL."""
    v = (wartosc or "").strip()
    if not LOGIN_MIN <= len(v) <= LOGIN_MAX:
        raise ValueError(f"Login musi mieć od {LOGIN_MIN} do {LOGIN_MAX} znaków")
    if not _LOGIN_RE.match(v):
        raise ValueError("Login może zawierać litery, cyfry oraz znaki _ . - "
                         "i musi zaczynać się literą lub cyfrą")
    warianty = _warianty(v)
    if _ma_wulgaryzm(warianty):
        raise ValueError("Login zawiera niedozwolone słowo")
    if _zastrzezona(warianty):
        raise ValueError("Ta nazwa jest zastrzeżona")
    return v


def sprawdz_miesiac_urodzenia(wartosc: str, dzis: date | None = None) -> str:
    """Zwraca 'RRRR-MM' albo rzuca ValueError.

    Dnia urodzenia nie zbieramy (minimalizacja danych), więc osoba urodzona
    w tym samym miesiącu 18 lat temu mogła jeszcze nie skończyć 18 lat —
    taki wpis odrzucamy.
    """
    m = _YM_RE.match((wartosc or "").strip())
    if not m:
        raise ValueError("Podaj miesiąc i rok urodzenia")
    rok, miesiac = int(m[1]), int(m[2])
    dzis = dzis or date.today()
    if not 1 <= miesiac <= 12 or rok < _ROK_MIN or (rok, miesiac) > (dzis.year, dzis.month):
        raise ValueError("Nieprawidłowa data urodzenia")
    if (dzis.year - rok) * 12 + (dzis.month - miesiac) <= _MIESIECY_18_LAT:
        raise ValueError(KOMUNIKAT_NIEPELNOLETNI)
    return f"{rok:04d}-{miesiac:02d}"
