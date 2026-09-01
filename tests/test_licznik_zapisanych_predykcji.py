"""Licznik zapisanych predykcji nie moze liczyc duplikatow jako nowych wierszy.

ZMIERZONE 01.09 (`footstats-final-66gjs`). Log powiedzial:

    Zapisano 4 predykcji PO weryfikacji kursow

W bazie NIE przybyl ani jeden wiersz — najnowsza predykcja byla z poprzedniego
przebiegu, sprzed godziny. Powod w `core/backtest.py`:

    istnieje = conn.execute("SELECT id FROM predictions WHERE team_home=? ...")
    if istnieje:
        return istnieje["id"]        # <- zwraca id ISTNIEJACEGO wiersza

Deduplikacja jest poprawna (top3 + kupon_a/c robily wczesniej 2-5 duplikatow
psujacych statystyki). Bledny byl licznik: `zapisanych += 1` po KAZDYM udanym
wywolaniu, wiec "wstawiono" i "juz tam bylo" mialy ten sam wynik.

To ten sam ksztalt, co reszta awarii tego dnia: jedna liczba opisuje dwa stany,
a cisza czyni je nieodroznialnymi. Kosztowalo to bledna diagnoze — z logu
wynikalo, ze zapis dziala, choc nie powstalo nic nowego.

UWAGA PRZY ZMIANIE: detektor cichej awarii pyta o `_zapisanych`, czyli
"czy skonczylismy z predykcjami w bazie". Ponowny przebieg tego samego dnia
LEGALNIE tworzy zero nowych wierszy — gdyby alarm patrzyl na `_nowych`,
wylby przy kazdym powtorzeniu. Dlatego liczby sa DWIE, a nie podmienione.
"""
from __future__ import annotations

import sqlite3

import pytest

from tests.test_backtest_db import _SCHEMA, _SQLiteConn


@pytest.fixture
def baza(tmp_path, monkeypatch):
    sciezka = str(tmp_path / "pred.db")
    conn = sqlite3.connect(sciezka)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    return sciezka


def _zapisz(**kw):
    from footstats.core.backtest import save_prediction
    domyslne = dict(match_date="2026-09-01", team_home="FC Zürich",
                    team_away="BSC Young Boys", ai_tip="BTTS", ai_confidence=69)
    return save_prediction(**{**domyslne, **kw})


# ── save_prediction mowi, CZY wstawil ───────────────────────────────────────

def test_pierwszy_zapis_zglasza_utworzenie(baza):
    _id, utworzony = _zapisz()

    assert utworzony is True
    assert isinstance(_id, int)


def test_powtorzony_zapis_zglasza_duplikat(baza):
    id1, utworzony1 = _zapisz()
    id2, utworzony2 = _zapisz()

    assert utworzony1 is True
    assert utworzony2 is False, "drugi zapis tego samego meczu+tipu udaje nowy wiersz"
    assert id1 == id2, "dedup ma zwrocic id ISTNIEJACEGO wiersza"


def test_dedup_naprawde_nie_dubluje_wierszy(baza):
    """Kontrola: sprawdzamy BAZE, nie tylko wartosc zwracana."""
    _zapisz()
    _zapisz()

    conn = sqlite3.connect(baza)
    ile = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    conn.close()
    assert ile == 1


def test_inny_tip_to_nowy_wiersz(baza):
    """Kontrola negatywna: dedup nie moze zjadac roznych typow z tego meczu."""
    _zapisz(ai_tip="BTTS")
    _id, utworzony = _zapisz(ai_tip="Over 2.5")

    assert utworzony is True


# ── licznik w _auto_zapisz_backtest rozdziela obie liczby ───────────────────

def _dane_z_jednym_typem():
    return {"top3": [{"mecz": "FC Zürich vs BSC Young Boys", "typ": "BTTS",
                      "kurs": 1.37, "pewnosc_pct": 69}]}


def _wyniki():
    return [{"gospodarz": "FC Zürich", "goscie": "BSC Young Boys",
             "data": "2026-09-01", "liga": "Super League", "pred": {}}]


def test_pierwszy_przebieg_wszystko_nowe(baza):
    from footstats.ai.analyzer_helpers import _auto_zapisz_backtest

    dane = _dane_z_jednym_typem()
    _auto_zapisz_backtest(dane, _wyniki())

    assert dane["_zapisanych"] == 1
    assert dane["_nowych"] == 1


def test_powtorka_ma_zero_NOWYCH_ale_nadal_ma_zapisane(baza):
    """Sedno. Log mowil 'Zapisano 4', gdy nie przybylo nic."""
    from footstats.ai.analyzer_helpers import _auto_zapisz_backtest

    _auto_zapisz_backtest(_dane_z_jednym_typem(), _wyniki())

    dane = _dane_z_jednym_typem()
    _auto_zapisz_backtest(dane, _wyniki())

    assert dane["_nowych"] == 0, "powtorka raportuje nowe wiersze, ktorych nie ma"
    assert dane["_zapisanych"] == 1, (
        "`_zapisanych` musi zostac, bo to na nim stoi detektor cichej awarii — "
        "ponowny przebieg tego samego dnia nie jest awaria"
    )


# ── log mowi obie liczby ────────────────────────────────────────────────────

def test_log_rozdziela_nowe_od_juz_istniejacych(monkeypatch, caplog):
    """Sedno awarii: log mowil 'Zapisano 4', gdy 4 wiersze JUZ tam byly."""
    import logging

    import footstats.ai.analyzer_helpers as ah
    from footstats.daily_agent import _zapisz_predykcje_po_weryfikacji

    def _stub(dane, wyniki):
        dane["_zapisanych"] = 4
        dane["_nowych"] = 0

    monkeypatch.setattr(ah, "_auto_zapisz_backtest", _stub)
    monkeypatch.setattr(ah, "_dopisz_typy_z_modelu", lambda *a, **k: 0, raising=False)

    with caplog.at_level(logging.INFO):
        _zapisz_predykcje_po_weryfikacji({"top3": [{"mecz": "A vs B"}]}, [], {})

    tekst = " ".join(r.getMessage() for r in caplog.records)
    assert "0 nowych" in tekst, f"log nie mowi ile NOWYCH wierszy: {tekst}"
    assert "4 juz bylo" in tekst, f"log nie mowi ile bylo duplikatow: {tekst}"


def test_log_przy_pierwszym_przebiegu_mowi_o_samych_nowych(monkeypatch, caplog):
    """Kontrola negatywna: normalny dzien nie moze wygladac na powtorke."""
    import logging

    import footstats.ai.analyzer_helpers as ah
    from footstats.daily_agent import _zapisz_predykcje_po_weryfikacji

    monkeypatch.setattr(ah, "_auto_zapisz_backtest",
                        lambda dane, wyniki: dane.update({"_zapisanych": 3, "_nowych": 3}))

    with caplog.at_level(logging.INFO):
        _zapisz_predykcje_po_weryfikacji({"top3": [{"mecz": "A vs B"}]}, [], {})

    tekst = " ".join(r.getMessage() for r in caplog.records)
    assert "3 nowych" in tekst and "0 juz bylo" in tekst
