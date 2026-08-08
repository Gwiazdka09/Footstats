"""Generowanie aliasów nazw drużyn — reguła wyboru, bez sieci i bazy.

PO CO: źródło predykcji i nasz dataset piszą nazwy inaczej ("Club Brugge KV"
vs "Club Brugge", "Wolverhampton" vs "Wolves", "Wisła Kraków" vs "Wisla").
Zmierzone 08.08 na 14 realnych kandydatach: tylko 4 dały się połączyć
z własnymi danymi, mimo że dataset pokrywa ich ligi. Bez połączenia nie ma
ani λ Poissona, ani formy liczonej z historii.

DLACZEGO NIE ZWYKŁE DOPASOWANIE ROZMYTE: `team_similarity` daje 0.800 zarówno
dla ("Wisła Kraków", "Wisla") jak i ("Wisła Płock", "Wisla") — sam próg nie
rozdzieli dwóch klubów. Reguła jest więc dwustopniowa:

  1. dokładne dopasowanie po normalizacji wygrywa zawsze i kończy sprawę
     (dlatego "Wisła Płock" trafia na "Wisla Plock", zanim cokolwiek zgaduje);
  2. rozmyte tylko gdy zwycięzca jest JEDEN i przewyższa drugiego o margines.

Alias trafia do `data/team_mappings.json`, którego używa `normalize_team_name`
w całym projekcie — także przy rozliczaniu kuponów. Zły wpis rozliczyłby kupon
cudzym meczem, więc reguła jest celowo zachowawcza: brak aliasu jest tańszy
niż alias błędny.
"""
from __future__ import annotations

import pytest

from scripts.generuj_aliasy_druzyn import (
    MARGINES,
    PROG,
    dopasuj_nazwe,
    zbuduj_aliasy,
)


@pytest.fixture(autouse=True)
def bez_zapisanych_aliasow(monkeypatch):
    """Testy liczą regułę, nie zawartość `data/team_mappings.json`.

    Bez tego generator widzi własne poprzednie wyniki: po dopisaniu aliasu
    "club brugge kv" -> "club brugge" ta sama para wychodzi już jako
    dopasowanie DOKŁADNE, więc test reguły rozmytej przestaje ją widzieć.
    """
    from footstats.utils import normalize

    monkeypatch.setattr(normalize, "_load_mappings", dict)

# Fragment realnych nazw z datasetu (po normalizacji robi to sam generator).
DATASET = [
    "Wisla", "Wisla Plock", "Club Brugge", "Kortrijk", "Wolves",
    "Gornik Zabrze", "Radomiak Radom", "Cambuur", "Excelsior",
]


# ── pojedyncze dopasowanie ─────────────────────────────────────────────────

def test_dokladne_dopasowanie_po_normalizacji() -> None:
    trafienie, powod = dopasuj_nazwe("Górnik Zabrze", DATASET)
    assert trafienie == "Gornik Zabrze"
    assert powod == "dokladne"


def test_sufiks_klubowy_dopasowany_rozmycie() -> None:
    trafienie, powod = dopasuj_nazwe("Club Brugge KV", DATASET)
    assert trafienie == "Club Brugge"
    assert powod == "rozmyte"


def test_prefiks_klubowy_dopasowany() -> None:
    assert dopasuj_nazwe("KV Kortrijk", DATASET)[0] == "Kortrijk"


def test_dwa_kluby_o_wspolnym_rdzeniu_rozdzielone() -> None:
    """Płock ma swoje dokładne dopasowanie i nie kradnie Wisły.

    Gdyby oba szły przez rozmyte, oba trafiłyby na to samo (0.800 do "Wisla").
    Kraków różni się nazwą miasta, nie członem prawnym, więc automat go NIE
    aliasuje — trafia do przeglądu, bo ta sama różnica raz znaczy skrót nazwy,
    a raz zupełnie inny klub ("Gremio Novorizontino" vs "Gremio").
    """
    assert dopasuj_nazwe("Wisła Płock", DATASET)[0] == "Wisla Plock"
    assert dopasuj_nazwe("Wisła Kraków", DATASET) == (None, "rdzen")


def test_odrzucone_trafiaja_do_przegladu() -> None:
    """Nic nie ginie po cichu — niejednoznaczne pary ma zobaczyć człowiek."""
    from scripts.generuj_aliasy_druzyn import propozycje_do_przegladu

    pary = propozycje_do_przegladu(["Wisła Kraków"], DATASET)
    assert pary == [("Wisła Kraków", "Wisla")]


def test_brak_dopasowania_gdy_nic_nie_przekracza_progu() -> None:
    trafienie, powod = dopasuj_nazwe("Shanghai Shenhua", DATASET)
    assert trafienie is None and powod == "brak"


def test_remis_nie_daje_aliasu() -> None:
    """Dwa równie dobre dopasowania = nie wiadomo które; alias byłby zgadywaniem."""
    trafienie, powod = dopasuj_nazwe("Wisla", ["Wisla Gora", "Wisla Dol"])
    assert trafienie is None and powod in ("remis", "brak")


def test_zbyt_maly_margines_nie_daje_aliasu() -> None:
    kandydaci = ["Sporting Lisbon", "Sporting Lisboa"]
    trafienie, _ = dopasuj_nazwe("Sporting Lisbo", kandydaci)
    assert trafienie is None, "przy dwoch niemal identycznych nie wolno wybierac"


def test_nazwa_identyczna_nie_potrzebuje_aliasu() -> None:
    trafienie, powod = dopasuj_nazwe("Excelsior", DATASET)
    assert trafienie == "Excelsior" and powod == "dokladne"


def test_pusta_nazwa() -> None:
    assert dopasuj_nazwe("", DATASET) == (None, "brak")


def test_pusty_dataset() -> None:
    assert dopasuj_nazwe("Legia", []) == (None, "brak")


# ── budowa mapy ────────────────────────────────────────────────────────────

def test_dokladne_trafienia_nie_trafiaja_do_mapy() -> None:
    """Alias dla nazwy, która i tak się dopasowuje, to zbędny wpis do utrzymania."""
    mapa, raport = zbuduj_aliasy(["Excelsior", "Górnik Zabrze"], DATASET)
    assert mapa == {}
    assert raport["dokladne"] == 2


def test_rozmyte_trafienia_trafiaja_do_mapy() -> None:
    mapa, raport = zbuduj_aliasy(["Club Brugge KV"], DATASET)
    assert mapa and raport["rozmyte"] == 1
    # klucz i wartość są znormalizowane — tego oczekuje normalize_team_name
    assert list(mapa.values()) == ["club brugge"]


def test_nietrafione_sa_policzone_a_nie_zgadywane() -> None:
    mapa, raport = zbuduj_aliasy(["Shanghai Shenhua", "Levski Sofia"], DATASET)
    assert mapa == {}
    assert raport["brak"] == 2


def test_dwie_rozne_nazwy_nie_moga_wskazac_tej_samej_druzyny() -> None:
    """Zabezpieczenie przed sklejeniem dwóch klubów w jeden.

    Gdyby "Wisła Kraków" i "Wisła Płock" trafiły oba na "Wisla", rozliczenia
    myliłyby ich mecze. Generator ma wtedy odrzucić OBA, nie wybierać.
    """
    mapa, _ = zbuduj_aliasy(["Wisła Kraków", "Wisła Płock"], ["Wisla"])
    assert len(set(mapa.values())) == len(mapa), "dwie nazwy wskazuja ten sam klub"


def test_powtorzona_nazwa_daje_jeden_wpis() -> None:
    mapa, _ = zbuduj_aliasy(["Club Brugge KV", "Club Brugge KV"], DATASET)
    assert len(mapa) == 1


# ── realne bledne propozycje z podgladu 08.08 ──────────────────────────────
#
# Sam prog 0.80 z marginesem proponowal ponizsze. Krotka nazwa w datasecie
# przyciaga dowolna dluzsza o wspolnym rdzeniu, wiec doszedl warunek: tokeny
# roznicujace musza byc WYLACZNIE czlonami prawnymi klubu.

@pytest.mark.parametrize(("zrodlo", "dataset_nazwa"), [
    ("Wynnum Wolves", "Wolves"),                 # Queensland vs Wolverhampton
    ("Moreton City Excelsior", "Excelsior"),     # Australia vs Holandia
    ("Gremio Novorizontino", "Gremio"),          # dwa rozne kluby BRA
    ("Botafogo SP", "Botafogo RJ"),              # dwa rozne kluby BRA
    ("Algeria", "Almeria"),                      # reprezentacja vs klub
    ("Peru", "Perugia"),
    ("England", "New England Revolution"),
])
def test_rozne_kluby_nie_dostaja_aliasu(zrodlo: str, dataset_nazwa: str) -> None:
    trafienie, powod = dopasuj_nazwe(zrodlo, [dataset_nazwa])
    assert trafienie is None, f"{zrodlo!r} sklejone z {dataset_nazwa!r} (powod={powod})"


@pytest.mark.parametrize(("zrodlo", "dataset_nazwa"), [
    ("Club Brugge KV", "Club Brugge"),
    ("KV Kortrijk", "Kortrijk"),
    ("IF Gnistan", "Gnistan"),
    ("Viborg FF", "Viborg"),
    ("Örgryte IS", "Orgryte"),
    ("Portimonense SAD", "Portimonense"),
])
def test_czlon_prawny_nadal_dopasowany(zrodlo: str, dataset_nazwa: str) -> None:
    """Różnica o sam człon prawny to ten sam klub — tego nie wolno zgubić."""
    assert dopasuj_nazwe(zrodlo, [dataset_nazwa])[0] == dataset_nazwa


def test_sam_czlon_prawny_nie_jest_wspolnym_rdzeniem() -> None:
    """"FC Barcelona" i "FC Porto" dziela tylko "fc" — to nie ten sam klub."""
    assert dopasuj_nazwe("FC Barcelona", ["FC Porto"])[0] is None


# ── lista przejrzana recznie ───────────────────────────────────────────────

def test_reczne_aliasy_nie_zawieraja_odrzuconych_par() -> None:
    """Pary świadomie odrzucone przy przeglądzie 08.08 nie mogą wrócić tylnymi drzwiami."""
    from scripts.generuj_aliasy_druzyn import ALIASY_RECZNE

    zakazane = {
        "algeria": "almeria",
        "peru": "perugia",
        "england": "new england revolution",
        "botafogo sp": "botafogo rj",
        "gremio novorizontino": "gremio",
        "wynnum wolves": "wolves",
        "moreton city excelsior": "excelsior",
        "union sportive yacoub el mansour": "le mans",
        "san diego wave": "san diego fc",
    }
    trafienia = [k for k, v in zakazane.items() if ALIASY_RECZNE.get(k) == v]
    assert not trafienia, f"odrzucone pary wrocily do listy recznej: {trafienia}"


def test_zaden_reczny_alias_nie_wskazuje_dc_united() -> None:
    """"DC United" przyciągało KAŻDY klub z członem "United" — artefakt, nie podobieństwo."""
    from scripts.generuj_aliasy_druzyn import ALIASY_RECZNE

    assert "dc united" not in set(ALIASY_RECZNE.values())


def test_reczne_aliasy_sa_znormalizowane() -> None:
    """Klucz i wartość muszą być w formie, jaką zwraca `normalize_team_name`."""
    from footstats.utils.normalize import normalize_team_name
    from scripts.generuj_aliasy_druzyn import ALIASY_RECZNE

    zle = [
        f"{k} -> {v}"
        for k, v in ALIASY_RECZNE.items()
        if normalize_team_name(k) != k
    ]
    assert not zle, f"klucze nie sa znormalizowane: {zle}"


def test_reczny_alias_nie_wskazuje_sam_na_siebie() -> None:
    from scripts.generuj_aliasy_druzyn import ALIASY_RECZNE

    assert not [k for k, v in ALIASY_RECZNE.items() if k == v]


def test_reczne_aliasy_sa_iniektywne() -> None:
    """Dwie różne nazwy na jeden cel sklejałyby dwa kluby w jeden."""
    from scripts.generuj_aliasy_druzyn import ALIASY_RECZNE

    cele = list(ALIASY_RECZNE.values())
    assert len(set(cele)) == len(cele), "dwa aliasy wskazuja ten sam klub"


def test_progi_sa_zachowawcze() -> None:
    """Świadomy wybór, nie przypadek — luźniejsze progi psują rozliczenia."""
    assert PROG >= 0.80
    assert MARGINES >= 0.10


def test_pusta_lista_zrodel() -> None:
    mapa, raport = zbuduj_aliasy([], DATASET)
    assert mapa == {} and sum(raport.values()) == 0


@pytest.mark.parametrize("nazwa", ["Wisła Kraków", "Club Brugge KV", "KV Kortrijk"])
def test_wynik_jest_powtarzalny(nazwa: str) -> None:
    assert dopasuj_nazwe(nazwa, DATASET) == dopasuj_nazwe(nazwa, DATASET)
