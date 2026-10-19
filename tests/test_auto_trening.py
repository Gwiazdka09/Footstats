"""test_auto_trening.py — flaga AUTO_TRENING i odczyt licznika po nazwie kolumny.

Produkcja loguje "Blok auto-treningu przerwany (KeyError: 0)" w kazdym przebiegu:
polaczenie uzywa RealDictCursor, wiec `fetchone()[0]` nie dziala. Auto-trening
jest domyslnie WYLACZONY (model zamrozony, wynik treningu przepada w efemerycznym
kontenerze). Nic tu nie dotyka bazy, Popen ani Telegrama.
"""
from __future__ import annotations

import inspect
import logging
import re
import subprocess
from pathlib import Path

import pytest

import footstats.core.backtest as bt

_WZORZEC_TRENERA = re.compile(r'"-m",\s*"footstats\.ai\.trainer"')


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


def test_trener_uruchamiany_tylko_z_jednego_miejsca():
    """Każde uruchomienie trenera idzie przez odpal_trener_w_tle (jeden wyłącznik)."""
    src_root = Path(__file__).resolve().parents[1] / "src" / "footstats"
    trafienia = []
    for plik in src_root.rglob("*.py"):
        tresc = plik.read_text(encoding="utf-8", errors="replace")
        if _WZORZEC_TRENERA.search(tresc):
            trafienia.append(plik.relative_to(src_root).as_posix())

    assert trafienia == ["core/backtest.py"], (
        f"Znalezione miejsca uruchomienia trenera: {trafienia}. "
        "Każde uruchomienie trenera ma iść przez odpal_trener_w_tle + "
        "auto_trening_wlaczony (core/backtest.py)."
    )
    assert _WZORZEC_TRENERA.search(inspect.getsource(bt.odpal_trener_w_tle))


def test_telegram_nie_idzie_po_nieudanym_starcie(monkeypatch, caplog):
    monkeypatch.setenv("AUTO_TRENING", "1")
    monkeypatch.setattr(bt, "_connect", lambda: _Conn({"n": 40}))

    def _padnij(*a, **k):
        raise OSError("brak")

    monkeypatch.setattr(subprocess, "Popen", _padnij)
    import footstats.utils.telegram_notify as tg
    monkeypatch.setattr(tg, "telegram_dostepny", lambda: True)
    wyslane: list = []
    monkeypatch.setattr(tg, "_send", wyslane.append)

    with caplog.at_level(logging.WARNING):
        bt._sprawdz_auto_trening()

    assert wyslane == []
    assert "start trenera nieudany" in caplog.text


@pytest.fixture
def evening_trener(monkeypatch):
    """Podmienia ZRODLO odpal_trener_w_tle (import w evening jest lokalny)."""
    wywolania: list = []

    def _rejestruj(cwd=None):
        wywolania.append(cwd)
        return True

    monkeypatch.setattr(bt, "odpal_trener_w_tle", _rejestruj)
    return wywolania


def test_evening_nie_odpala_gdy_flaga_wylaczona(monkeypatch, evening_trener):
    import footstats.evening_agent as ea
    monkeypatch.delenv("AUTO_TRENING", raising=False)

    assert ea._moze_odpal_auto_trener(25) is False
    assert evening_trener == []


def test_evening_odpala_z_katalogiem_repo_gdy_flaga_wlaczona(monkeypatch, evening_trener):
    import footstats.evening_agent as ea
    monkeypatch.setenv("AUTO_TRENING", "1")

    assert ea._moze_odpal_auto_trener(25) is True
    assert len(evening_trener) == 1
    cwd = evening_trener[0]
    assert Path(cwd).resolve() == Path(ea.__file__).resolve().parents[2]


def test_evening_nie_odpala_ponizej_20_wynikow(monkeypatch, evening_trener):
    import footstats.evening_agent as ea
    monkeypatch.setenv("AUTO_TRENING", "1")

    assert ea._moze_odpal_auto_trener(19) is False
    assert evening_trener == []
