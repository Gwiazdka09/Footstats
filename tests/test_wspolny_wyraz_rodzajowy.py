"""Wspólny wyraz RODZAJOWY nie czyni z dwóch klubów jednego.

ZNALEZIONE 2026-09-03 przy dopisywaniu aliasu na Wolverhampton. Reguła token-prefix
uznawała dopasowanie, gdy znaczące tokeny krótszej nazwy miały przedrostek
w DOWOLNYM tokenie dłuższej — także w ostatnim:

    City      vs  Manchester City         = 0.80
    United    vs  Newcastle United        = 0.80
    Turku PS  vs  Inter Turku             = 0.80
    Wolves    vs  Chattanooga Red Wolves  = 0.80

Wszystkie POWYŻEJ progu rozliczeń 0.70, a `_znajdz_wynik` bierze PIERWSZY fixture
powyżej progu, nie najlepszy. Turku PS i Inter Turku grały 31.08 w tej samej lidze;
Wolves i Chattanooga Red Wolves 29.08 — `_fetch_fixtures_by_date` wrzuca wszystkie
mecze dnia do jednej puli.

PIERWSZA PRÓBA NAPRAWY BYŁA ZŁA i warto to mieć spisane: wymagała, żeby krótsza
nazwa zaczepiała się od POCZĄTKU dłuższej. Zabiło to `Lyon` ~ `Olympique Lyonnais`
(0.80 -> 0.36) i wywaliło trzy testy `test_evening_agent.py`. Człon identyfikujący
bywa DRUGIM słowem — Olympique **Lyonnais**, Real **Madrid** — więc pozycja nie
jest tu właściwym kryterium.

Właściwym jest INFORMACYJNOŚĆ tokenu. `_ROZROZNIAJACE` to dokładnie ten zbiór
wyrazów, które nie identyfikują klubu w pojedynkę, więc nazwa złożona wyłącznie
z nich nie może dopasować się do niczego.

CZEGO TA REGUŁA NIE ŁAPIE: wspólnego tokenu, który tożsamość NIESIE, a mimo to
należy do dwóch klubów ("turku", "bristol"). Tam potrzebny jest jawny alias —
patrz `test_aliasy_nazw_z_zaleglosci.py`.
"""
from __future__ import annotations

import pytest

from footstats.utils.normalize import team_similarity

PROG_ROZLICZEN = 0.70


@pytest.mark.parametrize("krotka,dluga", [
    ("Legia", "Legia Warszawa"),
    ("Man United", "Manchester United"),
    # "Borussia" celowo NIE MA tu być: jest dwuznaczne (Dortmund vs
    # Mönchengladbach), a alias sprowadza "Borussia Dortmund" do "dortmund".
    ("Bayern", "Bayern Munchen"),
    ("Real", "Real Madrid"),
    ("Lyon", "Olympique Lyonnais"),
])
def test_legalny_skrot_dalej_pasuje(krotka, dluga):
    """To jest cel reguły i musi przetrwać — inaczej naprawa kosztuje więcej niż daje.

    `Lyon` jest tu najważniejszy: to on obalił pierwszą wersję naprawy.
    """
    assert team_similarity(krotka, dluga) >= PROG_ROZLICZEN
    assert team_similarity(dluga, krotka) >= PROG_ROZLICZEN


@pytest.mark.parametrize("a,b", [
    # Rozstrzyga sama reguła — nazwa złożona z samego wyrazu rodzajowego.
    ("City", "Manchester City"),
    ("United", "Newcastle United"),
    # Rozstrzygają ALIASY (`_DEFAULT_MAPPINGS`), bo "turku" i "wolves" niosą tu
    # tożsamość i żadna reguła ogólna ich nie rozdzieli. Zostają w tym pliku,
    # żeby ochrona była pilnowana niezależnie od tego, którym mechanizmem działa.
    ("Turku PS", "Inter Turku"),
    ("Wolves", "Chattanooga Red Wolves"),
])
def test_wspolny_wyraz_nie_laczy_roznych_klubow(a, b):
    """`_znajdz_wynik` bierze pierwszy fixture powyżej progu, więc 0.80 tutaj
    oznaczało realne ryzyko rozliczenia kuponu wynikiem cudzego meczu."""
    assert team_similarity(a, b) < PROG_ROZLICZEN
    assert team_similarity(b, a) < PROG_ROZLICZEN


def test_kolizja_z_tej_samej_ligi_i_tego_samego_dnia():
    """Najostrzejszy przypadek: oba kluby z Turku, Veikkausliiga, 31.08.2026.

    Fixture'y tego dnia: `Gnistan vs Turku PS` (1-1) i `Inter Turku vs KuPS` (1-0).
    Przy 0.80 kupon na TPS mógł dostać wynik Interu.
    """
    assert team_similarity("Turku PS", "Inter Turku") < PROG_ROZLICZEN
