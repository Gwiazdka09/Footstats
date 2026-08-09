"""RAG sięga po historię, gdy własne predykcje nie mają jeszcze paliwa.

PO CO: `pobierz_rag_wzorce` liczy skuteczność z tabeli `predictions`, a tam jest
**0 rozliczonych predykcji z niepustymi `factors`** (pomiar produkcyjny
09.08.2026). Zwracała więc pusty string i będzie tak robić tygodniami.
Tablica historyczna z 139 102 meczów daje te same liczby od razu.

Kolejność jest istotna: WŁASNE predykcje mają pierwszeństwo, bo opisują ten
model i tę warstwę selekcji. Historia wchodzi dopiero, gdy własnych brak.
"""
from __future__ import annotations

import pytest

from footstats.ai import rag


@pytest.fixture
def bez_wlasnych_danych(monkeypatch):
    """Baza nie ma rozliczonych predykcji z czynnikami — stan produkcji."""
    class _Kursor:
        def fetchall(self):
            return []

    class _Conn:
        def execute(self, sql, params=None):
            return _Kursor()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(rag, "_connect", lambda: _Conn())
    monkeypatch.setattr(rag, "init_db", lambda: None)


def test_bez_wlasnych_danych_siega_po_historie(bez_wlasnych_danych, monkeypatch):
    monkeypatch.setattr(
        "footstats.core.wzorce_historyczne.wczytaj_tablice",
        lambda: {"wzorce": {"PATENT->1": {"n": 170, "trafien": 98}}},
    )

    wynik = rag.pobierz_rag_wzorce(["PATENT"], ai_tip="1")

    assert "PATENT->1" in wynik
    assert "98/170" in wynik


def test_brak_tablicy_zostawia_pusty_wynik(bez_wlasnych_danych, monkeypatch):
    """Brak obu zrodel ma dac "" — wolajacy pomija sekcje RAG w prompcie."""
    monkeypatch.setattr("footstats.core.wzorce_historyczne.wczytaj_tablice", dict)

    assert rag.pobierz_rag_wzorce(["PATENT"], ai_tip="1") == ""


def test_wlasne_dane_maja_pierwszenstwo(monkeypatch):
    """Historia to zapas, nie zamiennik: wlasne predykcje opisuja TEN model."""
    class _Kursor:
        def fetchall(self):
            return [{"n": 40, "hits": 30}]

    class _Conn:
        def execute(self, sql, params=None):
            return _Kursor()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(rag, "_connect", lambda: _Conn())
    monkeypatch.setattr(rag, "init_db", lambda: None)

    def _nie_wolaj():
        raise AssertionError("siegnieto po historie mimo wlasnych danych")

    monkeypatch.setattr("footstats.core.wzorce_historyczne.wczytaj_tablice", _nie_wolaj)

    wynik = rag.pobierz_rag_wzorce(["PATENT"], ai_tip="1")

    assert "30/40" in wynik


def test_brak_czynnikow_nie_siega_nigdzie(monkeypatch):
    """Bez czynnikow nie ma czego szukac — ani w bazie, ani w historii."""
    def _nie_wolaj():
        raise AssertionError("siegnieto po historie bez czynnikow")

    monkeypatch.setattr("footstats.core.wzorce_historyczne.wczytaj_tablice", _nie_wolaj)

    assert rag.pobierz_rag_wzorce([], ai_tip="1") == ""
