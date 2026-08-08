"""Niemieckie nazwy ze źródła kursów muszą schodzić się z nazwami z datasetu.

PO CO: Bundesliga jest poligonem modelu, a jej kalendarz znamy PRZED pierwszą
kolejką — The Odds API oddaje pary drużyn już w sierpniu. Zmierzone 09.08.2026:
12 z 18 nazw Bundesligi dopasowywało się samo, a 6 nie, bo dataset skraca nazwę
("Borussia Dortmund" → "Dortmund", "1. FC Köln" → "FC Koln"). Nazwa bez
dopasowania = brak λ Poissona i brak formy, czyli mecz wypada z modelu.

Ten test pilnuje ALIASÓW (`data/team_mappings.json`), nie datasetu — nie
potrzebuje parquetu ani sieci, więc łapie regresję od razu, a nie po kolejce.
"""
from __future__ import annotations

import pytest

from footstats.utils.normalize import normalize_team_name

# (nazwa z The Odds API, nazwa w datasecie football-data.co.uk)
PARY_BUNDESLIGA = [
    ("1. FC Köln", "FC Koln"),
    ("Borussia Dortmund", "Dortmund"),
    ("Borussia Monchengladbach", "M'gladbach"),
    ("Eintracht Frankfurt", "Ein Frankfurt"),
    ("FSV Mainz 05", "Mainz"),
    ("Hamburger SV", "Hamburg"),
    # te schodziły się bez aliasu — pilnujemy, żeby aliasy ich nie zepsuły
    ("Bayern Munich", "Bayern Munich"),
    ("Bayer Leverkusen", "Leverkusen"),
    ("RB Leipzig", "RB Leipzig"),
    ("SC Freiburg", "Freiburg"),
    ("TSG Hoffenheim", "Hoffenheim"),
    ("Union Berlin", "Union Berlin"),
    ("VfB Stuttgart", "Stuttgart"),
    ("Werder Bremen", "Werder Bremen"),
    ("Augsburg", "Augsburg"),
    ("Elversberg", "Elversberg"),
    ("FC Schalke 04", "Schalke 04"),
    ("SC Paderborn", "Paderborn"),
]

PARY_ZAPLECZE = [
    ("1. FC Kaiserslautern", "Kaiserslautern"),
    ("1. FC Nürnberg", "Nurnberg"),
    ("Dynamo Dresden", "Dresden"),
    ("Eintracht Braunschweig", "Braunschweig"),
    ("Hannover 96", "Hannover"),
    ("Karlsruher SC", "Karlsruhe"),
    ("Arminia Bielefeld", "Bielefeld"),
    ("Hertha Berlin", "Hertha"),
    ("MSV Duisburg", "Duisburg"),
    ("Wehen Wiesbaden", "Wehen"),
    ("TSV 1860 München", "Munich 1860"),
    ("SC Preußen Münster", "Preußen Münster"),
    ("FC St. Pauli", "St Pauli"),
    ("Greuther Fürth", "Greuther Furth"),
    ("VfL Bochum", "Bochum"),
    ("Fortuna Düsseldorf", "Fortuna Dusseldorf"),
    ("Holstein Kiel", "Holstein Kiel"),
    ("Erzgebirge Aue", "Erzgebirge Aue"),
    ("Hansa Rostock", "Hansa Rostock"),
]


@pytest.mark.parametrize(("zrodlo", "dataset"), PARY_BUNDESLIGA + PARY_ZAPLECZE)
def test_nazwa_ze_zrodla_trafia_w_dataset(zrodlo, dataset):
    assert normalize_team_name(zrodlo) == normalize_team_name(dataset)


# Pary, które WYGLĄDAJĄ podobnie, ale to inne kluby. Zły alias tu rozliczyłby
# kupon cudzym meczem — dlatego pilnujemy ich osobno i od drugiej strony.
PARY_ROZNE_KLUBY = [
    ("FC Viktoria Köln 1904", "FC Koln"),
    ("TSG Hoffenheim II", "Hoffenheim"),
    ("Bayern Munich", "Munich 1860"),
    ("Borussia Dortmund", "Borussia Monchengladbach"),
]


@pytest.mark.parametrize(("a", "b"), PARY_ROZNE_KLUBY)
def test_rozne_kluby_nie_sklejaja_sie(a, b):
    assert normalize_team_name(a) != normalize_team_name(b)
