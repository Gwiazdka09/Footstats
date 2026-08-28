"""Schemat bazy ma mieć JEDNO źródło — inaczej świeża baza zależy od tego,
który moduł zaimportował się pierwszy.

STAN ZASTANY (zmierzone 28.08). Tabele bazowe powstawały w DWÓCH miejscach:

    api/main._init_db()       8 tabel, `predictions` BEZ prob_home/prob_draw/
                              prob_away/settle_attempts/odds_verified
    core/backtest.init_db()   2 tabele, `predictions` Z tymi kolumnami,
                              ale z kluczem obcym do `coupons`, których
                              sama nie zakłada

Obie robią `CREATE TABLE IF NOT EXISTS` na TEJ SAMEJ bazie (`utils.db.connect`
jest wyłącznie Postgresem), więc na pustej bazie wygrywa ta, która wykona się
pierwsza. A wykonuje się różna w zależności od obrazu: `api/main` nie jest
importowany w obrazie jobs, gdzie `backtest.init_db()` woła dziewięć miejsc
(evening_agent, rag, post_match_analyzer, results_updater ×2, coupon_settlement ×2).

Dlaczego to jeszcze nie wybuchło: produkcyjna baza już istnieje, a na Postgresie
migracje 12/13 mają `ADD COLUMN IF NOT EXISTS`. Na SQLite ten sam ALTER jest BEZ
`IF NOT EXISTS` — czyli świeża baza zbudowana wersją z `backtest.py` wywala
migrację na kolumnie, która już jest.

NIEZMIENNIK, którego pilnują te testy, to NIE „jedna definicja" — `core/walkforward.py`
ma własny magazyn SQLite i musi mieć własny dialekt. Pilnowany jest ZESTAW KOLUMN:
kopie tej samej tabeli mogą różnić się składnią, nie zawartością.
"""
from __future__ import annotations

import re
from pathlib import Path

KORZEN = Path(__file__).resolve().parents[1]
SRC = KORZEN / "src" / "footstats"

_CREATE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)", re.I)


_KOLUMNY = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\s*\)", re.S | re.I
)
_NIE_KOLUMNA = ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT")


def _kolumny_w_pliku(tekst: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for m in _KOLUMNY.finditer(tekst):
        kol = set()
        for linia in m.group(2).splitlines():
            linia = linia.strip()
            if not linia or linia.startswith("--") or linia.upper().startswith(_NIE_KOLUMNA):
                continue
            kol.add(linia.split()[0].strip(","))
        out[m.group(1)] = kol
    return out


def test_kopie_tej_samej_tabeli_maja_ten_sam_zestaw_kolumn():
    """SEDNO. Nie zabraniam drugiej definicji — `core/walkforward.py` ma własny
    magazyn SQLITE (własny `_connect`, `AUTOINCREMENT` zamiast `SERIAL`), więc
    dialekt MUSI się różnić. Zabraniam RÓŻNIC W KOLUMNACH, bo to one decydują,
    czy kod czytający kolumnę ją znajdzie.

    Tak wyglądał zastany rozjazd (28.08): `predictions` w `api/main.py` nie miało
    prob_home/prob_draw/prob_away/settle_attempts/odds_verified, a w `backtest.py`
    miało; `coupons` w `coupon_tracker.py` miało bookmaker/user_id, a w `api/main.py`
    nie. Na pustej bazie wygrywała definicja, która wykonała się pierwsza."""
    per_tabela: dict[str, dict[str, set[str]]] = {}
    for plik in SRC.rglob("*.py"):
        for tabela, kolumny in _kolumny_w_pliku(plik.read_text(encoding="utf-8")).items():
            per_tabela.setdefault(tabela, {})[str(plik.relative_to(KORZEN))] = kolumny

    rozjazdy = {}
    for tabela, wersje in per_tabela.items():
        zestawy = {frozenset(k) for k in wersje.values()}
        if len(zestawy) > 1:
            wspolne = set.intersection(*(set(k) for k in wersje.values()))
            rozjazdy[tabela] = {
                plik: sorted(kol - wspolne) for plik, kol in wersje.items()
            }

    assert not rozjazdy, (
        "ta sama tabela ma rozne zestawy kolumn w roznych modulach"
        f" — swieza baza zalezy od kolejnosci importow: {rozjazdy}"
    )


def test_schemat_bazowy_zaklada_tabele_na_ktore_wskazuje():
    """`backtest.init_db()` tworzyło `predictions` z `REFERENCES coupons(id)`,
    nie tworząc `coupons`. Na pustej bazie to jest błąd, nie ostrzeżenie."""
    from footstats.db import schema

    ddl = schema.SCHEMAT_BAZOWY
    tworzone = set(_CREATE.findall(ddl))
    wskazywane = set(re.findall(r"REFERENCES\s+(\w+)\s*\(", ddl, re.I))

    brakujace = wskazywane - tworzone
    assert not brakujace, (
        f"schemat wskazuje kluczem obcym na tabele, ktorych nie zaklada: {sorted(brakujace)}"
    )


def test_oba_bootstrapy_uzywaja_tego_samego_ddl():
    """Sedno. `api/main._init_db` i `core/backtest.init_db` muszą wykonywać
    ten sam tekst SQL — nie „podobny", ten sam obiekt."""
    zrodla = {
        "api/main.py": (SRC / "api" / "main.py").read_text(encoding="utf-8"),
        "core/backtest.py": (SRC / "core" / "backtest.py").read_text(encoding="utf-8"),
    }
    for nazwa, tekst in zrodla.items():
        assert "footstats.db.schema import utworz_schemat_bazowy" in tekst, (
            f"{nazwa} nie uzywa wspolnego DDL z footstats.db.schema"
        )
        assert not _CREATE.search(tekst), (
            f"{nazwa} dalej ma wlasny CREATE TABLE — to jest ten rozjazd"
        )


def test_predictions_ma_kolumny_ktorych_wymaga_kod_rozliczen():
    """Regresja na konkretną stratę: wersja z `api/main.py` nie miała
    `settle_attempts` ani `odds_verified`, a kod rozliczeń czyta oba."""
    from footstats.db import schema

    for kolumna in ("settle_attempts", "odds_verified", "prob_home", "prob_draw", "prob_away"):
        assert kolumna in schema.SCHEMAT_BAZOWY, f"brak `{kolumna}` w schemacie bazowym"
