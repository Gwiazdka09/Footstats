"""Kolumna CLV musi powstawać migracją, nie oportunistycznym ALTER-em.

PO CO: `clv_tracker._ensure_clv_column` robi `ALTER TABLE predictions ADD COLUMN
clv_closing_odds REAL` w `try/except Exception: pass`. Ten except połyka
WSZYSTKO — nie tylko "kolumna już istnieje", ale też brak uprawnień, literówkę
i każdy inny błąd. Sprawdzone na produkcji 09.08.2026:

    psycopg2.errors.UndefinedColumn: column "clv_closing_odds" does not exist

Kolumny nie ma, więc `record_closing_odds` nie ma gdzie pisać, a `get_clv_report`
nie ma czego czytać — CLV nie działa od momentu powstania i nikt się nie
dowiedział. To czwarta awaria tej samej rodziny tego dnia: cichy `except`
zamienia awarię w „brak danych".

CLV jest jedyną miarą przewagi odporną na szczęście: mówi, czy nasz kurs bije
zamknięcie rynku, i daje odpowiedź w tygodnie zamiast po setkach rozliczeń.
Dlatego kolumna należy do migracji — jedynego mechanizmu, który wykona się
dokładnie raz i GŁOŚNO padnie, gdy się nie uda.
"""
from __future__ import annotations

import pytest

from footstats.db.migrations import _get_migrations_for_dialect as _migracje


NUMER = 11
NAZWA = "add_clv_closing_odds_to_predictions"


@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_migracja_istnieje_w_obu_dialektach(dialekt):
    """Testy chodzą na SQLite, produkcja na PostgreSQL — rozjazd = martwa kolumna."""
    numery = {m[0]: m[1] for m in _migracje(dialekt)}
    assert numery.get(NUMER) == NAZWA, f"brak migracji {NUMER} dla {dialekt}"


@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_migracja_dodaje_wlasciwa_kolumne(dialekt):
    sql = " ".join(
        " ".join(m[2]) for m in _migracje(dialekt) if m[0] == NUMER
    ).lower()
    assert "clv_closing_odds" in sql
    assert "alter table predictions" in sql


def test_postgres_uzywa_if_not_exists():
    """Ponowny przebieg migracji nie moze wywalic startu API."""
    sql = " ".join(
        " ".join(m[2]) for m in _migracje("postgresql") if m[0] == NUMER
    ).lower()
    assert "if not exists" in sql


@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_numery_migracji_sa_unikalne_i_rosnace(dialekt):
    """Duplikat numeru = jedna z migracji nigdy sie nie wykona."""
    numery = [m[0] for m in _migracje(dialekt)]
    assert numery == sorted(numery), "migracje nie sa w kolejnosci"
    assert len(numery) == len(set(numery)), "zduplikowany numer migracji"


def test_oba_dialekty_maja_ten_sam_zestaw_numerow():
    """Migracja dodana tylko po jednej stronie to bomba z opoznionym zaplonem."""
    sqlite = {m[0] for m in _migracje("sqlite")}
    postgres = {m[0] for m in _migracje("postgresql")}
    assert sqlite == postgres, f"rozjazd migracji: tylko sqlite={sqlite - postgres}, tylko pg={postgres - sqlite}"
