"""Skrót nazwy klubu nie może rozbroić reguły odróżniania klubów.

ZNALEZIONE 25.08.2026, przypadkiem — przy próbie dopisania aliasu na krótkie nazwy.
`test_normalize_kolizje.py` pilnuje par typu Manchester United / Manchester City
od 31.07, ale pilnuje ich po PEŁNYCH nazwach. Tymczasem:

    Sheffield United  vs Sheffield Wednesday  ->  0.800
    Bristol City      vs Bristol Rovers       ->  0.696

Oba POWYŻEJ progów rozliczeń (0.6 w `evening_agent.py:87`, 0.70 w `_znajdz_wynik`),
czyli wynik jednego klubu mógł rozliczyć kupon na drugi — dokładnie ten błąd,
który naprawiano 31.07, tylko wpuszczony innymi drzwiami.

MECHANIZM: `_DEFAULT_MAPPINGS` skraca nazwy do `sheffield weds` i `bristol rvs`.
Skróty `weds` i `rvs` nie były członami odróżniającymi, więc reguła „ta sama baza
+ różne człony = różne kluby" **w ogóle się nie odpalała** i o wyniku decydował
wspólny przedrostek w SequenceMatcherze. Naprawa: `wednesday` do `_ROZROZNIAJACE`,
`rvs`/`weds` do `_ROZ_SKROTY`.

Wniosek ogólny: każdy alias SKRACAJĄCY nazwę może zdjąć człon odróżniający i tym
samym wyłączyć zabezpieczenie. Dlatego druga połowa tego pliku sprawdza pary po
formach SKRÓCONYCH, nie tylko pełnych.
"""
from __future__ import annotations

import pytest

from footstats.utils.normalize import normalize_team_name, team_similarity

# Próg używany przez warstwę rozliczeń (`evening_agent.py:87`).
PROG_ROZLICZEN = 0.6


# ── kluby z tej samej miejscowości, rozróżniane przez skrót ────────────────

KLUBY_ROZNE = [
    ("Sheffield United", "Sheffield Wednesday"),
    ("Bristol City", "Bristol Rovers"),
    ("Manchester United", "Manchester City"),
    ("Nottingham Forest", "Notts County"),
    ("Bolton Wanderers", "Bristol Rovers"),
]


@pytest.mark.parametrize("a,b", KLUBY_ROZNE)
def test_rozne_kluby_nie_moga_sie_skleic(a: str, b: str):
    assert normalize_team_name(a) != normalize_team_name(b), f"{a} == {b}"
    assert team_similarity(a, b) < PROG_ROZLICZEN, (
        f"'{a}' vs '{b}' = {team_similarity(a, b):.2f} — powyżej progu rozliczeń;"
        " wynik jednego klubu może rozliczyć kupon na drugi"
    )


@pytest.mark.parametrize("a,b", [
    ("Sheffield United", "Sheffield Wednesday"),
    ("Bristol City", "Bristol Rovers"),
])
def test_skrot_nie_zdejmuje_czlonu_odrozniajacego(a: str, b: str):
    """Sedno usterki: po skróceniu nazwy człon odróżniający musi PRZETRWAĆ.

    Gdy znika, reguła rozróżniania klubów milczy i decyduje wspólny przedrostek —
    a to daje 0.7-0.8, czyli powyżej progu rozliczeń.
    """
    assert team_similarity(a, b) == pytest.approx(0.0), (
        "regula odrozniania klubow sie nie odpalila — skrot zzarl czlon tozsamosci"
    )


# ── koszt ZDJĘTY 2026-09-03, ale tylko tam, gdzie dane na to pozwalają ─────

@pytest.mark.parametrize("pelna,krotka", [
    ("Bolton Wanderers", "Bolton"),
    ("Newcastle United", "Newcastle"),
    ("Cardiff City", "Cardiff"),
    ("Ipswich Town", "Ipswich"),
])
def test_krotka_forma_jednoznacznej_bazy_laczy_sie_z_pelna(pelna: str, krotka: str):
    """Do 2026-09-03 ten test wymagał czegoś ODWROTNEGO i to było świadome.

    Stała tu wtedy nota: „to NIE jest błąd — to zapłacona cena". Cena była realna
    i policzona: `football-data.co.uk` pisze krótkimi formami, więc kupon #124
    (`Bolton Wanderers vs Preston North End`) poszedł do VOID, mimo że wynik `2-1`
    leżał w źródle od dziesięciu dni.

    Nota podawała też WARUNEK zdjęcia kosztu:

        „bez listy klubów nie da się odróżnić »Bolton« (jednoznaczne)
         od »Manchester« (dwa kluby) ani od »Sheffield« (dwa kluby).
         Zdjęcie tego kosztu wymaga JAWNEJ, PRZEJRZANEJ listy aliasów,
         a nie reguły ogólnej."

    Warunek został spełniony: `normalize._BAZY_WIELOZNACZNE` to taka lista,
    wyprowadzona z 1063 nazw w `data/hist_cache/full_dataset.parquet`, a nie
    z pamięci — i pilnowana testem, który odtwarza ją z danych
    (`test_nazwa_skrocona_nie_jest_innym_klubem.py`).

    Skala pomiaru, który to uruchomił: `_znajdz_wynik` nie dopasował ANI JEDNEGO
    z 32 zaległych kuponów. Po zmianie — 26 z 32.
    """
    assert team_similarity(pelna, krotka) >= PROG_ROZLICZEN
    assert team_similarity(krotka, pelna) >= PROG_ROZLICZEN


@pytest.mark.parametrize("pelna,krotka", [
    ("Manchester United", "Manchester"),
    ("Sheffield United", "Sheffield"),
    ("Bristol Rovers", "Bristol"),
    ("Dundee United", "Dundee"),
])
def test_krotka_forma_DWUZNACZNEJ_bazy_dalej_sie_nie_laczy(pelna: str, krotka: str):
    """Dokładnie te bazy, które nota wymieniała jako powód fail-closed.

    Tu skrót nadal nie wskazuje klubu, więc zgadywanie jest zabronione — i to jest
    ta część reguły, która ZOSTAJE. Bez tego testu poprzednia zmiana wyglądałaby
    jak zdjęcie całego zabezpieczenia.
    """
    assert team_similarity(pelna, krotka) < PROG_ROZLICZEN
    assert team_similarity(krotka, pelna) < PROG_ROZLICZEN
