"""test_auto_trening.py — flaga AUTO_TRENING i odczyt licznika po nazwie kolumny.

Produkcja loguje "Blok auto-treningu przerwany (KeyError: 0)" w kazdym przebiegu:
polaczenie uzywa RealDictCursor, wiec `fetchone()[0]` nie dziala. Auto-trening
jest domyslnie WYLACZONY (model zamrozony, wynik treningu przepada w efemerycznym
kontenerze). Nic tu nie dotyka bazy, Popen ani Telegrama.
"""
from __future__ import annotations

import logging
import subprocess

import pytest

import footstats.core.backtest as bt


class _Conn:
    def __init__(self, wiersz):
        self._wiersz = wiersz

    def execute(self, sql, params=()):
        return self

    def fetchone(self):
        return self._wiersz

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def popen(monkeypatch):
    """Podmienia ZRODLO subprocess.Popen i wycisza Telegram; zwraca liste odpalen."""
    odpalone: list = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: odpalone.append(a))
    import footstats.utils.telegram_notify as tg
    monkeypatch.setattr(tg, "telegram_dostepny", lambda: False)
    return odpalone


def test_domyslnie_wylaczony_nie_dotyka_bazy(monkeypatch, popen, caplog):
    monkeypatch.delenv("AUTO_TRENING", raising=False)

    def _nie_wolno():
        raise AssertionError("_connect nie moze byc wolane przy wylaczonej fladze")

    monkeypatch.setattr(bt, "_connect", _nie_wolno)
    with caplog.at_level(logging.DEBUG):
        bt._sprawdz_auto_trening()

    assert popen == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_wiersz_slownikowy_n_40_odpala_trening(monkeypatch, popen):
    monkeypatch.setenv("AUTO_TRENING", "1")
    monkeypatch.setattr(bt, "_connect", lambda: _Conn({"n": 40}))
    bt._sprawdz_auto_trening()
    assert len(popen) == 1


def test_wiersz_slownikowy_n_41_nie_odpala(monkeypatch, popen):
    monkeypatch.setenv("AUTO_TRENING", "1")
    monkeypatch.setattr(bt, "_connect", lambda: _Conn({"n": 41}))
    bt._sprawdz_auto_trening()
    assert popen == []


def test_brak_wiersza_nie_wywala_i_nie_odpala(monkeypatch, popen):
    monkeypatch.setenv("AUTO_TRENING", "1")
    monkeypatch.setattr(bt, "_connect", lambda: _Conn(None))
    bt._sprawdz_auto_trening()
    assert popen == []


def test_blad_bazy_przy_wlaczonej_fladze_to_warning(monkeypatch, popen, caplog):
    monkeypatch.setenv("AUTO_TRENING", "1")

    def _wybuch():
        raise RuntimeError("DB down")

    monkeypatch.setattr(bt, "_connect", _wybuch)
    with caplog.at_level(logging.WARNING):
        bt._sprawdz_auto_trening()

    assert "Blok auto-treningu przerwany" in caplog.text
    assert popen == []
