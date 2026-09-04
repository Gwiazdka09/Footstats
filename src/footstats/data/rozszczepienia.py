"""data/rozszczepienia.py — jeden klub, dwie pisownie, połowa historii.

Football-data.co.uk potrafi zmienić zapis nazwy klubu W TRAKCIE sezonu. Dataset
dostaje wtedy dwa byty: `Din. Bucuresti` (480 meczów do 2026-02-21) i
`Dinamo Bucuresti` (20 meczów od 2026-03-01).

Dlaczego to boli akurat w modelu: `form._tabela_ratingow` grupuje po SUROWYM
stringu (`dane["gospodarz"] == druzyna`), a `poisson._kanoniczne_nazwy` mapuje
nazwę z predykcji na PIERWSZĄ napotkaną pisownię (`mapa.setdefault`). Mecze
spod drugiej pisowni po prostu nie wchodzą do maski. Klub grający w tym
tygodniu liczy λ z 20 meczów zamiast z 500 — bez ostrzeżenia, bo model nie ma
jak zgłosić, że historia jest okrojona.

CZEGO TU CELOWO NIE MA: aliasu w `utils/normalize`. Tamte mapowania działają
GLOBALNIE — również w rozliczeniach i w dopasowaniu meczów u dostawców.
Sklejenie dwóch pisowni tam zmienia zachowanie settlementu, a problem jest
wyłącznie w danych treningowych. Precedens: alias `shanghai sipg → shanghai
port` został cofnięty dokładnie dlatego.

DETEKTOR JEST NARZĘDZIEM AUDYTU, NIE ŚCIEŻKĄ PRODUKCYJNĄ. Produkcja czyta jawną
listę z `data/rozszczepione_kluby.json` (wzorzec `af_league_ids.json`: wybiera
CZŁOWIEK). Detektor biega w teście i pilnuje, żeby lista nie została w tyle za
danymi — nowe rozszczepienie po odświeżeniu datasetu ma wywalić test, a nie po
cichu obniżyć λ.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SCIEZKA_MAPY = Path(__file__).parents[3] / "data" / "rozszczepione_kluby.json"

# Próg `team_similarity`. 0.80 to wartość, przy której funkcja zwraca dopasowanie
# po przedrostku tokenów — a więc łapie `Gornik Z.` vs `Gornik Zabrze`. Sam próg
# NICZEGO nie rozstrzyga: to tylko wstępne sito, po którym idą trzy testy
# falsyfikujące. Na pełnym datasecie (140k meczów) samo sito daje 57 par, z
# czego 52 to różne kluby.
PROG_PODOBIENSTWA = 0.80


def _pary_kandydujace(nazwy: list[str]) -> list[tuple[str, str]]:
    from footstats.utils.normalize import team_similarity
    return [(nazwy[i], nazwy[j])
            for i in range(len(nazwy)) for j in range(i + 1, len(nazwy))
            if team_similarity(nazwy[i], nazwy[j]) >= PROG_PODOBIENSTWA]


def wykryj_rozszczepienia(df: pd.DataFrame) -> list[dict]:
    """Pary (stara pisownia, nowa pisownia) tego samego klubu w tej samej lidze.

    Podpis przemianowania u źródła: dwie nazwy grają w TYM SAMYM sezonie i tej
    samej lidze, ale ich zakresy dat są ROZŁĄCZNE i nigdy nie zagrały ze sobą.
    Klub nie może wystąpić w jednym sezonie pod dwiema nazwami inaczej niż przez
    zmianę zapisu.

    Trzy testy falsyfikujące, każdy zabija inny fałszywy trop:
      * zagrały ze sobą        → dwa kluby (Oster vs Ostersunds);
      * zakresy dat zachodzą   → grają równolegle (Gaziantep vs Gaziantepspor);
      * brak wspólnego sezonu  → minęły się w tabeli (Barnsley vs Burnley,
        Chester vs Chesterfield — obie pary mają `team_similarity` = 0.800 i
        przechodzą dwa poprzednie testy).

    Wyjątek: różnica wyłącznie w wielkości liter (`Colon Santa FE` /
    `Colon Santa Fe`) nie wymaga wspólnego sezonu — nie ma tam czego odsiewać.

    Kanoniczna jest pisownia z PÓŹNIEJSZYMI meczami: to ją przysyłają dziś
    źródła live, więc wygrana starszej dalej gubiłaby najświeższe mecze klubu.
    """
    wymagane = {"league", "season", "date", "home", "away"}
    brak = wymagane - set(df.columns)
    if brak:
        raise ValueError(f"wykryj_rozszczepienia: brak kolumn {sorted(brak)}")

    dane = df[["league", "season", "date", "home", "away"]].copy()
    dane["date"] = pd.to_datetime(dane["date"], errors="coerce")

    dlugie = pd.concat([
        dane[["league", "season", "date", "home"]].rename(columns={"home": "t"}),
        dane[["league", "season", "date", "away"]].rename(columns={"away": "t"}),
    ])
    zakresy = dlugie.groupby(["league", "t"])["date"].agg(["min", "max"])
    sezony = dlugie.groupby(["league", "t"])["season"].apply(set)
    starcia = (set(zip(dane["league"], dane["home"], dane["away"]))
               | set(zip(dane["league"], dane["away"], dane["home"])))

    wynik: list[dict] = []
    for liga, grupa in zakresy.groupby(level=0):
        nazwy = [str(t) for (_, t) in grupa.index]
        for a, b in _pary_kandydujace(nazwy):
            if (liga, a, b) in starcia:
                continue
            a_min, a_max = zakresy.loc[(liga, a)]
            b_min, b_max = zakresy.loc[(liga, b)]
            if a_max < b_min:
                stara, nowa = a, b
            elif b_max < a_min:
                stara, nowa = b, a
            else:
                continue  # zakresy zachodzą → grają równolegle
            sam_zapis = a.casefold() == b.casefold()
            if not sam_zapis and not (sezony.loc[(liga, a)] & sezony.loc[(liga, b)]):
                continue
            wynik.append({"liga": str(liga), "stara": stara, "nowa": nowa})
    return wynik


def wczytaj_mape() -> dict[tuple[str, str], str]:
    """{(liga, stara pisownia): nowa pisownia}. Pusta, gdy pliku nie ma."""
    if not SCIEZKA_MAPY.exists():
        return {}
    surowe = json.loads(SCIEZKA_MAPY.read_text(encoding="utf-8"))
    mapa: dict[tuple[str, str], str] = {}
    for wpis in surowe.get("pary", []):
        mapa[(wpis["liga"], wpis["stara"])] = wpis["nowa"]
    return mapa


def scal_pisownie(df: pd.DataFrame, mapa: dict[tuple[str, str], str]) -> pd.DataFrame:
    """Przepisuje stare pisownie na kanoniczne. Zwraca NOWĄ ramkę.

    Liczba i kolejność wierszy bez zmian — to nie jest filtr. Klucz jest parą
    (liga, nazwa), bo ta sama nazwa w innej lidze zwykle znaczy inny klub
    (rezerwy, niższa klasa) i nie wolno jej ruszyć.
    """
    if not mapa or df.empty:
        return df
    out = df.copy()
    ligi = out["league"].astype(str)
    for kolumna in ("home", "away"):
        nazwy = out[kolumna].astype(str)
        klucze = list(zip(ligi, nazwy))
        out[kolumna] = [mapa.get(k, n) for k, n in zip(klucze, nazwy)]
    return out


def scal_z_pliku(df: pd.DataFrame) -> pd.DataFrame:
    """`scal_pisownie` z mapą z pliku + log ile wierszy realnie dotknięto."""
    mapa = wczytaj_mape()
    if not mapa:
        return df
    out = scal_pisownie(df, mapa)
    zmienione = int((out["home"] != df["home"]).sum() + (out["away"] != df["away"]).sum())
    if zmienione:
        log.info("rozszczepienia: ujednolicono %d nazw w %d parach",
                 zmienione, len(mapa))
    return out
