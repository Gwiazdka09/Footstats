"""Brak członu rozróżniającego to SKRÓT nazwy, nie inny klub.

ZMIERZONE 2026-09-03. `_znajdz_wynik` (próg 0.70 na obu stronach) nie dopasował
ANI JEDNEGO z 32 zaległych kuponów, choć wyniki były w API-Football:

    Bristol Rovers vs Colchester United  ->  fixture "Bristol Rovers / Colchester"
    sim(gospodarz) = 1.00   sim(gość) = 0.00

Zero, nie 0.9. Winna reguła „ta sama baza + RÓŻNE człony = różne kluby":

    "Colchester United":  baza={colchester}  człony={united}
    "Colchester":         baza={colchester}  człony={}
    człony różne + baza równa  ->  0.0

Reguła powstała, żeby odróżnić Manchester United od Manchester City i tam działa
poprawnie — OBIE strony mają człon i te człony sobie przeczą. Ale gdy jedna strona
nie ma go WCALE, to nie jest sprzeczność, tylko krótsza pisownia tej samej drużyny.
Pusty zbiór był traktowany jak konkurencyjna wartość.

DLACZEGO NIE WOLNO ZDJĄĆ REGUŁY DO KOŃCA. Na 1063 nazwach z
`data/hist_cache/full_dataset.parquet` jest **siedem** baz, gdzie skrót naprawdę
jest dwuznaczny:

    bristol    Bristol City     vs Bristol Rovers
    dundee     Dundee           vs Dundee United
    edinburgh  FC Edinburgh     vs Edinburgh City
    guangzhou  Guangzhou FC     vs Guangzhou City
    man        Man City         vs Man United
    oxford     Oxford           vs Oxford City
    sheffield  Sheffield United vs Sheffield Weds

Pierwszy pomiar dał PIĘĆ i był błędny — grupował tokeny po surowym
`t in _ROZROZNIAJACE`, z pominięciem `_ROZ_SKROTY`, więc "Sheffield Weds" dawało
bazę "sheffield weds" zamiast "sheffield". Gdyby to poszło dalej, "Sheffield"
dopasowywałoby się do Sheffield United.

Dla tych siedmiu zostaje fail-closed: lepiej nie rozliczyć i zauważyć, niż rozliczyć
kupon wynikiem cudzego meczu. Dla pozostałych ~1056 nazw poprzednie zachowanie było
czystą stratą.
"""
from __future__ import annotations

import pytest

from footstats.utils.normalize import team_similarity

PROG_ROZLICZEN = 0.70  # `results_updater._znajdz_wynik`


# ── skrót tej samej drużyny musi się dopasować ──────────────────────────────

@pytest.mark.parametrize("pelna,skrot", [
    ("Colchester United", "Colchester"),
    ("Stoke City", "Stoke"),
    ("Cheltenham Town", "Cheltenham"),
    ("Rotherham United", "Rotherham"),
    ("Grimsby Town", "Grimsby"),
    ("Doncaster Rovers", "Doncaster"),
    ("Wycombe Wanderers", "Wycombe"),
    ("Wigan Athletic", "Wigan"),
])
def test_skrot_nazwy_dopasowuje_sie_do_pelnej(pelna, skrot):
    """To są realne pary z produkcji: kupon ma pełną nazwę, źródło skróconą."""
    assert team_similarity(pelna, skrot) >= PROG_ROZLICZEN
    assert team_similarity(skrot, pelna) >= PROG_ROZLICZEN, "reguła musi być symetryczna"


# ── ale sprzeczne człony dalej znaczą różne kluby ───────────────────────────

@pytest.mark.parametrize("a,b", [
    ("Manchester United", "Manchester City"),
    ("Sheffield United", "Sheffield Wednesday"),
    ("Bristol Rovers", "Bristol City"),
    ("Dundee United", "Dundee FC"),
])
def test_rozne_czlony_to_dalej_rozne_kluby(a, b):
    """Regresja reguły z 31.07 — bez niej wynik jednego meczu rozliczał drugi."""
    assert team_similarity(a, b) == 0.0


# ── bazy dwuznaczne: skrót NIE wystarcza ────────────────────────────────────

@pytest.mark.parametrize("pelna,skrot", [
    ("Dundee United", "Dundee"),
    ("Edinburgh City", "Edinburgh"),
    ("Guangzhou City", "Guangzhou"),
    ("Oxford City", "Oxford"),
    ("Manchester United", "Manchester"),
    ("Sheffield United", "Sheffield"),
    ("Bristol Rovers", "Bristol"),
])
def test_baza_dwuznaczna_zostaje_fail_closed(pelna, skrot):
    """Tu skrót naprawdę nie mówi, o który klub chodzi — nie zgadujemy.

    Każda z tych baz ma w danych DWA różne kluby (zmierzone na 1063 nazwach),
    więc dopasowanie po samym skrócie mogłoby rozliczyć kupon cudzym wynikiem.
    """
    assert team_similarity(pelna, skrot) < PROG_ROZLICZEN
    assert team_similarity(skrot, pelna) < PROG_ROZLICZEN


def test_lista_baz_dwuznacznych_zgadza_sie_z_danymi():
    """Ratchet: lista ma odzwierciedlać dane, nie pamięć autora.

    Jeśli dataset urośnie o kolejny taki przypadek, ten test go pokaże, zamiast
    czekać, aż kupon rozliczy się cudzym wynikiem. Bez datasetu — skip, bo
    pomiar bez danych nie jest pomiarem.
    """
    import collections
    from pathlib import Path

    sciezka = Path("data/hist_cache/full_dataset.parquet")
    if not sciezka.exists():
        pytest.skip("brak datasetu historycznego — nie ma na czym mierzyć")

    pd = pytest.importorskip("pandas")
    from footstats.utils.normalize import (
        _BAZY_WIELOZNACZNE, _czlony_rozrozniajace, _ROZ_SKROTY, _ROZROZNIAJACE,
        normalize_team_name,
    )

    df = pd.read_parquet(sciezka)
    nazwy = set(df["home"].dropna().astype(str)) | set(df["away"].dropna().astype(str))

    # Grupowanie MUSI iść przez `_czlony_rozrozniajace`, nie przez samo
    # `t in _ROZROZNIAJACE`: dataset pisze "Sheffield Weds", a `weds` jest członem
    # tożsamości dopiero po przejściu przez `_ROZ_SKROTY`. Pierwsza wersja tego
    # wyliczenia tego nie robiła i zgubiła `sheffield` oraz `bristol`.
    #
    # Oba warianty normalizacji, bo aliasy z `_DEFAULT_MAPPINGS` też skracają
    # nazwy i mogą zmienić bazę.
    warianty: dict[str, set] = collections.defaultdict(set)
    for nazwa in nazwy:
        for z_mapami in (True, False):
            tokeny = set(normalize_team_name(nazwa, use_mappings=z_mapami).split())
            czlony = frozenset(_czlony_rozrozniajace(tokeny))
            baza = " ".join(sorted(
                t for t in tokeny if _ROZ_SKROTY.get(t, t) not in _ROZROZNIAJACE
            ))
            if baza:
                warianty[baza].add(czlony)

    z_danych = {b for b, v in warianty.items() if len(v) > 1}
    nieobjete = z_danych - _BAZY_WIELOZNACZNE
    assert not nieobjete, (
        "Dataset zna bazy dwuznaczne, których nie ma w `_BAZY_WIELOZNACZNE` — "
        f"skrót takiej nazwy moze rozliczyc kupon cudzym wynikiem: {sorted(nieobjete)}"
    )


def test_sprzeczne_czlony_dzialaja_takze_dla_bazy_spoza_listy():
    """Gałąź „obie strony mają człon" musi bronić klubów, których w danych NIE MA.

    Wszystkie znane pary z konfliktem członów (man, sheffield, bristol) mają bazę
    w `_BAZY_WIELOZNACZNE`, więc łapie je DRUGA reguła. Mutacja usuwająca pierwszą
    przeżyła całą suitę — zabezpieczenie działało przez przypadek, nie przez test.

    Tu baza jest celowo spoza listy: gdy w danych pojawi się kolejne miasto z
    dwoma klubami, `_BAZY_WIELOZNACZNE` jeszcze o nim nie wie, a rozróżnienie ma
    zadziałać od pierwszego meczu — nie dopiero po dopisaniu wpisu.
    """
    assert "colchester" not in _BAZY_WIELOZNACZNE_SNAPSHOT()
    assert team_similarity("Colchester United", "Colchester City") == 0.0
    assert team_similarity("Colchester City", "Colchester United") == 0.0


def _BAZY_WIELOZNACZNE_SNAPSHOT():
    from footstats.utils.normalize import _BAZY_WIELOZNACZNE

    return _BAZY_WIELOZNACZNE
