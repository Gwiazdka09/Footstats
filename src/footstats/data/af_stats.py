"""af_stats.py — statystyki meczowe z API-Football jako OSOBNY artefakt.

DLACZEGO OSOBNY PLIK, A NIE KOLUMNY W `full_dataset.parquet`
------------------------------------------------------------
`download_all()` kończy się `df.to_parquet(out_f)` — nadpisuje dataset w całości.
Robi to co poniedziałek 04:30 UTC automat `.github/workflows/dataset_refresh.yml`,
na CZYSTYM checkoutcie runnera GitHuba, i commituje wynik przez PR. Kolumny
dopisane wprost do tamtego pliku przepadłyby przy pierwszym odświeżeniu.

Za te dane płacimy requestami ze wspólnego z produkcją limitu 7500/dobę. Trzymanie
ich w pliku, który cudza automatyka nadpisuje bez pytania, byłoby cichą utratą
pierwszej klasy — dokładnie ten kształt błędu, który ten projekt już zna.

Dlatego: `full_dataset.parquet` zostaje deterministycznym odbiciem
football-data.co.uk, `af_stats.parquet` jest ŹRÓDŁEM PRAWDY dla statystyk,
a scalenie dzieje się przy ODCZYCIE (`historical_loader.load_cached`). Żaden
zapis nie może skasować niczego, czego nie da się odtworzyć bez płacenia drugi raz.

CO JEST PROMOWANE DO RAMKI MODELU
---------------------------------
Tylko `hst`/`ast` (czyta `core/form.py` przez `WAGA_STRZALOW`; zmierzony efekt
tam, gdzie strzały są: Brier 0.6290 → 0.6180) oraz `hs`/`as_` (czyta
`core/ml_features.py`). Reszta pól z odpowiedzi API — rożne, kartki, posiadanie,
podania, faule, obrony bramkarza — nie ma w `src/` ani jednego czytelnika.

xG zostaje w PLIKU, ale NIE jest promowane. `predict_match(use_xg=True)` sięga
do cache Understata, nie do datasetu, więc kolumna xG w ramce nie miałaby dziś
czytelnika — a kolumna bez czytelnika prędzej czy później zostanie użyta bez pomiaru.

ZGODNOŚĆ POLA, zmierzona 2026-09-03 na Eredivisie (liga mająca strzały u OBU
źródeł): `Shots on Goal` z API-Football zgadza się z `HST` z football-data
w 60 z 60 meczów, i to nie w tolerancji ±1, tylko co do sztuki.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from footstats.data.historical_loader import CACHE_DIR

log = logging.getLogger(__name__)

SCIEZKA_AF_STATS = CACHE_DIR / "af_stats.parquet"

# Klucz złączenia. `date` normalizowana do doby: API-Football podaje kick-off
# ze znacznikiem godziny, football-data samą datę.
KLUCZ = ("date", "home", "away")

# Kolumny wchodzące do ramki modelu. Krótka lista jest CELOWA — patrz docstring.
KOLUMNY_PROMOWANE: tuple[str, ...] = ("hs", "as_", "hst", "ast")

KOLUMNY_PLIKU: tuple[str, ...] = (
    "date", "league", "home", "away",
    "hs", "as_", "hst", "ast",
    "xg_home", "xg_away",
    "af_fixture_id", "status", "pobrano",
)


def _pusta_ramka() -> pd.DataFrame:
    """Pusta ramka ZE SCHEMATEM — wołający filtruje po kolumnach, nie po zawartości."""
    return pd.DataFrame({k: pd.Series(dtype="object") for k in KOLUMNY_PLIKU})


def wczytaj_af_stats(sciezka: Path | None = None) -> pd.DataFrame:
    """Statystyki z dysku albo pusta ramka ze schematem, gdy pliku nie ma.

    Brak pliku to stan NORMALNY — świeży klon repozytorium, obraz zbudowany przed
    backfillem. Uszkodzony plik to co innego i musi być słyszalny: bez logu
    wyglądałby identycznie jak brak, a stracilibyśmy komplet zapłaconych danych
    nie wiedząc o tym.
    """
    sciezka = Path(sciezka or SCIEZKA_AF_STATS)
    if not sciezka.exists():
        return _pusta_ramka()
    try:
        return pd.read_parquet(sciezka)
    except (OSError, ValueError) as e:
        log.warning(
            "Nie moge odczytac %s (%s: %s) — traktuje jak BRAK statystyk AF."
            " Model wroci do samych goli w ligach, ktore strzalow nie maja"
            " u football-data.", sciezka, type(e).__name__, e,
        )
        return _pusta_ramka()


def zapisz_af_stats(df: pd.DataFrame, sciezka: Path | None = None) -> None:
    """Zapis ATOMOWY: plik tymczasowy + `os.replace`.

    Backfill zrzuca plik przyrostowo co kilkadziesiąt meczów. Ubicie procesu
    w trakcie `to_parquet` zostawiłoby pół-plik zamiast poprzedniej, dobrej
    wersji — czyli utratę tysięcy zapłaconych requestów. `os.replace` jest
    atomowe w obrębie jednego systemu plików, więc czytelnik widzi albo starą
    wersję, albo nową, nigdy połówki.
    """
    sciezka = Path(sciezka or SCIEZKA_AF_STATS)
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tmp = sciezka.with_suffix(sciezka.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, sciezka)


def _klucz_ramki(df: pd.DataFrame) -> pd.DataFrame:
    """Trzy kolumny pomocnicze klucza: data znormalizowana do doby, nazwy jako tekst."""
    return pd.DataFrame({
        "_k_date": pd.to_datetime(df["date"], errors="coerce").dt.normalize(),
        "_k_home": df["home"].astype(str),
        "_k_away": df["away"].astype(str),
    }, index=df.index)


def scal_statystyki(
    df: pd.DataFrame,
    af: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Dopełnia BRAKUJĄCE `hs/as_/hst/ast` w `df` wartościami z API-Football.

    Kontrakt, każdy punkt ma swój test:
      * liczba i KOLEJNOŚĆ wierszy bez zmian — `poisson.predict_match` czyta
        ramkę pozycyjnie (`.tail(OSTATNIE_N)`), więc porządek jest częścią umowy;
      * wartości z football-data NIGDY nie są nadpisywane, AF tylko dopełnia NaN;
      * żadnych nowych kolumn — w szczególności xG nie wchodzi do ramki modelu;
      * wejście nie jest mutowane.

    Wiersze bez ani jednej promowanej wartości (placeholder po nieudanym pobraniu)
    są odrzucane PRZED sprawdzeniem duplikatów. Inaczej ślad „tego meczu AF nie
    ma", który istnieje po to, żeby nie płacić drugi raz, blokowałby późniejszy
    prawdziwy wpis dla tej samej pary.
    """
    if df is None or df.empty:
        return df
    if af is None:
        af = wczytaj_af_stats()
    if af is None or af.empty:
        return df

    # Dopełniamy wyłącznie kolumny, które ramka JUŻ ma. Dołożenie nowej zmieniłoby
    # schemat datasetu w miejscu, którego nikt o to nie prosił.
    obecne = [k for k in KOLUMNY_PROMOWANE if k in af.columns and k in df.columns]
    if not obecne:
        return df

    prawa = af.dropna(subset=obecne, how="all")
    if prawa.empty:
        return df

    prawa = pd.concat([_klucz_ramki(prawa), prawa[obecne]], axis=1)
    prawa = prawa.dropna(subset=["_k_date", "_k_home", "_k_away"])
    if prawa.empty:
        return df

    duplikaty = prawa.duplicated(subset=["_k_date", "_k_home", "_k_away"], keep=False)
    if duplikaty.any():
        # NIE wybieramy „ostatniego" po cichu. Dwa różne komplety statystyk dla
        # jednego meczu znaczą, że dopasowanie fixture'a wpuściło cudzy mecz —
        # a wtedy każdy wybór jest zgadywaniem, którego nikt później nie wykryje.
        przyklady = (
            prawa.loc[duplikaty, ["_k_date", "_k_home", "_k_away"]]
            .drop_duplicates().head(3).to_dict("records")
        )
        raise ValueError(
            f"af_stats: {int(duplikaty.sum())} wierszy o powtorzonym kluczu"
            f" (date, home, away). Przyklady: {przyklady}."
            " To znaczy, ze dopasowanie fixture'a wpuscilo wiecej niz jeden mecz"
            " na te sama pare — nie zgaduje ktory."
        )

    prawa = prawa.rename(columns={k: f"{k}__af" for k in obecne})

    out = df.copy()
    lewa = pd.concat([out, _klucz_ramki(out)], axis=1)

    n_przed = len(lewa)
    scalone = lewa.merge(
        prawa, on=["_k_date", "_k_home", "_k_away"], how="left", validate="m:1",
    )
    if len(scalone) != n_przed:
        raise ValueError(
            f"af_stats: zlaczenie zmienilo liczbe wierszy {n_przed} -> {len(scalone)}"
        )

    for kol in obecne:
        # Konwersja PRZED `fillna`, nie po. Liga bez strzalow ma kolumne samych
        # `None`, czyli dtype `object` — `fillna` na takiej robi ciche
        # downcastowanie, ktore pandas wlasnie deprecjonuje. Po zmianie
        # zachowania kolumna zostalaby tekstem, a model czyta ja liczbowo.
        lewa = pd.to_numeric(scalone[kol], errors="coerce")
        prawa = pd.to_numeric(scalone[f"{kol}__af"], errors="coerce")
        scalone[kol] = lewa.fillna(prawa)

    scalone = scalone.drop(columns=[c for c in scalone.columns
                                    if c.endswith("__af") or c.startswith("_k_")])
    scalone.index = out.index
    return scalone


def raport_pokrycia(df: pd.DataFrame) -> dict[str, float]:
    """Ułamek wierszy z wartością, per promowana kolumna.

    Idzie do logu w `load_cached`, bo bez tej liczby „pliku nie ma w obrazie"
    wygląda dokładnie tak samo jak „ta liga po prostu nie ma strzałów". To są
    dwa różne stany i mylenie ich kosztowało już ten projekt jeden pipeline.
    """
    if df is None or df.empty:
        return {k: 0.0 for k in KOLUMNY_PROMOWANE}
    return {
        k: (float(df[k].notna().mean()) if k in df.columns else 0.0)
        for k in KOLUMNY_PROMOWANE
    }
