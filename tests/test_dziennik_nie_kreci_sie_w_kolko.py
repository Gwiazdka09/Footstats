"""Wpis, którego NIGDY nie da się rozliczyć, musi wyjść z kolejki dziennika.

ZMIERZONE NA PRODUKCJI 28.08: 218 wierszy `model_log` z rozegranym meczem nie ma
wyniku (34% dziennika). Puchary 58,2%, ligi 17,3%. Sonda po FlashScore pokazała,
dlaczego — źródło ODDAJE wynik, tylko po dogrywce:

    LASK vs Celtic (Champions League)  -> '5-1aet'
    Hallescher FC vs FC Schalke 04     -> '2-5aet'
    VSG Altglienicke vs VfL Wolfsburg  -> '3-3 (Pen- 5-6)'

`oblicz_tip_correct` odrzuca takie wyniki słusznie: rynki 90-minutowe wymagają
wyniku regulaminowego, a „skoro była dogrywka, to po 90 minutach był remis" jest
zawodne przy dwumeczu. Ale `zapisz_wynik` nie zapisywało wtedy NICZEGO, więc
wiersz zostawał z `tip_correct IS NULL` i `pobierz_nierozliczone` podawało go
z powrotem. Każdego dnia. W nieskończoność — razem z ostrzeżeniem w logach
i z zapytaniem do scrapera.

ROZRÓŻNIENIE, KTÓRE TO NAPRAWIA (i którego kod nie miał):
  * `actual_result` puste  → „jeszcze nie wiemy"  → wracaj do kolejki;
  * `actual_result` pełne, `tip_correct` NULL → „wiemy i wiemy, że się nie da"
    → z kolejki wyjdź, ale trafności NIE zapisuj (zero fałszowałoby kalibrację).

Izolacja: własna plikowa SQLite, `_connect` podmieniony. Zero prod, zero sieci.
"""
from __future__ import annotations

import sqlite3

import pytest

import footstats.core.kalibracja_log as kl
import footstats.core.match_linker as ml

from tests.test_match_linker import _SQLiteConn

DATA = "2026-08-25"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date     TEXT NOT NULL,
    league         TEXT,
    team_home      TEXT NOT NULL,
    team_away      TEXT NOT NULL,
    model_tip      TEXT,
    actual_result  TEXT,
    tip_correct    INTEGER,
    over25_correct INTEGER,
    btts_correct   INTEGER,
    draw_correct   INTEGER
);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    sciezka = str(tmp_path / "dziennik.db")
    setup = sqlite3.connect(sciezka)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()
    monkeypatch.setattr(kl, "_connect", lambda: _SQLiteConn(sciezka))
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)
    monkeypatch.setattr(ml, "connect", lambda: _SQLiteConn(sciezka))
    return sciezka


def _wstaw(sciezka: str, home="LASK", away="Celtic", tip="1", data=DATA) -> int:
    conn = sqlite3.connect(sciezka)
    cur = conn.execute(
        "INSERT INTO model_log (match_date, team_home, team_away, model_tip)"
        " VALUES (?, ?, ?, ?)",
        (data, home, away, tip),
    )
    conn.commit()
    wpis_id = cur.lastrowid
    conn.close()
    return int(wpis_id or 0)


def _wiersz(sciezka: str, wpis_id: int):
    conn = sqlite3.connect(sciezka)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM model_log WHERE id = ?", (wpis_id,)).fetchone()
    conn.close()
    return r


def _w_kolejce(wpis_id: int) -> bool:
    return any(w["id"] == wpis_id for w in kl.pobierz_nierozliczone(dni_wstecz=3650))


# ── sedno: koniec nieskończonej pętli ───────────────────────────────────────


def test_wynik_po_dogrywce_zapisuje_sie_i_wychodzi_z_kolejki(db):
    """Wpis wraca do kolejki tylko dopóki wyniku NIE MAMY."""
    wpis_id = _wstaw(db)
    assert _w_kolejce(wpis_id), "wpis bez wyniku ma czekać w kolejce"

    zapisano = kl.zapisz_wynik(wpis_id, "5-1aet", "1")

    assert zapisano is False, "dogrywki nie liczymy jako rozliczonej"
    assert not _w_kolejce(wpis_id), "wpis z wynikiem nie może wracać w nieskończoność"


def test_dogrywka_nie_dostaje_trafnosci(db):
    """Zero zamiast NULL zafałszowałoby kalibrację: „nie wiemy" to nie
    „model się pomylił". Wynik zapisujemy, ocen NIE."""
    wpis_id = _wstaw(db)
    kl.zapisz_wynik(wpis_id, "5-1aet", "1")

    r = _wiersz(db, wpis_id)
    assert r["actual_result"] == "5-1aet"
    assert r["tip_correct"] is None
    assert r["over25_correct"] is None
    assert r["btts_correct"] is None
    assert r["draw_correct"] is None


def test_karne_traktowane_tak_samo_jak_dogrywka(db):
    """FlashScore oddał realnie '3-3 (Pen- 5-6)' — ten sam problem, inny zapis."""
    wpis_id = _wstaw(db, "VSG Altglienicke", "VfL Wolfsburg")
    assert kl.zapisz_wynik(wpis_id, "3-3 (Pen- 5-6)", "1") is False
    assert not _w_kolejce(wpis_id)


def test_brak_wyniku_zostawia_wpis_w_kolejce(db):
    """KONTROLA NEGATYWNA. Mecz nierozegrany albo źródło go nie zna — wpis MUSI
    wrócić jutro. Bez tego testu „wyjście z kolejki" dałoby się zrobić przez
    wyrzucanie wszystkiego."""
    wpis_id = _wstaw(db)
    assert kl.zapisz_wynik(wpis_id, None, "1") is False
    assert _wiersz(db, wpis_id)["actual_result"] is None
    assert _w_kolejce(wpis_id)


def test_pusty_string_to_tez_brak_wyniku(db):
    """Źródło potrafi oddać `''` zamiast None — to dalej „nie wiemy"."""
    wpis_id = _wstaw(db)
    kl.zapisz_wynik(wpis_id, "", "1")
    assert _w_kolejce(wpis_id)


def test_normalny_wynik_dalej_rozlicza_sie_w_pelni(db):
    """REGRES ścieżki zdrowej — cztery rynki naraz, wpis znika z kolejki."""
    wpis_id = _wstaw(db)
    assert kl.zapisz_wynik(wpis_id, "3-1", "1") is True

    r = _wiersz(db, wpis_id)
    assert r["actual_result"] == "3-1"
    assert r["tip_correct"] == 1
    assert r["over25_correct"] == 1
    assert r["btts_correct"] == 1
    assert r["draw_correct"] == 0
    assert not _w_kolejce(wpis_id)


def test_wpis_bez_typu_nie_znika_po_cichu(db):
    """Brak `model_tip` to nasz błąd zapisu, nie właściwość meczu — taki wiersz
    ma zostać widoczny w kolejce, a nie zniknąć z pełnym `actual_result`."""
    wpis_id = _wstaw(db, tip="")
    assert kl.zapisz_wynik(wpis_id, "3-1", "") is False
    assert _w_kolejce(wpis_id), "brak typu nie może uchodzić za mecz nierozliczalny"


# ── sprzężenie z rozliczaniem kuponów ───────────────────────────────────────


def test_dogrywka_z_model_log_nie_blokuje_zrodel_zewnetrznych(db):
    """Po tej zmianie `model_log` PO RAZ PIERWSZY trzyma wyniki po dogrywce,
    więc `wynik_z_model_log` mógłby je podać rozliczaniu kuponów — a tam
    `elif` przerwałby łańcuch i zewnętrzne źródło (mające wynik regulaminowy)
    nie zostałoby zapytane. Kupon utknąłby przez dane, które właśnie dodaliśmy.

    Kontrakt tej funkcji brzmi „daj wynik, którym da się rozliczyć"."""
    wpis_id = _wstaw(db)
    kl.zapisz_wynik(wpis_id, "5-1aet", "1")

    assert ml.wynik_z_model_log("LASK", "Celtic", DATA) is None


def test_normalny_wynik_z_model_log_dalej_wraca(db):
    """Kontrola pozytywna do testu wyżej."""
    wpis_id = _wstaw(db)
    kl.zapisz_wynik(wpis_id, "3-1", "1")
    assert ml.wynik_z_model_log("LASK", "Celtic", DATA) == "3-1"
