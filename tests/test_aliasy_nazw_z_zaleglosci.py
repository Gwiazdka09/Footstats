"""Aliasy nazw wyprowadzone z KONKRETNYCH kuponów, które się nie rozliczyły.

Po naprawie reguły „brak członu = skrót" (2026-09-03) z 32 zaległych kuponów
dopasowało się 26. Zostało sześć, a ich analiza wobec realnych nazw u dostawcy
dała cztery przypadki, których żadna reguła ogólna nie rozstrzygnie — bo to nie
warianty pisowni, tylko INNE NAZWY tego samego klubu:

    Wolverhampton      / Wolves            (sim 0.53)  ×2 kupony
    Turun Palloseura   / Turku PS          (sim 0.58)
    Kuopion Palloseura / KuPS              (sim 0.36)
    Celta Fortuna      / Celta de Vigo II  (sim 0.00)

Piąty — `Shanghai Port` / `SHANGHAI SIPG` — dopisałem i COFNĄŁEM. To ta sama
drużyna po zmianie nazwy (2021), ale dataset historyczny trzyma obie pisownie jako
osobne drużyny, a `normalize_team_name` karmi też historię modelu (λ per drużyna),
nie tylko rozliczenia. Alias sklejał ich wiersze i złapał to
`test_zadne_dwie_rozne_druzyny_z_datasetu_sie_nie_zlewaja`. Para i tak ma 0.77,
czyli powyżej progu — alias nie naprawiał nic zmierzonego, a kosztowałby zmianę
danych wejściowych modelu.

Szóstego NIE naprawiamy i to jest świadome: kupon `Shenzhen Peng City vs Shanghai
Port` z 28.08 nie ma odpowiednika u dostawcy — tego dnia grało `Sichuan Jiuniu vs
SHANGHAI SIPG`. Inny mecz, nie inna pisownia. Alias „naprawiłby" go rozliczeniem
cudzego wyniku.

DLACZEGO W KODZIE, NIE W PLIKU JSON: `_load_mappings` bierze `_DEFAULT_MAPPINGS`
jako bazę i pozwala plikowi nadpisać. Alias dopisany tylko do pliku nie dojedzie
na maszynę, która plik już ma (`_seed_mappings_file` tworzy go wyłącznie, gdy nie
istnieje) — ten błąd jest już opisany w docstringu `_load_mappings`.
"""
from __future__ import annotations

import pytest

from footstats.utils.normalize import team_similarity

PROG_ROZLICZEN = 0.70  # `results_updater._znajdz_wynik`


@pytest.mark.parametrize("nasza,dostawcy", [
    ("Wolverhampton", "Wolves"),
    ("Turun Palloseura", "Turku PS"),
    ("Kuopion Palloseura", "KuPS"),
    ("Celta Fortuna", "Celta de Vigo II"),
    # Dopisane 03.09 rano: kupon #351 (AGF vs FC Midtjylland, 02.09) byl jedynym,
    # ktory po nocnej naprawie zostal nierozliczony z powodu NAZWY. Wynik
    # "Aarhus 0-2 FC Midtjylland" byl u dostawcy jako FT, ale sim("AGF","Aarhus")
    # = 0.22. Dataset zna tylko jedna druzyne "Aarhus", wiec alias jest jednoznaczny.
    ("AGF", "Aarhus"),
    # Kupon #180 (28.08). Wczoraj uznalem go za nierozliczalny — BLEDNIE. Dostawca
    # nazywa ten klub `Sichuan Jiuniu`, czyli nazwa SPRZED przenosin: klub przeniosl
    # sie do Shenzhen i zmienil nazwe w 2024 (zrodlo: Wikipedia, Shenzhen Peng City
    # F.C.). Pelna kolejka CSL 27-30.08 ma 8 meczow, dokladnie 16 druzyn ligi, i
    # `Sichuan Jiuniu vs SHANGHAI SIPG` JEST naszym meczem.
    ("Shenzhen Peng City", "Sichuan Jiuniu"),
])
def test_alias_laczy_nasza_nazwe_z_nazwa_dostawcy(nasza, dostawcy):
    """Pary wzięte z realnych kuponów i realnych fixture'ów, nie wymyślone."""
    assert team_similarity(nasza, dostawcy) >= PROG_ROZLICZEN
    assert team_similarity(dostawcy, nasza) >= PROG_ROZLICZEN


def test_alias_nie_skleja_klubu_z_jego_sasiadem_z_ligi():
    """Alias na Turku PS nie może wciągnąć Interu Turku — grają w tej samej lidze.

    Oba kluby są z Turku i oba grały 31.08 w Veikkausliidze, więc pomyłka tutaj
    rozliczyłaby kupon wynikiem meczu obok w tabeli.
    """
    assert team_similarity("Turun Palloseura", "Inter Turku") < PROG_ROZLICZEN
    assert team_similarity("Turku PS", "Inter Turku") < PROG_ROZLICZEN


def test_alias_celty_nie_laczy_rezerw_z_pierwsza_druzyna():
    """`Celta Fortuna` to REZERWY Celty — nie wolno ich zlać z pierwszym zespołem.

    Alias sprowadza obie pisownie do formy ze znacznikiem rezerw, więc reguła
    `ZNACZNIKI_REZERW` dalej odróżnia je od „Celta Vigo".
    """
    assert team_similarity("Celta Fortuna", "Celta Vigo") < PROG_ROZLICZEN
    assert team_similarity("Celta de Vigo II", "Celta Vigo") < PROG_ROZLICZEN


def test_wolves_nie_laczy_sie_z_rezerwami():
    """`Wolves U18` grało tego samego dnia co `Wolves` — 29.08, ta sama pula wyników."""
    assert team_similarity("Wolverhampton", "Wolves U18") < PROG_ROZLICZEN


def test_aliasy_zyja_w_kodzie_a_nie_tylko_w_pliku():
    """Regresja: alias tylko w JSON-ie jest martwy na maszynie, która plik ma.

    Opisane w docstringu `_load_mappings`. Test patrzy na `_DEFAULT_MAPPINGS`
    wprost, bo `normalize_team_name` przeszłoby także na wpisie z pliku — i wtedy
    zielony test niczego by nie gwarantował na produkcji.
    """
    from footstats.utils.normalize import _DEFAULT_MAPPINGS

    # Klucze to formy SKRÓCONE, wartości — identyfikujące. Kierunek nie jest
    # kosmetyką: "wolverhampton" -> "wolves" STWORZYŁOBY kolizję z
    # "Chattanooga Red Wolves" (0.80, ten sam dzień). Odwrotny ją usuwa.
    for klucz in ("wolves", "turku ps", "kups", "celta fortuna", "agf",
                  "sichuan jiuniu"):
        assert klucz in _DEFAULT_MAPPINGS, f"alias {klucz!r} tylko w pliku = martwy po wdrożeniu"


def test_alias_zmiany_nazwy_nie_skleja_wierszy_datasetu():
    """Czym ten alias rozni sie od cofnietego `shanghai sipg` -> `shanghai port`.

    Oba to zmiany nazwy tego samego klubu. Roznica jest w DANYCH: dataset
    historyczny zawiera OBIE pisownie Shanghai jako osobne druzyny, wiec tamten
    alias zlewal ich wiersze i zmienial lambda per druzyna. Nazwy "Sichuan" dataset
    nie zna w ogole, wiec tutaj nie ma czego sklejac.

    Test pilnuje tej przeslanki, a nie samego wyniku — gdyby dataset kiedys dostal
    wiersze "Sichuan Jiuniu", ten alias trzeba przemyslec tak samo jak tamten.
    """
    from pathlib import Path

    sciezka = Path("data/hist_cache/full_dataset.parquet")
    if not sciezka.exists():
        pytest.skip("brak datasetu historycznego")

    pd = pytest.importorskip("pandas")
    df = pd.read_parquet(sciezka)
    nazwy = set(df["home"].dropna().astype(str)) | set(df["away"].dropna().astype(str))

    assert not [x for x in nazwy if "sichuan" in x.lower()], (
        "dataset zna teraz 'Sichuan' — alias zaczal sklejac wiersze, przemysl go"
    )


def test_termalica_i_nieciecza_to_ten_sam_klub() -> None:
    """Zrodla wziely INNE czlony tej samej nazwy — podobienstwo wynosi 0.0.

    Bruk-Bet Termalica Nieciecza: football-data zapisuje "Termalica B-B.",
    API-Football "Nieciecza". Nie ma wspolnego tokenu, wiec `team_similarity`
    daje dokladnie zero i zadne dopasowanie rozmyte tego nie przeskoczy —
    to musi byc alias albo nic.

    Zmierzone na backfillu Ekstraklasy 2026-09-03: ten jeden klub odpowiadal za
    WSZYSTKIE 34 niedopasowane mecze z 659 rozwazanych.
    """
    from footstats.utils.normalize import normalize_team_name, team_similarity

    assert normalize_team_name("Nieciecza") == normalize_team_name("Termalica B-B.")
    assert team_similarity("Nieciecza", "Termalica B-B.") == 1.0


def test_alias_nieciecza_nie_ma_czego_skleic_w_datasecie() -> None:
    """Ten sam warunek, ktory przepuscil `sichuan jiuniu`, a zatrzymal `shanghai sipg`.

    Alias jest bezpieczny tylko wtedy, gdy dataset nie zna nazwy zrodlowej —
    inaczej zlewa dwa istniejace wiersze i zmienia lambda per druzyna.
    `normalize_team_name` karmi takze historie modelu, nie tylko rozliczenia.
    """
    import pandas as pd
    import pytest

    from footstats.data.historical_loader import CACHE_DIR

    plik = CACHE_DIR / "full_dataset.parquet"
    if not plik.exists():
        pytest.skip("brak full_dataset.parquet w tym srodowisku")

    df = pd.read_parquet(plik)
    druzyny = set(df["home"].astype(str)) | set(df["away"].astype(str))
    kolidujace = {t for t in druzyny if "nieciecz" in t.lower()}
    assert not kolidujace, (
        f"dataset zna juz nazwe 'Nieciecza' ({kolidujace}) — alias zlalby wiersze"
    )
