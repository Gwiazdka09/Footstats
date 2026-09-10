"""core/rynki_dziennika.py — rynki, które formularz dziennika oferuje ludziom.

Decyzja 2026-09-10: formularz kuponu ręcznego przestaje przyjmować dowolny tekst
typu jako jedyną drogę. `settle_manual_coupons` rozlicza nogę przez
`oblicz_tip_correct`, a ta zna konkretne zapisy — typ spoza nich („Powyżej 0.5
& Powyżej 1.5 1. połowa”, rzuty rożne, strzelec) daje None i noga zostaje
ACTIVE na zawsze. Formularz podaje więc listę stąd plus „inny — rozliczę sam”.

Lista mieszka w Pythonie, a front ją pobiera (`GET /coupon/markets`). Druga
kopia w JSX rozjechałaby się z rozliczeniem po cichu.

`czy_rozliczalny` NIE porównuje z listą, tylko pyta samo rozliczenie: typ wpisany
jako „inny”, który `oblicz_tip_correct` jednak rozumie (np. „2:1”), rozliczy się
automatycznie i nie ma sensu mówić użytkownikowi, że musi to zrobić sam.
"""
from __future__ import annotations

from typing import NamedTuple

from footstats.utils.betting import oblicz_tip_correct


class Rynek(NamedTuple):
    wartosc: str    # zapis, który trafia do nogi i który rozumie rozliczenie
    etykieta: str   # co widzi człowiek
    grupa: str      # nagłówek grupy w liście wyboru


_LINIE_MECZU = ("0.5", "1.5", "2.5", "3.5", "4.5")
_LINIE_DRUZYNY = ("0.5", "1.5", "2.5")

RYNKI: tuple[Rynek, ...] = (
    Rynek("1", "1 — wygrana gospodarza", "Wynik meczu"),
    Rynek("X", "X — remis", "Wynik meczu"),
    Rynek("2", "2 — wygrana gościa", "Wynik meczu"),
    Rynek("1X", "1X — gospodarz lub remis", "Podwójna szansa"),
    Rynek("X2", "X2 — remis lub gość", "Podwójna szansa"),
    Rynek("12", "12 — bez remisu", "Podwójna szansa"),
    *(Rynek(f"Over {l}", f"Powyżej {l} gola", "Gole w meczu") for l in _LINIE_MECZU),
    *(Rynek(f"Under {l}", f"Poniżej {l} gola", "Gole w meczu") for l in _LINIE_MECZU),
    Rynek("BTTS", "Obie strzelą — tak", "Obie drużyny strzelą"),
    Rynek("BTTS NO", "Obie strzelą — nie", "Obie drużyny strzelą"),
    *(Rynek(f"1 OVER {l}", f"Gospodarz powyżej {l} gola", "Gole drużyny")
      for l in _LINIE_DRUZYNY),
    *(Rynek(f"2 OVER {l}", f"Gość powyżej {l} gola", "Gole drużyny")
      for l in _LINIE_DRUZYNY),
)

# Wyniki próbne: remis bez goli, jednobramkowa wygrana, remis z golami, wygrana
# gościa, wysoki wynik — z połową, bo część rynków jej potrzebuje.
_WYNIKI_PROBNE = ("0-0;HT:0-0", "1-0;HT:1-0", "2-2;HT:1-1", "0-3;HT:0-2", "3-1;HT:2-0")


def czy_rozliczalny(tip: str | None) -> bool:
    """Czy automat rozliczy nogę z tym typem — pytane samo rozliczenie, nie lista."""
    if not tip or not str(tip).strip():
        return False
    return all(oblicz_tip_correct(str(tip), w) is not None for w in _WYNIKI_PROBNE)


def lista_rynkow() -> list[dict]:
    """Rynki dla frontu, w kolejności wyświetlania."""
    return [r._asdict() for r in RYNKI]
