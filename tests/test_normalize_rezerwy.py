"""test_normalize_rezerwy.py — drużyny rezerw i młodzieżowe to NIE pierwszy zespół.

PO CO: `team_similarity` daje 0.80 parze ("Legia", "Legia II"), bo reguła
token-prefix widzi tam legalny skrót nazwy — tak samo jak w parze
("Legia Warszawa", "Legia"). Progi w produkcji są niżej: 0.70 w `_znajdz_wynik`
(rozliczenia), 0.6 w `evening_agent`. Rezerwy przechodziły więc jako pierwszy
zespół.

Skutek: kupon na Legię mógł zostać rozliczony wynikiem Legii II — a rezerwy
często grają w ten sam weekend, więc obie drużyny bywają w tej samej puli
wyników. To trzeci przypadek tej samej rodziny błędów, po Manchester
United/City i po surowym SequenceMatcher w `_znajdz_wynik_fdb`.

Samo podobieństwo nazw tego nie rozstrzygnie — "Legia II" jest tak samo bliskie
"Legii" jak "Legia Warszawa". Potrzebny osobny znacznik: rezerwy mają w nazwie
człon, którego pierwszy zespół nie ma.

Zasada fail-closed: przy wątpliwości wolimy nie rozliczyć i to zauważyć, niż
rozliczyć kupon wynikiem cudzego meczu.
"""
from __future__ import annotations

import pytest

from footstats.utils.normalize import team_similarity

# Progi używane w produkcji — testy mają pilnować ich, nie abstrakcyjnego 0.0.
PROG_ZNAJDZ_WYNIK = 0.70
PROG_EVENING = 0.6


REZERWY = [
    ("Legia", "Legia II"),
    ("Bayern Monachium", "Bayern Monachium II"),
    ("Athletic Bilbao", "Athletic Bilbao B"),
    ("Barcelona", "Barcelona B"),
    ("Real Madryt", "Real Madryt Castilla"),
    ("Ajax", "Jong Ajax"),
    ("PSV", "Jong PSV"),
    ("Borussia Dortmund", "Borussia Dortmund U19"),
    ("Chelsea", "Chelsea U21"),
    ("Benfica", "Benfica U23"),
]

# ŚWIADOMIE POMINIĘTE: "Sevilla" vs "Sevilla Atletico". Znacznik `atletico`
# rozdzieliłby też "Club Atletico Boca Juniors" od "Boca Juniors" — pierwszy
# zespół od samego siebie. Blast radius fałszywego negatywu większy niż zysk,
# więc ten wariant zostaje na aliasach w team_mappings.json.


@pytest.mark.parametrize("pierwszy,rezerwy", REZERWY)
def test_rezerwy_to_inna_druzyna(pierwszy, rezerwy):
    assert team_similarity(pierwszy, rezerwy) == 0.0, (
        f"{rezerwy!r} uznane za {pierwszy!r} — rozliczenie wynikiem cudzego meczu"
    )


@pytest.mark.parametrize("pierwszy,rezerwy", REZERWY)
def test_rezerwy_ponizej_progu_rozliczen(pierwszy, rezerwy):
    """Nawet gdyby wynik nie był zerem, musi zostać pod progami produkcyjnymi."""
    assert team_similarity(pierwszy, rezerwy) < PROG_EVENING
    assert team_similarity(rezerwy, pierwszy) < PROG_ZNAJDZ_WYNIK


def test_porownanie_jest_symetryczne():
    assert team_similarity("Legia", "Legia II") == team_similarity("Legia II", "Legia")


def test_dwie_rozne_rezerwy_tego_samego_klubu():
    """Legia II i Legia III to osobne zespoły, nie ten sam."""
    assert team_similarity("Legia II", "Legia III") == 0.0


def test_te_same_rezerwy_pasuja_do_siebie():
    """Reguła ma odróżniać poziomy, nie blokować rezerw w ogóle."""
    assert team_similarity("Legia II", "Legia II") == 1.0
    assert team_similarity("FC Bayern Monachium II", "Bayern Monachium II") == 1.0


# ── nie wolno zepsuć legalnych dopasowań ────────────────────────────────────

LEGALNE = [
    ("Legia Warszawa", "Legia"),
    ("Man Utd", "Manchester United"),
    ("Paris Saint-Germain", "PSG"),
    ("FC Bayern Monachium", "Bayern Monachium"),
    ("KS Lechia Gdańsk", "Lechia Gdansk"),
]


@pytest.mark.parametrize("a,b", LEGALNE)
def test_legalne_warianty_nadal_pasuja(a, b):
    assert team_similarity(a, b) >= PROG_ZNAJDZ_WYNIK, f"{a!r} ~ {b!r} przestało pasować"


def test_klub_z_litera_b_w_srodku_nazwy_nie_jest_rezerwa():
    """Znacznik rezerw to osobny człon na końcu, nie dowolne 'b' w nazwie."""
    assert team_similarity("Hertha BSC", "Hertha BSC") == 1.0
    assert team_similarity("Bayer Leverkusen", "Bayer Leverkusen") == 1.0
