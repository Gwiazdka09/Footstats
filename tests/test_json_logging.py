"""test_json_logging.py — logi JSON wspolne dla API i jobow.

PO CO (2026-07-30):

`_JsonFormatter` siedzial w `api/main.py`, wiec strukturalne logi mialo TYLKO
API. Joby (`daily_agent`, `evening_agent`) leca w Cloud Run Jobs i logowaly
plaskim tekstem — w Cloud Logging nie da sie po tym filtrowac ani po poziomie,
ani po loggerze, a to wlasnie joby robia caly pipeline predykcji.

Przy przenosinach wyszedl drugi defekt: stary formatter nadpisywal `format()`
i NIGDY nie siegal po `exc_info`, wiec `log.error(..., exc_info=True)` gubil
traceback. Bledy w logach byly jednolinijkowe i bezuzyteczne do debugowania.
"""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

import pytest

from footstats.core.logging_config import (
    JsonFormatter,
    request_id_var,
    skonfiguruj_logi_json,
)

_SRC = Path(__file__).resolve().parents[1] / "src" / "footstats"


def _rekord(msg: str = "test", poziom: int = logging.INFO, **kw) -> logging.LogRecord:
    return logging.LogRecord(
        name="footstats.test", level=poziom, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=kw.get("exc_info"),
    )


def test_format_zwraca_poprawny_json():
    wynik = json.loads(JsonFormatter().format(_rekord("wiadomosc")))
    assert wynik["level"] == "INFO"
    assert wynik["msg"] == "wiadomosc"
    assert wynik["logger"] == "footstats.test"
    assert "time" in wynik


def test_request_id_pusty_gdy_nieustawiony():
    """Joby nie maja requestu — pole ma byc puste, nie wywalac formattera."""
    request_id_var.set("")
    assert json.loads(JsonFormatter().format(_rekord()))["request_id"] == ""


def test_request_id_trafia_do_logu():
    token = request_id_var.set("abc12345")
    try:
        assert json.loads(JsonFormatter().format(_rekord()))["request_id"] == "abc12345"
    finally:
        request_id_var.reset(token)


def test_traceback_trafia_do_logu():
    """Regresja: stary formatter gubil exc_info — bledy byly nie do zdebugowania."""
    try:
        raise ValueError("rozwalone")
    except ValueError:
        import sys
        rekord = _rekord("padlo", poziom=logging.ERROR, exc_info=sys.exc_info())

    wynik = json.loads(JsonFormatter().format(rekord))
    assert "exc" in wynik, "brak pola exc — traceback zgubiony"
    assert "ValueError" in wynik["exc"]
    assert "rozwalone" in wynik["exc"]


def test_brak_pola_exc_gdy_nie_ma_wyjatku():
    """Zwykly log nie ma puchnac o puste pole."""
    assert "exc" not in json.loads(JsonFormatter().format(_rekord()))


def test_konfiguracja_jest_idempotentna():
    """Dwukrotne wywolanie nie moze duplikowac handlerow (podwojne linie w logach)."""
    root = logging.getLogger()
    zachowane = list(root.handlers)
    try:
        skonfiguruj_logi_json()
        po_pierwszym = len(logging.getLogger().handlers)
        skonfiguruj_logi_json()
        assert len(logging.getLogger().handlers) == po_pierwszym
    finally:
        root.handlers = zachowane


def test_konfiguracja_ustawia_formatter_json():
    root = logging.getLogger()
    zachowane = list(root.handlers)
    try:
        skonfiguruj_logi_json()
        formattery = [h.formatter for h in logging.getLogger().handlers]
        assert any(isinstance(f, JsonFormatter) for f in formattery)
    finally:
        root.handlers = zachowane


@pytest.mark.parametrize("modul", ["daily_agent.py", "evening_agent.py"])
def test_joby_konfiguruja_logi_json(modul: str):
    """Sedno zmiany: oba joby MUSZA wolac konfiguracje, inaczej dalej logują plaskim tekstem.

    Sprawdzamy statycznie (AST), bo uruchomienie main() jobow to odpalenie
    produkcyjnego pipeline'u — blokowane przez guard_live_ops.
    """
    drzewo = ast.parse((_SRC / modul).read_text(encoding="utf-8"))
    wolania = {
        w.func.id if isinstance(w.func, ast.Name) else getattr(w.func, "attr", "")
        for w in ast.walk(drzewo) if isinstance(w, ast.Call)
    }
    assert "skonfiguruj_logi_json" in wolania, (
        f"{modul} nie woła skonfiguruj_logi_json() — logi joba zostaną płaskim tekstem"
    )


def test_api_uzywa_wspolnego_formattera():
    """api/main.py ma korzystac ze wspolnego modulu, a nie miec wlasnej kopii."""
    tekst = (_SRC / "api" / "main.py").read_text(encoding="utf-8")
    assert "class _JsonFormatter" not in tekst, "api/main.py wciąż ma własną kopię formattera"
    assert "logging_config" in tekst
