"""Stop-loss na saldzie wirtualnym nie zatrzymuje potoku (domyslnie).

Od 1.11 final konczyl sie po ~100 s przez `return` przed KROK 0, z exit 0, bez
predykcji i bez `model_log`. Testy przechodza przez `daily_agent.main()` i pytaja
o ZACHOWANIE: czy przebieg doszedl do kroku po stop-lossie (sentinel na
`_streak_do_przebiegu`), czy zostal przerwany.

Seam: bankroll i admin_user importowane lokalnie w funkcji -> patch ZRODLA;
`_streak_do_przebiegu`, `_wyslij_alarm`, `_bankroll_do_przebiegu` to globale
modulu daily_agent -> patch w daily_agent.
"""
from __future__ import annotations

import logging
import sys

import pytest

import footstats.core.bankroll as br
import footstats.daily_agent as da
from footstats.core import alarmy_jakosci as aj


class _Doszlo(Exception):
    """Sentinel: przebieg przeszedl stop-loss i poszedl dalej."""


@pytest.fixture
def agent(monkeypatch):
    stan = {"alarmy": [], "auto_pause": 0}
    monkeypatch.delenv("STOP_LOSS_ZATRZYMUJE", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr("footstats.core.logging_config.skonfiguruj_logi_json",
                        lambda *a, **k: None)
    monkeypatch.setattr("footstats.utils.admin_user.resolve_admin_user_id", lambda: 1)
    monkeypatch.setattr(da, "_bankroll_do_przebiegu", lambda a, u: 1000.0)
    monkeypatch.setattr(da, "_wyslij_alarm",
                        lambda nazwa, *a, **k: stan["alarmy"].append(nazwa))

    def _dalej(*a, **k):
        raise _Doszlo

    monkeypatch.setattr(da, "_streak_do_przebiegu", _dalej)
    monkeypatch.setattr(br, "is_agent_paused", lambda: False)
    monkeypatch.setattr(br, "check_daily_stop_loss", lambda user_id=1: False)
    monkeypatch.setattr(br, "check_weekly_alert", lambda user_id=1: False)
    monkeypatch.setattr(br, "get_weekly_drawdown", lambda user_id=1: 0.25)
    monkeypatch.setattr(br, "get_daily_loss", lambda user_id=1: 150.0)

    def _pauza(user_id=1):
        stan["auto_pause"] += 1
        return True

    monkeypatch.setattr(br, "check_and_auto_pause", _pauza)
    monkeypatch.setattr(sys, "argv", ["daily_agent", "--faza", "final"])
    return stan


def _uruchom_main() -> bool:
    """True = przebieg doszedl dalej niz stop-loss, False = main wrocil wczesniej."""
    try:
        da.main()
    except _Doszlo:
        return True
    return False


def test_flaga_domyslnie_wylaczona(monkeypatch):
    monkeypatch.delenv("STOP_LOSS_ZATRZYMUJE", raising=False)
    assert br.stop_loss_zatrzymuje() is False


@pytest.mark.parametrize("wartosc,oczekiwane", [("1", True), ("0", False), ("", False), ("true", False)])
def test_flaga_czytana_przy_kazdym_wywolaniu(monkeypatch, wartosc, oczekiwane):
    monkeypatch.setenv("STOP_LOSS_ZATRZYMUJE", wartosc)
    assert br.stop_loss_zatrzymuje() is oczekiwane


def test_drawdown_tygodniowy_nie_konczy_main_domyslnie(agent, monkeypatch, caplog):
    monkeypatch.setattr(br, "check_weekly_alert", lambda user_id=1: True)
    with caplog.at_level(logging.WARNING, logger="footstats.daily_agent"):
        assert _uruchom_main() is True
    assert agent["alarmy"] == []
    assert agent["auto_pause"] == 0
    tekst = caplog.text
    assert "wirtualne" in tekst and "STOP_LOSS_ZATRZYMUJE" in tekst and "25.0%" in tekst


def test_strata_dzienna_nie_konczy_main_domyslnie(agent, monkeypatch, caplog):
    monkeypatch.setattr(br, "check_daily_stop_loss", lambda user_id=1: True)
    with caplog.at_level(logging.WARNING, logger="footstats.daily_agent"):
        assert _uruchom_main() is True
    assert agent["alarmy"] == []
    assert "wirtualne" in caplog.text and "150.00" in caplog.text


def test_flaga_1_dzienna_strata_przerywa(agent, monkeypatch):
    monkeypatch.setenv("STOP_LOSS_ZATRZYMUJE", "1")
    monkeypatch.setattr(br, "check_daily_stop_loss", lambda user_id=1: True)
    assert _uruchom_main() is False


def test_flaga_1_drawdown_przerywa_i_alarmuje(agent, monkeypatch):
    monkeypatch.setenv("STOP_LOSS_ZATRZYMUJE", "1")
    assert _uruchom_main() is False
    assert agent["alarmy"] == ["send_stop_loss_alert"]
    assert agent["auto_pause"] == 1


def test_reczna_pauza_dalej_przerywa(agent, monkeypatch):
    monkeypatch.setattr(br, "is_agent_paused", lambda: True)
    assert _uruchom_main() is False
    assert agent["alarmy"] == ["send_alert"]


def test_dry_run_bez_zmian(agent, monkeypatch):
    monkeypatch.setenv("STOP_LOSS_ZATRZYMUJE", "1")
    monkeypatch.setattr(br, "check_daily_stop_loss", lambda user_id=1: True)
    monkeypatch.setattr(br, "is_agent_paused", lambda: True)
    monkeypatch.setattr(sys, "argv", ["daily_agent", "--faza", "final", "--dry-run"])
    assert _uruchom_main() is True
    assert agent["alarmy"] == [] and agent["auto_pause"] == 0


def test_alarm_telegram_nie_wspomina_dashboardu(monkeypatch):
    import footstats.utils.telegram_notify as tg
    wyslane: list[str] = []
    monkeypatch.setattr(tg, "_send", lambda text, **kw: wyslane.append(text) or True)
    tg.send_stop_loss_alert(0.25, 800.0)
    assert "dashboard" not in wyslane[0].lower()
    assert "wirtualne" in wyslane[0] and "STOP_LOSS_ZATRZYMUJE=0" in wyslane[0]


class _K:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, n24):
        self.n24 = n24

    def execute(self, sql, params=()):
        plaski = " ".join(sql.split())
        if "coupons" in plaski:
            return _K({"mapowalne": 0, "z_clv": 0})
        if "72 hours" in plaski:
            return _K({"n": 0, "tn": 0})
        return _K({"n": self.n24, "pois": 0, "pois_lambda": 0})


def test_alarm_zero_wierszy_model_log():
    powody, _ = aj.sprawdz_jakosc(_Conn(0))
    assert len(powody) == 1 and "zero nowych ocen" in powody[0]
    assert "dzień bez meczów" in powody[0]


def test_alarm_zero_wierszy_milczy_gdy_sa_oceny():
    powody, _ = aj.sprawdz_jakosc(_Conn(5))
    assert powody == []
