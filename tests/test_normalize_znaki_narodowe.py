"""Litery narodowe, których NFKD nie rozkłada, muszą mieć zamiennik ASCII.

PO CO: `_strip_diacritics` opierało się na NFKD + mapie polskich liter. NFKD
rozkłada tylko znaki złożone z litery i znaku łączącego (ü → u + ¨), więc litery
BĘDĄCE osobnymi znakami — ß, ø, æ, đ, ı, þ, ð — przechodziły dalej nietknięte
i dopiero krok „wywal wszystko poza [a-z0-9 ]" zamieniał je w SPACJĘ:

    "Preußen Münster"  → "preu en munster"     (rozpada nazwę na dwa człony)
    "Bodø/Glimt"       → "bod glimt"
    "SG Sonnenhof Großaspach" → "sg sonnenhof gro aspach"

Nazwa rozbita spacją nie dopasuje się do swojego odpowiednika w datasecie, więc
mecz przepada dla λ Poissona i dla formy. Alias "bod glimt" → "bodo glimt" w
`scripts/generuj_aliasy_druzyn.py` był objawem dokładnie tego, nie osobnym
problemem — po tym fiksie obie nazwy schodzą się same.
"""
from __future__ import annotations

import pytest

from footstats.utils.normalize import _norm_ascii, normalize_team_name


@pytest.mark.parametrize(
    ("nazwa", "oczekiwane"),
    [
        ("Preußen Münster", "preussen munster"),
        ("Großaspach", "grossaspach"),
        ("Bodø/Glimt", "bodo glimt"),
        ("Tromsø", "tromso"),
        ("Brøndby", "brondby"),
        ("Æ Club", "ae club"),
        ("Bešiktaş", "besiktas"),
        ("Ümraniyespor", "umraniyespor"),
    ],
)
def test_litery_narodowe_schodza_do_ascii(nazwa, oczekiwane):
    assert normalize_team_name(nazwa, use_mappings=False) == oczekiwane


def test_zadna_litera_nie_zamienia_sie_w_spacje():
    """Sedno regresji: litera zjedzona jako spacja rozbija nazwę na człony."""
    wynik = normalize_team_name("Preußen", use_mappings=False)
    assert " " not in wynik


def test_norm_ascii_nie_kasuje_liter_bez_sladu():
    """`ascii/ignore` samo w sobie WYRZUCA ß i ø ("Preußen" → "preuen").

    Ta funkcja paruje nazwy z The Odds API z nazwami z datasetu, więc każda
    zjedzona litera to mecz bez kursów.
    """
    assert _norm_ascii("Preußen Münster") == "preussen munster"
    assert _norm_ascii("Bodø/Glimt") == "bodoglimt"


def test_wersje_z_diakrytykami_i_bez_daja_to_samo():
    """Zapis źródła i zapis datasetu muszą się schodzić bez aliasu."""
    pary = [
        ("Preußen Münster", "Preussen Munster"),
        ("Bodø/Glimt", "Bodo Glimt"),
        ("1. FC Nürnberg", "1 FC Nurnberg"),
    ]
    for a, b in pary:
        assert normalize_team_name(a, use_mappings=False) == normalize_team_name(
            b, use_mappings=False
        ), f"{a!r} != {b!r}"
