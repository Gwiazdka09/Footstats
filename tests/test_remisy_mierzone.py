"""ZADANIE R — remis przestaje być ślepą plamą modelu.

STAN ZASTANY (produkcja 2026-08-26, n=427 wierszy z wynikiem): `model_tip` = "X"
wystąpił ZERO razy (304x "1", 123x "2"). `prob_draw` ma maksimum 34.0%, więc
nie może wygrać argmaxu 1X2 przeciw dwóm pozostałym opcjom poza skrajnymi
przypadkami — remisy są niemierzalne przez `tip_correct` STRUKTURALNIE, nie
przez przypadek. Tymczasem realna częstość remisów w tej samej próbce to 23.6%
(100 z 424 rozliczalnych) — zdanie modelu o co czwartym meczu nie zostało
zweryfikowane ani razu.

To dokładnie ten sam kształt co D4 (commit 7e5d35918): `prob_over25` i
`prob_btts` były zapisywane od początku i nigdy z niczym nie porównywane.
Rozwiązanie jest identyczne — osobna kolumna `draw_correct`, licz. z SAMEGO
WYNIKU (`actual_result`), niezależnie od tego, co obstawił model.
"""
from __future__ import annotations

import pytest

from footstats.core import kalibracja_log as kl
from scripts import stan_uczenia


# ── atrapa bazy dla kalibracja_log (wzorowana na D4: test_model_log_rynki_golowe) ──

class _Kursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Conn:
    """Atrapa bazy — notuje zapytania, oddaje ustalone wiersze."""

    def __init__(self, do_uzupelnienia=None):
        self.do_uzupelnienia = do_uzupelnienia or []
        self.zapytania: list[tuple] = []

    def execute(self, sql, params=()):
        plaski = " ".join(sql.split())
        self.zapytania.append((plaski, params))
        g = plaski.upper()
        if g.startswith("SELECT") and "ACTUAL_RESULT IS NOT NULL" in g:
            return _Kursor(self.do_uzupelnienia)
        return _Kursor([])

    def executescript(self, sql):
        self.zapytania.append((" ".join(sql.split()), ()))

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def zawierajace(self, fragment: str) -> list[tuple]:
        return [z for z in self.zapytania if fragment.upper() in z[0].upper()]


@pytest.fixture
def baza(monkeypatch):
    stan = {"conn": _Conn()}
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: stan["conn"])
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)
    return stan


# ── oceny_rynkow: draw_correct ─────────────────────────────────────────────

def test_oceny_rynkow_remis_trafiony():
    assert kl.oceny_rynkow("1", "1-1")["draw_correct"] == 1


def test_oceny_rynkow_remis_nietrafiony():
    assert kl.oceny_rynkow("1", "2-1")["draw_correct"] == 0


def test_wynik_nierozliczalny_nie_zapisuje_zadnej_kolumny():
    """Dogrywka/karne: cała ocena znika, żadna kolumna (w tym draw_correct)
    nie dostaje cichego zera."""
    assert kl.oceny_rynkow("1", "2-1 (AET)") is None


def test_draw_correct_niezalezny_od_typu_modelu():
    """NAJWAŻNIEJSZY test tego pliku — cały sens zadania.

    Model typował "1" i pomylił się (`tip_correct=0`), a mecz skończył się
    remisem "0-0". Model NIE mówił "X" — gdyby `draw_correct` czerpał z
    `model_tip`, wyszłoby 0. Poprawna odpowiedź to 1, bo pytamy o SAM WYNIK,
    nie o zgadywankę modelu. Bez tego testu ktoś w przyszłości „uprości" to
    z powrotem do `model_tip`.
    """
    oceny = kl.oceny_rynkow("1", "0-0")
    assert oceny["tip_correct"] == 0
    assert oceny["draw_correct"] == 1


def test_oceny_rynkow_zwraca_wszystkie_cztery_klucze():
    oceny = kl.oceny_rynkow("2", "3-1")
    assert set(oceny) == {"tip_correct", "over25_correct", "btts_correct", "draw_correct"}


# ── zapis wyniku ────────────────────────────────────────────────────────────

def test_zapisz_wynik_dopisuje_draw_correct(baza):
    assert kl.zapisz_wynik(7, "1-1", "1") is True

    update = baza["conn"].zawierajace("UPDATE model_log")
    assert update, "brak UPDATE"
    sql, params = update[0]
    assert "draw_correct" in sql, sql
    assert 1 in params  # 1-1 to remis, draw_correct=1


def test_zapisz_wynik_nierozliczalny_nic_nie_zapisuje(baza):
    assert kl.zapisz_wynik(7, "2-1 (AET)", "1") is False
    assert not baza["conn"].zawierajace("UPDATE model_log")


# ── uzupełnienie wierszy historycznych (uzupelnij_rynki_golowe) ────────────

def test_uzupelnianie_zapytania_lapie_wiersze_bez_draw_correct(monkeypatch):
    """REGRESJA NA WARUNEK WHERE — to jest najważniejsza linijka zadania.

    427 istniejących wierszy ma już `over25_correct` i `btts_correct`, więc
    warunek liczący tylko te dwie kolumny nigdy by ich nie złapał. Bez
    `draw_correct IS NULL` w WHERE żaden z tych wierszy nie dostałby remisu.
    """
    conn = _Conn(do_uzupelnienia=[{"id": 42, "model_tip": "1", "actual_result": "3-1"}])
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)

    kl.uzupelnij_rynki_golowe(dry_run=True)

    select = conn.zawierajace("ACTUAL_RESULT IS NOT NULL")
    assert select, "brak zapytania SELECT"
    sql = select[0][0].upper()
    assert "DRAW_CORRECT IS NULL" in sql, sql


def test_uzupelnianie_dry_run_nic_nie_zapisuje(monkeypatch):
    conn = _Conn(do_uzupelnienia=[{"id": 1, "model_tip": "1", "actual_result": "1-1"}])
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)

    stat = kl.uzupelnij_rynki_golowe(dry_run=True)

    assert stat["uzupelnione"] == 1, "suchy przebieg ma RAPORTOWAC, ile by zrobil"
    assert not conn.zawierajace("UPDATE model_log"), "suchy przebieg zapisal do bazy"


def test_uzupelnianie_zapisuje_draw_correct(monkeypatch):
    conn = _Conn(do_uzupelnienia=[{"id": 5, "model_tip": "1", "actual_result": "1-1"}])
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)

    kl.uzupelnij_rynki_golowe(dry_run=False)

    update = conn.zawierajace("UPDATE model_log")
    assert update, "brak UPDATE"
    sql, params = update[0]
    assert "draw_correct" in sql, sql
    assert 1 in params  # 1-1 to remis


def test_uzupelnianie_pomija_nierozliczalne_dalej_dziala(monkeypatch):
    conn = _Conn(do_uzupelnienia=[
        {"id": 1, "model_tip": "1", "actual_result": "2-1 (AET)"},
        {"id": 2, "model_tip": "1", "actual_result": "3-1"},
    ])
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)

    stat = kl.uzupelnij_rynki_golowe(dry_run=False)

    assert stat["uzupelnione"] == 1
    assert stat["pominiete"] == 1


# ── schemat ─────────────────────────────────────────────────────────────────

def test_init_dodaje_kolumne_draw_correct(monkeypatch):
    """Tabela żyje na produkcji od tygodni — `CREATE IF NOT EXISTS` jej nie ruszy.
    Bez idempotentnego ALTER-a `draw_correct` istniałby wyłącznie w testach.
    """
    conn = _Conn()
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)

    kl.init_kalibracja_log()

    altery = " ".join(z[0].upper() for z in conn.zawierajace("ADD COLUMN IF NOT EXISTS"))
    assert "DRAW_CORRECT" in altery, altery


# ── raport_remisow (scripts/stan_uczenia.py) ────────────────────────────────

class _ConnRaportu:
    """Minimalne połączenie zwracające zaplanowane wiersze po kolei."""

    def __init__(self, odpowiedzi: list[list[dict]]):
        self.odpowiedzi = list(odpowiedzi)
        self.zapytania: list[str] = []

    def execute(self, zapytanie, params=None):
        self.zapytania.append(zapytanie)
        wiersze = self.odpowiedzi.pop(0) if self.odpowiedzi else []
        return _KursorRaportu(wiersze)


class _KursorRaportu:
    def __init__(self, wiersze):
        self._w = wiersze

    def fetchall(self):
        return self._w


def test_raport_remisow_brak_danych_mowi_co_uruchomic(capsys):
    conn = _ConnRaportu([[{"n": 0, "realnie": None}]])

    stan_uczenia.raport_remisow(conn)

    out = capsys.readouterr().out
    assert "BRAK DANYCH" in out
    assert "uzupelnij_rynki_golowe(dry_run=False)" in out


def test_raport_remisow_drukuje_linie_bazowa_i_werdykt(capsys):
    conn = _ConnRaportu([
        [{"n": 427, "realnie": 23.6}],
        [
            {"koszyk": "<15%", "od": 7.3, "n": 40, "model": 12.0, "realnie": 15.0},
            {"koszyk": "15-20%", "od": 15.0, "n": 120, "model": 17.5, "realnie": 20.0},
            {"koszyk": "20-25%", "od": 20.0, "n": 150, "model": 22.0, "realnie": 24.0},
            {"koszyk": "25-30%", "od": 25.0, "n": 80, "model": 27.0, "realnie": 27.0},
            {"koszyk": "30%+", "od": 30.0, "n": 37, "model": 32.0, "realnie": 30.0},
        ],
    ])

    stan_uczenia.raport_remisow(conn)

    out = capsys.readouterr().out
    assert "23.6%" in out, "brak linii bazowej"
    assert "ROSNIE" in out, "krzywa jest monotoniczna, werdykt ma to pokazac"
    assert "rozpietosc" in out


def test_raport_remisow_nie_rosnie_gdy_krzywa_nieuporzadkowana(capsys):
    conn = _ConnRaportu([
        [{"n": 100, "realnie": 22.0}],
        [
            {"koszyk": "<15%", "od": 7.3, "n": 20, "model": 12.0, "realnie": 25.0},
            {"koszyk": "15-20%", "od": 15.0, "n": 20, "model": 17.5, "realnie": 10.0},
        ],
    ])

    stan_uczenia.raport_remisow(conn)

    out = capsys.readouterr().out
    assert "NIE rosnie" in out
