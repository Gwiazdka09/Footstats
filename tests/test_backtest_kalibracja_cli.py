"""test_backtest_kalibracja_cli.py — kalibracja do promptu + CLI backtestu.

PO CO:
  * `pobierz_kalibracje_backtest()` produkuje string wstrzykiwany do promptu
    Groqa. Gdy cicho zwroci "", model traci informacje o wlasnej skutecznosci
    per rynek i nikt tego nie zauwazy po wyniku.
  * `_sprawdz_auto_trening()` odpala PODPROCES z trenerem co N wynikow. Bez
    testu nie bylo wiadomo, czy odpala sie w ogole i czy nie odpala za czesto.
  * `_cli_*` renderuja raporty, ktore user czyta — i wywalaly sie na `None`
    w polach accuracy (typowy stan przy swiezej bazie).

`subprocess.Popen` i Telegram sa podstawione WSZEDZIE — test nie ma prawa
odpalic trenera ani wyslac wiadomosci.
"""
from __future__ import annotations

import subprocess

import pytest

import footstats.core.backtest as bt


def _rynek(total=10, correct=7, accuracy_pct=70.0, avg_odds=1.9) -> dict:
    return {"total": total, "correct": correct,
            "accuracy_pct": accuracy_pct, "avg_odds": avg_odds}


def _stats(**nadpisz) -> dict:
    baza = {
        "date_from": "2026-05-01", "date_to": "2026-07-30",
        "total_tips": 100, "evaluated": 90, "correct": 55,
        "accuracy_pct": 61.1, "roi_pct": 4.2,
        "best_market": "Over 2.5", "worst_market": "X", "best_league": "ENG-Premier League",
        "by_market": {"Over 2.5": _rynek(), "X": _rynek(accuracy_pct=30.0)},
        "by_league": {"ENG-Premier League": _rynek()},
        "by_confidence_band": {"60-70%": _rynek()},
        "by_kupon": {"A": _rynek()},
    }
    baza.update(nadpisz)
    return baza


# ── pobierz_kalibracje_backtest ─────────────────────────────────────────────

def test_sklada_string_z_rynkow_i_roi(monkeypatch):
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(
        by_market={"1": _rynek(total=80, accuracy_pct=58.0),
                   "Over 2.5": _rynek(total=150, accuracy_pct=73.0)},
        roi_pct=4.2,
    ))
    wynik = bt.pobierz_kalibracje_backtest()

    assert "1 acc=58%(n=80)" in wynik
    assert "Over 2.5 acc=73%(n=150)" in wynik
    assert "ROI=+4.2%" in wynik


def test_odsiewa_rynki_ponizej_min_n(monkeypatch):
    """Male proby to szum — nie wolno nimi kalibrowac modelu."""
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(
        by_market={"1": _rynek(total=2), "BTTS": _rynek(total=40)},
    ))
    wynik = bt.pobierz_kalibracje_backtest(min_n=5)

    assert "BTTS" in wynik
    assert "1 acc=" not in wynik


def test_pusty_string_gdy_zadnego_rynku_nie_starczy(monkeypatch):
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(
        by_market={"1": _rynek(total=1)}))
    assert bt.pobierz_kalibracje_backtest(min_n=5) == ""


def test_kolejnosc_rynkow_wg_ustalonej_listy(monkeypatch):
    """1X2 przed rynkami golowymi — stala kolejnosc ulatwia modelowi czytanie."""
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(
        by_market={"BTTS": _rynek(total=30), "1": _rynek(total=30),
                   "X": _rynek(total=30)},
        roi_pct=None,
    ))
    wynik = bt.pobierz_kalibracje_backtest()
    assert wynik.index("1 acc") < wynik.index("X acc") < wynik.index("BTTS acc")


def test_nieznany_rynek_laduje_na_koncu(monkeypatch):
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(
        by_market={"EGZOTYCZNY": _rynek(total=30), "1": _rynek(total=30)},
        roi_pct=None,
    ))
    wynik = bt.pobierz_kalibracje_backtest()
    assert wynik.index("1 acc") < wynik.index("EGZOTYCZNY acc")


def test_brak_roi_pomijany(monkeypatch):
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(roi_pct=None))
    assert "ROI=" not in bt.pobierz_kalibracje_backtest()


def test_rynek_bez_accuracy_pomijany(monkeypatch):
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(
        by_market={"1": _rynek(accuracy_pct=None), "X": _rynek(accuracy_pct=50.0)},
        roi_pct=None,
    ))
    wynik = bt.pobierz_kalibracje_backtest()
    assert "1 acc" not in wynik
    assert "X acc=50%" in wynik


def test_blad_bazy_daje_pusty_string_zamiast_wysypki(monkeypatch):
    """Padnieta baza nie moze zatrzymac budowania promptu."""
    def _wybuch(days=30):
        raise RuntimeError("DB down")

    monkeypatch.setattr(bt, "get_stats", _wybuch)
    assert bt.pobierz_kalibracje_backtest() == ""


def test_przekazuje_liczbe_dni_do_get_stats(monkeypatch):
    przechwycone = {}
    monkeypatch.setattr(bt, "get_stats",
                        lambda days=30: przechwycone.update(days=days) or _stats())
    bt.pobierz_kalibracje_backtest(dni=45)
    assert przechwycone["days"] == 45


# ── _sprawdz_auto_trening ───────────────────────────────────────────────────

class _Conn:
    def __init__(self, n: int):
        self._n = n

    def execute(self, sql, params=()):
        return self

    def fetchone(self):
        return [self._n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def auto_trening(monkeypatch):
    """Odcina podproces i Telegram; zwraca liste odpalen."""
    odpalone: list = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: odpalone.append(a))

    import footstats.utils.telegram_notify as tg
    monkeypatch.setattr(tg, "telegram_dostepny", lambda: False)
    return odpalone


@pytest.mark.parametrize("n", [20, 40, 200])
def test_odpala_trening_na_wielokrotnosci(monkeypatch, auto_trening, n, capsys):
    monkeypatch.setattr(bt, "_connect", lambda: _Conn(n))
    bt._sprawdz_auto_trening()

    assert len(auto_trening) == 1
    assert "footstats.ai.trainer" in auto_trening[0][0]
    assert f"n={n}" in capsys.readouterr().out


@pytest.mark.parametrize("n", [0, 1, 19, 21, 39])
def test_nie_odpala_poza_wielokrotnoscia(monkeypatch, auto_trening, n):
    monkeypatch.setattr(bt, "_connect", lambda: _Conn(n))
    bt._sprawdz_auto_trening()
    assert auto_trening == []


def test_zero_wynikow_nie_odpala_treningu(monkeypatch, auto_trening):
    """n=0 jest podzielne przez 20 — musi byc jawnie wykluczone."""
    monkeypatch.setattr(bt, "_connect", lambda: _Conn(0))
    bt._sprawdz_auto_trening()
    assert auto_trening == []


def test_blad_startu_podprocesu_zglaszany_ale_nie_wywala(monkeypatch, capsys):
    def _padnij(*a, **k):
        raise OSError("brak interpretera")

    monkeypatch.setattr(bt, "_connect", lambda: _Conn(20))
    monkeypatch.setattr(subprocess, "Popen", _padnij)
    import footstats.utils.telegram_notify as tg
    monkeypatch.setattr(tg, "telegram_dostepny", lambda: False)

    bt._sprawdz_auto_trening()
    assert "Auto-trening start failed" in capsys.readouterr().out


def test_blad_bazy_nie_wywala_zapisu_wyniku(monkeypatch, auto_trening):
    """Ta funkcja jest wolana PO update_result — jej awaria nie moze cofnac zapisu."""
    def _wybuch():
        raise RuntimeError("DB down")

    monkeypatch.setattr(bt, "_connect", _wybuch)
    bt._sprawdz_auto_trening()          # nie rzuca


def test_telegram_wysylany_gdy_dostepny(monkeypatch):
    monkeypatch.setattr(bt, "_connect", lambda: _Conn(20))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)

    wyslane = []
    import footstats.utils.telegram_notify as tg
    monkeypatch.setattr(tg, "telegram_dostepny", lambda: True)
    monkeypatch.setattr(tg, "_send", wyslane.append)

    bt._sprawdz_auto_trening()
    assert len(wyslane) == 1
    assert "Auto-trening" in wyslane[0]


# ── _cli_stats ──────────────────────────────────────────────────────────────

def test_cli_stats_brak_danych(monkeypatch, capsys):
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(total_tips=0))
    bt._cli_stats()
    assert "Brak danych" in capsys.readouterr().out


def test_cli_stats_renderuje_komplet(monkeypatch, capsys):
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats())
    bt._cli_stats(days=60)
    out = capsys.readouterr().out

    assert "ostatnie 60 dni" in out
    assert "Typy łącznie:  100" in out
    assert "61.1%" in out and "4.2%" in out
    assert "Over 2.5" in out                 # najlepszy rynek
    assert "--- Rynki ---" in out
    assert "--- Pewność AI ---" in out
    assert "--- Kupony ---" in out


def test_cli_stats_znosi_brak_accuracy(monkeypatch, capsys):
    """Swieza baza ma accuracy_pct=None — CLI ma pokazac kreske, nie paść."""
    monkeypatch.setattr(bt, "get_stats", lambda days=30: _stats(
        accuracy_pct=None, roi_pct=None,
        by_market={"1": _rynek(accuracy_pct=None, avg_odds=None)},
        best_market=None, worst_market=None, best_league=None,
        by_confidence_band={}, by_kupon={},
    ))
    bt._cli_stats()
    assert "—" in capsys.readouterr().out


# ── _cli_pending ────────────────────────────────────────────────────────────

def test_cli_pending_pusto(monkeypatch, capsys):
    monkeypatch.setattr(bt, "get_pending_results", lambda: [])
    bt._cli_pending()
    assert "Wszystko uzupełnione" in capsys.readouterr().out


def test_cli_pending_listuje_mecze(monkeypatch, capsys):
    monkeypatch.setattr(bt, "get_pending_results", lambda: [{
        "id": 7, "match_date": "2026-07-31", "team_home": "Legia",
        "team_away": "Lech", "league": "POL", "ai_tip": "1",
        "ai_confidence": 62, "odds": 1.85, "kupon_type": "A",
    }])
    bt._cli_pending()
    out = capsys.readouterr().out
    assert "Legia vs Lech" in out
    assert "backtest update" in out


def test_cli_pending_znosi_puste_pola(monkeypatch, capsys):
    monkeypatch.setattr(bt, "get_pending_results", lambda: [{
        "id": 1, "match_date": "2026-07-31", "team_home": "A", "team_away": "B",
        "league": None, "ai_tip": "X", "ai_confidence": 50,
        "odds": None, "kupon_type": None,
    }])
    bt._cli_pending()
    assert "—" in capsys.readouterr().out


# ── _cli_update ─────────────────────────────────────────────────────────────

def test_cli_update_odrzuca_nieliczbowe_id(capsys):
    with pytest.raises(SystemExit) as exc:
        bt._cli_update("abc", "2:1")
    assert exc.value.code == 1
    assert "musi być liczbą" in capsys.readouterr().out


def test_cli_update_zglasza_blad_walidacji(monkeypatch, capsys):
    def _wybuch(mid, wynik, match_stats=None):
        raise ValueError("nieznany format wyniku")

    monkeypatch.setattr(bt, "update_result", _wybuch)
    with pytest.raises(SystemExit) as exc:
        bt._cli_update("5", "zle")
    assert exc.value.code == 1
    assert "nieznany format wyniku" in capsys.readouterr().out


def test_cli_update_drukuje_podsumowanie(monkeypatch, capsys):
    monkeypatch.setattr(bt, "update_result", lambda mid, wynik, match_stats=None: {
        "id": mid, "ai_tip": "1", "actual_result": wynik, "status": "TRAFIONY",
    })
    bt._cli_update("5", "2:1")
    out = capsys.readouterr().out
    assert "Zaktualizowano ID=5" in out
    assert "2:1" in out
    assert "TRAFIONY" in out
