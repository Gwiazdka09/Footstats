"""D4 — dziennik modelu mierzy wyłącznie argmax 1X2, choć zapisuje trzy rynki.

STAN ZASTANY (zmierzony 24.08 na produkcji): `model_log` ma 595 wierszy, WSZYSTKIE
z `prob_over25` i `prob_btts`, a 388 ma już `actual_result`. Mimo to jedyną
mierzoną trafnością jest `tip_correct` liczony z `model_tip`, czyli argmax 1X2.
Rynki golowe są zapisywane i nigdy nie sprawdzane.

DLACZEGO TO BOLI TERAZ, A NIE KIEDYŚ: to właśnie rynki golowe są dziś głównym
wyjściem selekcji — z 20 kuponów z 15.08 osiemnaście to BTTS/Over/Under, z dzisiejszych
czternastu jedenaście. Flaga `BTTS_TWO_WAY` stoi na OFF, bo „brakuje danych do
walidacji", a dane leżą w tabeli od tygodni — brakuje wyłącznie policzenia ich.

CZEGO NIE TRZEBA CZEKAĆ: `actual_result` trzyma pełny wynik (`"3-1"`), a
`oblicz_tip_correct` rozlicza z niego Over/Under i BTTS tak samo dobrze jak 1X2.
Całe 388 wierszy da się ocenić wstecznie, bez jednego nowego meczu.

ZAKRES: trafność trzech rynków z jednego wyniku, uzupełnienie wierszy historycznych
i pilnowanie, żeby „nie wiemy" nigdy nie zapisało się jako „model się pomylił".
"""
from __future__ import annotations

import pytest

from footstats.core import kalibracja_log as kl


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


# ── trafność trzech rynków z jednego wyniku ────────────────────────────────

@pytest.mark.parametrize("wynik,tip,ocz_tip,ocz_o25,ocz_btts,ocz_draw", [
    # 3-1: gospodarz wygrał, 4 gole, obie strzeliły, nie remis
    ("3-1", "1", 1, 1, 1, 0),
    ("3-1", "X", 0, 1, 1, 0),
    # 0-0: remis, brak goli, BTTS nie
    ("0-0", "X", 1, 0, 0, 1),
    ("0-0", "1", 0, 0, 0, 1),
    # 1-1: remis, 2 gole (Under), obie strzeliły
    ("1-1", "X", 1, 0, 1, 1),
    # 2-0: gospodarz, 2 gole (Under), tylko jedna strzeliła, nie remis
    ("2-0", "1", 1, 0, 0, 0),
    # 4-2: gość przegrał, 6 goli, obie strzeliły, nie remis
    ("4-2", "2", 0, 1, 1, 0),
])
def test_jeden_wynik_ocenia_cztery_rynki(wynik, tip, ocz_tip, ocz_o25, ocz_btts, ocz_draw):
    oceny = kl.oceny_rynkow(tip, wynik)

    assert oceny == {
        "tip_correct": ocz_tip,
        "over25_correct": ocz_o25,
        "btts_correct": ocz_btts,
        "draw_correct": ocz_draw,
    }, f"{wynik} przy typie {tip}"


def test_granica_over_under_na_25():
    """2 gole to Under, 3 to Over — próg leży MIĘDZY nimi i to jedyny punkt,
    w którym łatwo o pomyłkę o jeden."""
    assert kl.oceny_rynkow("X", "1-1")["over25_correct"] == 0   # 2 gole
    assert kl.oceny_rynkow("1", "2-1")["over25_correct"] == 1   # 3 gole


def test_brak_wyniku_nie_ocenia_niczego():
    assert kl.oceny_rynkow("1", None) is None
    assert kl.oceny_rynkow("1", "") is None


def test_dogrywka_nie_zapisuje_zera(caplog):
    """„Nie wiemy" to nie to samo co „model się pomylił".

    Zapis zera dla meczu rozstrzygniętego po karnych zafałszowałby kalibrację
    WSZYSTKICH trzech rynków naraz, nie tylko 1X2.
    """
    assert kl.oceny_rynkow("1", "2-1 (AET)") is None
    assert kl.oceny_rynkow("1", "2-1aet") is None


# ── zapis wyniku ───────────────────────────────────────────────────────────

def test_zapisz_wynik_uzupelnia_oba_rynki_golowe(baza):
    assert kl.zapisz_wynik(7, "3-1", "1") is True

    update = baza["conn"].zawierajace("UPDATE model_log")
    assert update, "brak UPDATE"
    sql, params = update[0]
    assert "over25_correct" in sql, sql
    assert "btts_correct" in sql, sql
    # 3-1 → Over trafiony, BTTS trafiony, typ "1" trafiony
    assert 1 in params


def test_zapisz_wynik_nierozliczalny_nic_nie_zapisuje(baza):
    assert kl.zapisz_wynik(7, "2-1 (AET)", "1") is False
    assert not baza["conn"].zawierajace("UPDATE model_log")


def test_zapisz_wynik_bez_wyniku_nic_nie_zapisuje(baza):
    assert kl.zapisz_wynik(7, None, "1") is False
    assert not baza["conn"].zawierajace("UPDATE model_log")


# ── uzupełnienie wierszy historycznych ─────────────────────────────────────

def test_uzupelnia_wiersze_ktore_juz_maja_wynik(monkeypatch):
    """388 wierszy czeka z gotowym wynikiem — nie ma po co czekać na nowe mecze."""
    conn = _Conn(do_uzupelnienia=[
        {"id": 1, "model_tip": "1", "actual_result": "3-1"},
        {"id": 2, "model_tip": "X", "actual_result": "0-0"},
    ])
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)

    stat = kl.uzupelnij_rynki_golowe(dry_run=False)

    assert stat["uzupelnione"] == 2
    assert len(conn.zawierajace("UPDATE model_log")) == 2


def test_uzupelnianie_na_sucho_nic_nie_zapisuje(monkeypatch):
    conn = _Conn(do_uzupelnienia=[{"id": 1, "model_tip": "1", "actual_result": "3-1"}])
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)

    stat = kl.uzupelnij_rynki_golowe(dry_run=True)

    assert stat["uzupelnione"] == 1, "suchy przebieg ma RAPORTOWAC, ile by zrobil"
    assert not conn.zawierajace("UPDATE model_log"), "suchy przebieg zapisal do bazy"


def test_uzupelnianie_pomija_nierozliczalne(monkeypatch):
    """Mecz po karnych zostaje nietknięty, nie dostaje zer."""
    conn = _Conn(do_uzupelnienia=[
        {"id": 1, "model_tip": "1", "actual_result": "2-1 (AET)"},
        {"id": 2, "model_tip": "1", "actual_result": "3-1"},
    ])
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)

    stat = kl.uzupelnij_rynki_golowe(dry_run=False)

    assert stat["uzupelnione"] == 1
    assert stat["pominiete"] == 1
    assert len(conn.zawierajace("UPDATE model_log")) == 1


# ── schemat ────────────────────────────────────────────────────────────────

def test_init_dodaje_kolumny_do_istniejacej_tabeli(monkeypatch):
    """Tabela istnieje na produkcji od tygodni — `CREATE IF NOT EXISTS` jej nie ruszy.

    Bez idempotentnego ALTER-a kolumny pojawiłyby się wyłącznie na świeżej bazie,
    czyli w testach, a produkcja wywalałaby się na `column does not exist`.
    Dokładnie ten błąd popełniono już przy `model_source` — komentarz w kodzie
    o tym mówi, więc powtórka byłaby niewybaczalna.
    """
    conn = _Conn()
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)

    kl.init_kalibracja_log()

    altery = " ".join(z[0].upper() for z in conn.zawierajace("ADD COLUMN IF NOT EXISTS"))
    assert "OVER25_CORRECT" in altery, altery
    assert "BTTS_CORRECT" in altery, altery
