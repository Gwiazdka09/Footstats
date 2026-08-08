"""Zapytanie RAG musi mówić dialektem bazy, na której realnie chodzi.

PO CO: `pobierz_rag_wzorce` szukało czynników przez `json_each(factors)` —
to składnia SQLite. Produkcja siedzi na PostgreSQL (`utils/db.py` to psycopg2),
a tam sprawdzone 09.08.2026 wprost na bazie:

    UndefinedFunction: function json_each(text) does not exist

Całe ciało funkcji jest opakowane w `except Exception: return ""`, więc każde
wywołanie kończyło się pustym stringiem — RAG nie oddałby ANI JEDNEGO wzorca,
nawet gdyby `factors` były wypełnione. Objaw nie do odróżnienia od „za mało
danych historycznych", stąd nikt tego nie widział.

W PostgreSQL tablicę JSON rozwija `json_array_elements_text`, a kolumna
`factors` jest typu TEXT, więc wymaga rzutowania.
"""
from __future__ import annotations

import re

from footstats.ai import rag


def _przechwyc_sql(monkeypatch) -> list[str]:
    """Podstawia połączenie, które tylko zapamiętuje SQL i zwraca puste wyniki."""
    zebrane: list[str] = []

    class _Kursor:
        def fetchall(self):
            return []

    class _Conn:
        def execute(self, sql, params=None):
            zebrane.append(sql)
            return _Kursor()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(rag, "_connect", lambda: _Conn())
    monkeypatch.setattr(rag, "init_db", lambda: None)
    return zebrane


def test_zapytanie_nie_uzywa_skladni_sqlite(monkeypatch):
    zebrane = _przechwyc_sql(monkeypatch)

    rag.pobierz_rag_wzorce(["TWIERDZA", "PATENT"], ai_tip="1")

    assert zebrane, "funkcja nie doszla do zapytania"
    sql = " ".join(zebrane)
    assert "json_each" not in sql, "skladnia SQLite w zapytaniu do PostgreSQL"


def test_zapytanie_rozwija_tablice_po_postgresowemu(monkeypatch):
    zebrane = _przechwyc_sql(monkeypatch)

    rag.pobierz_rag_wzorce(["TWIERDZA"], ai_tip="1")

    sql = " ".join(zebrane)
    assert "json_array_elements_text" in sql
    assert "factors::json" in sql, "kolumna TEXT wymaga rzutowania na json"


def test_wartosci_czynnikow_leca_parametrami_nie_w_sql(monkeypatch):
    """Nazwa czynnika wklejona w SQL to wektor wstrzyknięcia, nie skrót."""
    zebrane = _przechwyc_sql(monkeypatch)

    rag.pobierz_rag_wzorce(["TWIERDZA'; DROP TABLE predictions--"], ai_tip="1")

    sql = " ".join(zebrane)
    assert "DROP TABLE" not in sql


def test_liczba_placeholderow_zgadza_sie_z_parametrami(monkeypatch):
    """Rozjazd = `ProgrammingError` polkniety przez `except` i cicha cisza."""
    zebrane: list[tuple[str, list]] = []

    class _Kursor:
        def fetchall(self):
            return []

    class _Conn:
        def execute(self, sql, params=None):
            zebrane.append((sql, list(params or [])))
            return _Kursor()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(rag, "_connect", lambda: _Conn())
    monkeypatch.setattr(rag, "init_db", lambda: None)

    rag.pobierz_rag_wzorce(["TWIERDZA", "PATENT", "ZEMSTA"], ai_tip="1")

    sql, params = zebrane[0]
    assert len(re.findall(r"\?", sql)) == len(params)
