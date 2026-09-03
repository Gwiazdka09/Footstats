"""`FALLBACK_ODDS_LIMIT` ma wynikać z budżetu, nie być wpisaną piętnastką.

Stała 15 miała jawne uzasadnienie w komentarzu `dolacz_kursy`:

    "1 mecz = 2 zapytania AF (`znajdz_fixture_id` + `kursy_fixture`) przy
     dziennym limicie 100 — dlatego `limit` jest twardy"

Oba człony tego uzasadnienia są nieaktualne od 2026-09-02:

  * limit dzienny to 7500, nie 100 (plan Pro, zmierzone przez `/status`);
  * `znajdz_fixture_id` czyta `/fixtures?date=`, które jest CACHE'OWANE na poziomie
    `_get` — więc jeden request na dzień, dzielony przez wszystkie mecze. Realny
    koszt to ~1 zapytanie na mecz, nie 2.

Skutek starej wartości: przy nieczynnym Bzzoiro kursy dostawało 15 kandydatów,
a reszta wypadała z typowania, bo `system_paper.najlepszy_typ` pomija typ bez kursu.
Przy 48 kandydatach (draft 02.09) to dwie trzecie puli.

Ten test pilnuje ZWIĄZKU z budżetem, nie konkretnej liczby — żeby zmiana planu
w którąkolwiek stronę przeliczyła limit sama, zamiast zostawić martwą stałą.
"""
from __future__ import annotations

from footstats.core.cloud_draft import domyslny_limit_kursow
from footstats.utils.cache import AF_BUDGET_DAILY


def test_limit_rosnie_razem_z_budzetem():
    """Na planie Pro limit musi objąć całą dzienną pulę kandydatów."""
    assert domyslny_limit_kursow(7500) >= 100


def test_limit_nie_zjada_calego_budzetu():
    """Kursy to jedno z zadań dnia — rozliczenia i składy też potrzebują zapytań."""
    assert domyslny_limit_kursow(7500) <= 7500 // 10


def test_na_malym_budzecie_zostaje_stara_ostroznosc():
    """Plan Free (100/dzień) ma dostać dokładnie to, co miał: 15.

    Bez tego „naprawa" limitu byłaby regresją dla każdego, kto zejdzie z Pro.
    """
    assert domyslny_limit_kursow(100) == 15


def test_domyslna_wartosc_bierze_realny_budzet():
    """Wywołanie bez argumentu ma czytać `AF_BUDGET_DAILY`, nie własną liczbę."""
    assert domyslny_limit_kursow() == domyslny_limit_kursow(AF_BUDGET_DAILY)


def test_env_dalej_nadpisuje(monkeypatch):
    """Ręczne ograniczenie musi zostać możliwe — to jest wyłącznik awaryjny."""
    from footstats.core import cloud_draft

    monkeypatch.setenv("FALLBACK_ODDS_LIMIT", "3")
    assert cloud_draft.limit_kursow_z_env() == 3


def test_bez_env_uzywa_wyliczonego(monkeypatch):
    from footstats.core import cloud_draft

    monkeypatch.delenv("FALLBACK_ODDS_LIMIT", raising=False)
    assert cloud_draft.limit_kursow_z_env() == domyslny_limit_kursow()


def test_smieciowy_env_nie_wywraca_draftu(monkeypatch):
    """Literówka w zmiennej nie może ubić całego przebiegu draftu."""
    from footstats.core import cloud_draft

    monkeypatch.setenv("FALLBACK_ODDS_LIMIT", "nie-liczba")
    assert cloud_draft.limit_kursow_z_env() == domyslny_limit_kursow()
