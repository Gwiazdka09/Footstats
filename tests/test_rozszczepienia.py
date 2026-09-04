"""Jeden klub pod dwiema pisowniami liczy λ z połowy własnej historii.

Źródło (football-data.co.uk) potrafi zmienić zapis nazwy W TRAKCIE sezonu.
Wtedy w datasecie powstają dwa byty: `Din. Bucuresti` (480 meczów do lutego
2026) i `Dinamo Bucuresti` (20 meczów od marca). `form._tabela_ratingow`
grupuje po SUROWYM stringu (`dane["gospodarz"] == druzyna`), a
`poisson._kanoniczne_nazwy` mapuje nazwę z predykcji na PIERWSZĄ napotkaną
pisownię (`setdefault`) — więc mecze pod drugą pisownią po prostu wypadają
z historii. Klub grający w tym tygodniu dostaje λ z 20 meczów zamiast z 500.

DLACZEGO NIE ALIAS W `normalize`: aliasy z `_DEFAULT_MAPPINGS` /
`team_mappings.json` działają GLOBALNIE — także w rozliczeniach i w dopasowaniu
meczów u dostawców. Sklejenie tam dwóch pisowni zmienia zachowanie settlementu,
a nie o to chodzi. Precedens: alias `shanghai sipg → shanghai port` został
cofnięty dokładnie z tego powodu (`normalize.py`, komentarz przy mapowaniach).
Tu scalamy WYŁĄCZNIE ramkę modelu, przy ładowaniu datasetu.

DLACZEGO LISTA W PLIKU, A NIE DETEKTOR PRZY KAŻDYM ŁADOWANIU: detektor jest
O(druzyny^2) na ligę i musiałby biec przy każdym `load_cached()`. Poza kosztem
— cicha, heurystyczna podmiana nazw w danych treningowych to zła własność.
Plik jest jawny i zatwierdzony przez człowieka (jak `data/af_league_ids.json`),
a detektor pilnuje go z testu: gdy odświeżenie datasetu przyniesie NOWE
rozszczepienie, test padnie zamiast po cichu obniżyć λ.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.data.rozszczepienia import (
    SCIEZKA_MAPY, scal_pisownie, wczytaj_mape, wykryj_rozszczepienia,
)


def _mecze(wiersze: list[tuple]) -> pd.DataFrame:
    """(liga, sezon, data, gospodarz, gosc) -> ramka w schemacie datasetu."""
    return pd.DataFrame(
        [{"league": l, "season": s, "date": pd.Timestamp(d), "home": h, "away": a}
         for l, s, d, h, a in wiersze]
    )


# --------------------------------------------------------------------------
# detektor: co MA znaleźć
# --------------------------------------------------------------------------

def test_zmiana_pisowni_w_srodku_sezonu_jest_wykryta():
    """Podpis przemianowania: ten sam sezon, rozłączne daty, luka rzędu kolejki."""
    df = _mecze([
        ("ROU", "2025/2026", "2026-02-01", "Din. Bucuresti", "Rapid"),
        ("ROU", "2025/2026", "2026-02-21", "Cluj", "Din. Bucuresti"),
        ("ROU", "2025/2026", "2026-03-01", "Dinamo Bucuresti", "Rapid"),
        ("ROU", "2025/2026", "2026-03-08", "Cluj", "Dinamo Bucuresti"),
    ])
    znalezione = wykryj_rozszczepienia(df)
    assert len(znalezione) == 1
    p = znalezione[0]
    assert (p["liga"], p["stara"], p["nowa"]) == ("ROU", "Din. Bucuresti", "Dinamo Bucuresti")


def test_kanoniczna_jest_pisownia_NOWSZA():
    """Live'owe źródła przysyłają dziś nową nazwę — to ona musi wygrać.

    Gdyby wygrywała starsza, `_kanoniczne_nazwy` dalej gubiłby NAJŚWIEŻSZE
    mecze klubu, czyli te najbardziej istotne dla predykcji na jutro.
    """
    df = _mecze([
        ("NOR", "2023", "2023-08-01", "Ham-Kam", "Bodo"),
        ("NOR", "2023", "2023-09-03", "Bodo", "Ham-Kam"),
        ("NOR", "2023", "2023-09-17", "HamKam", "Bodo"),
        ("NOR", "2023", "2023-10-01", "Bodo", "HamKam"),
    ])
    p = wykryj_rozszczepienia(df)[0]
    assert p["nowa"] == "HamKam", "kanoniczna ma być pisownia z późniejszymi meczami"


def test_roznica_tylko_w_wielkosci_liter_wystarczy_bez_wspolnego_sezonu():
    """`Colon Santa FE` i `Colon Santa Fe` to ten sam klub bez dalszych dowodów.

    Reguła wspólnego sezonu jest po to, żeby odsiać RÓŻNE kluby o podobnych
    nazwach. Przy różnicy wyłącznie w wielkości liter nie ma czego odsiewać —
    i bez tego wyjątku para z ARG-Copa (sezony 2022 i 2023) przepadłaby.
    """
    df = _mecze([
        ("ARG", "2022", "2022-05-01", "Colon Santa FE", "Boca"),
        ("ARG", "2023", "2023-08-01", "Colon Santa Fe", "Boca"),
    ])
    znalezione = wykryj_rozszczepienia(df)
    assert len(znalezione) == 1
    assert znalezione[0]["nowa"] == "Colon Santa Fe"


# --------------------------------------------------------------------------
# detektor: czego NIE MA znaleźć — to jest ważniejsza połowa
# --------------------------------------------------------------------------

def test_kluby_ktore_ze_soba_graly_nie_sa_scalane():
    """Najostrzejszy dowód odrębności: zagrały mecz przeciwko sobie."""
    df = _mecze([
        ("SWE", "2020", "2020-04-01", "Oster", "Ostersunds"),
        ("SWE", "2020", "2020-08-01", "Ostersunds", "Oster"),
    ])
    assert wykryj_rozszczepienia(df) == []


def test_zachodzace_zakresy_dat_nie_sa_scalane():
    """Dwie nazwy grające równolegle to dwa kluby, choćby nazwy były bliskie."""
    df = _mecze([
        ("TUR", "2019/2020", "2019-09-01", "Gaziantep", "Fener"),
        ("TUR", "2019/2020", "2019-10-01", "Gaziantepspor", "Besiktas"),
        ("TUR", "2019/2020", "2019-11-01", "Fener", "Gaziantep"),
    ])
    assert wykryj_rozszczepienia(df) == []


def test_brak_wspolnego_sezonu_nie_wystarcza():
    """Barnsley i Burnley: `team_similarity` = 0.800, rozłączne w czasie, nigdy razem.

    To jest dokładnie ten fałszywy trop, na którym łamie się słabsza reguła
    „rozłączne w czasie + nigdy ze sobą nie grały" — w niższych ligach kluby
    normalnie wchodzą i wychodzą, nie stykając się latami.
    """
    df = _mecze([
        ("ENG", "2021/2022", "2022-05-01", "Barnsley", "Hull"),
        ("ENG", "2022/2023", "2022-07-30", "Burnley", "Hull"),
    ])
    assert wykryj_rozszczepienia(df) == []


def test_rozne_ligi_nie_sa_scalane():
    """Ta sama nazwa w dwóch ligach to zwykle dwa różne kluby (rezerwy, niższa klasa)."""
    df = _mecze([
        ("ENG-A", "2023", "2023-02-01", "Din. Bucuresti", "X"),
        ("ENG-B", "2023", "2023-05-01", "Dinamo Bucuresti", "Y"),
    ])
    assert wykryj_rozszczepienia(df) == []


# --------------------------------------------------------------------------
# scalanie
# --------------------------------------------------------------------------

def test_scal_pisownie_przepisuje_obie_kolumny():
    df = _mecze([
        ("POL", "2022/2023", "2023-03-01", "Gornik Z.", "Legia"),
        ("POL", "2022/2023", "2023-04-01", "Legia", "Gornik Z."),
    ])
    out = scal_pisownie(df, {("POL", "Gornik Z."): "Gornik Zabrze"})
    assert list(out["home"]) == ["Gornik Zabrze", "Legia"]
    assert list(out["away"]) == ["Legia", "Gornik Zabrze"]


def test_scal_pisownie_nie_gubi_ani_nie_dodaje_wierszy():
    df = _mecze([("POL", "S", "2023-03-01", f"K{i}", f"K{i+1}") for i in range(20)])
    out = scal_pisownie(df, {("POL", "K3"): "K3 nowy"})
    assert len(out) == len(df)
    assert list(out.index) == list(df.index)


def test_scal_pisownie_nie_mutuje_wejscia():
    df = _mecze([("POL", "S", "2023-03-01", "Gornik Z.", "Legia")])
    scal_pisownie(df, {("POL", "Gornik Z."): "Gornik Zabrze"})
    assert df.loc[0, "home"] == "Gornik Z.", "wejscie zostalo zmutowane"


def test_scal_pisownie_dziala_tylko_we_wskazanej_lidze():
    """Klucz mapy jest parą (liga, nazwa) — ta sama nazwa gdzie indziej zostaje."""
    df = _mecze([
        ("POL", "S", "2023-03-01", "Gornik Z.", "Legia"),
        ("CZE", "S", "2023-03-01", "Gornik Z.", "Sparta"),
    ])
    out = scal_pisownie(df, {("POL", "Gornik Z."): "Gornik Zabrze"})
    assert list(out["home"]) == ["Gornik Zabrze", "Gornik Z."]


def test_pusta_mapa_zwraca_te_same_dane():
    df = _mecze([("POL", "S", "2023-03-01", "A", "B")])
    pd.testing.assert_frame_equal(scal_pisownie(df, {}), df)


# --------------------------------------------------------------------------
# zapadka na prawdziwym datasecie
# --------------------------------------------------------------------------

def test_plik_mapy_pokrywa_wszystko_co_detektor_widzi_w_datasecie():
    """Odświeżenie datasetu może przynieść NOWE rozszczepienie.

    Bez tej zapadki nowa zmiana pisowni u źródła obniżyłaby λ jakiegoś klubu
    po cichu — dokładnie tak, jak zrobiło to `Dinamo Bucuresti`, i nikt by się
    nie dowiedział, bo model nie ma jak zgłosić, że liczy z 20 meczów zamiast
    z 500. Test czyta parquet BEZ scalania (`z_af=False`, przed podmianą),
    żeby detektor widział surowy stan źródła.
    """
    pytest.importorskip("pyarrow")
    from footstats.data.historical_loader import sciezka_pelnego
    if not sciezka_pelnego().exists():
        pytest.skip("brak full_dataset.parquet")

    df = pd.read_parquet(sciezka_pelnego(),
                         columns=["league", "season", "date", "home", "away"])
    mapa = wczytaj_mape()
    brakujace = [p for p in wykryj_rozszczepienia(df)
                 if (p["liga"], p["stara"]) not in mapa]
    assert not brakujace, (
        f"Detektor widzi rozszczepienia spoza {SCIEZKA_MAPY.name}: {brakujace}\n"
        "Kazda pare obejrzyj RECZNIE (detektor odsiewa falszywe tropy, ale nie "
        "zna klubow) i dopisz do pliku albo uzasadnij odrzucenie."
    )


def test_kazdy_wpis_mapy_ma_pokrycie_w_datasecie():
    """Wpis, ktorego juz nie ma w danych, to martwa regula udajaca zywa."""
    pytest.importorskip("pyarrow")
    from footstats.data.historical_loader import sciezka_pelnego
    if not sciezka_pelnego().exists():
        pytest.skip("brak full_dataset.parquet")

    df = pd.read_parquet(sciezka_pelnego(), columns=["league", "home", "away"])
    obecne = set(zip(df["league"], df["home"])) | set(zip(df["league"], df["away"]))
    martwe = [k for k in wczytaj_mape() if k not in obecne]
    assert not martwe, f"wpisy bez pokrycia w datasecie: {martwe}"


def test_load_cached_scala_pisownie():
    """Bez wpiecia w `load_cached` caly modul jest martwym kodem."""
    pytest.importorskip("pyarrow")
    from footstats.data.historical_loader import load_cached, sciezka_pelnego
    if not sciezka_pelnego().exists():
        pytest.skip("brak full_dataset.parquet")

    mapa = wczytaj_mape()
    if not mapa:
        pytest.skip("mapa pusta")

    df = load_cached(z_af=False)
    nazwy = set(df["home"]) | set(df["away"])
    zostaly = [stara for (_, stara) in mapa if stara in nazwy]
    assert not zostaly, f"stare pisownie przezyly load_cached: {zostaly}"


# --------------------------------------------------------------------------
# dostarczenie do obrazów — bez pliku scalanie jest cichym no-opem
# --------------------------------------------------------------------------

@pytest.mark.parametrize("plik,wzorzec", [
    (".gitignore", "!/data/rozszczepione_kluby.json"),
    (".dockerignore", "!data/rozszczepione_kluby.json"),
    (".gcloudignore", "!/data/rozszczepione_kluby.json"),
    ("Dockerfile.api", "COPY data/rozszczepione_kluby.json"),
    ("Dockerfile.jobs", "COPY data/rozszczepione_kluby.json"),
])
def test_mapa_dojezdza_do_obrazow(plik: str, wzorzec: str) -> None:
    """`/data/*` wycina katalog — każda z pięciu bramek potrafi zjeść plik osobno.

    Bez pliku w obrazie `wczytaj_mape()` zwraca pustą mapę, `scal_z_pliku`
    oddaje ramkę bez zmian i produkcja wraca do liczenia λ z połowy historii —
    bez jednego wyjątku i bez linijki w logu. Lokalnie wszystko liczy się
    dobrze, bo plik leży na dysku.
    """
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[1]
    assert wzorzec in (root / plik).read_text(encoding="utf-8")


def test_plik_jest_sledzony_przez_gita() -> None:
    """Negacja w `.gitignore` nic nie da, jeśli nikt pliku nie dodał."""
    import subprocess
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[1]
    wynik = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "data/rozszczepione_kluby.json"],
        cwd=root, capture_output=True, text=True,
    )
    assert wynik.returncode == 0, "git add -f data/rozszczepione_kluby.json"


def test_sciezka_datasetu_jest_pozno_wiazana() -> None:
    """`sciezka_pelnego()` musi czytać BIEŻĄCE `CACHE_DIR`, nie to z importu.

    Testy przekierowują dataset przez `monkeypatch.setattr(hl, "CACHE_DIR",
    tmp_path)`. Gdy ścieżka jest stałą policzoną przy imporcie, podmiana nie
    działa i testy zaczynają czytać ORAZ NADPISYWAĆ produkcyjny
    `full_dataset.parquet` — pozostając zielone. Zdarzyło się to 2026-09-04
    przy wyciąganiu literału do stałej: `download_all` w teście podmienił
    prawdziwy zbiór (140 148 meczów) atrapą na 100 wierszy.
    """
    import footstats.data.historical_loader as hl
    from pathlib import Path as _P

    oryginal = hl.CACHE_DIR
    try:
        hl.CACHE_DIR = _P("nieistniejacy_katalog_testowy")
        assert hl.sciezka_pelnego().parent.name == "nieistniejacy_katalog_testowy"
    finally:
        hl.CACHE_DIR = oryginal
    assert hl.sciezka_pelnego() == oryginal / hl.NAZWA_PELNEGO
