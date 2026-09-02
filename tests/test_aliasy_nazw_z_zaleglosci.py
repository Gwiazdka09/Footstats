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
    for klucz in ("wolves", "turku ps", "kups", "celta fortuna"):
        assert klucz in _DEFAULT_MAPPINGS, f"alias {klucz!r} tylko w pliku = martwy po wdrożeniu"
