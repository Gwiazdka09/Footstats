"""
tests/test_daily_io.py — testy dla footstats.core.daily_io._zapisz_kupon_do_db.

Funkcja jest czystym glue nad coupon_tracker/bankroll/admin_user (już
przetestowanymi modułami) — tutaj mockujemy te zależności przez monkeypatch,
żeby zweryfikować logikę sklejania (DRAFT/FINAL/promote/fallback/błędy)
bez dotykania jakiejkolwiek bazy danych (SQLite czy Neon).
"""
from __future__ import annotations

from typing import Any

import pytest

from footstats.core import daily_io


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    *,
    admin_uid: int = 1,
    bankroll: float = 100.0,
    save_coupon_return: int | None = 42,
    draft_row: dict[str, Any] | None = None,
    promote_side_effect: Exception | None = None,
) -> dict[str, list]:
    """Podstawia mocki dla zależności i zwraca słownik z listami wywołań."""
    calls: dict[str, list] = {
        "save_coupon": [],
        "promote_to_active": [],
        "update_coupon_status": [],
        "process_bet": [],
        "init_coupon_tables": [],
    }

    def fake_init_coupon_tables() -> None:
        calls["init_coupon_tables"].append(())

    def fake_get_current_bankroll(user_id: int = 1) -> float:
        return bankroll

    def fake_resolve_admin_user_id(fallback: int = 1) -> int:
        return admin_uid

    def fake_save_coupon(**kwargs: Any) -> int | None:
        calls["save_coupon"].append(kwargs)
        return save_coupon_return

    def fake_get_draft_today(user_id: int = 1) -> dict[str, Any] | None:
        return draft_row

    def fake_promote_to_active(**kwargs: Any) -> None:
        calls["promote_to_active"].append(kwargs)
        if promote_side_effect is not None:
            raise promote_side_effect

    def fake_update_coupon_status(coupon_id: int, status: str) -> None:
        calls["update_coupon_status"].append((coupon_id, status))

    def fake_process_bet(stake: float, description: str = "", user_id: int = 1) -> float:
        calls["process_bet"].append((stake, description, user_id))
        return bankroll - stake

    monkeypatch.setattr(
        "footstats.core.coupon_tracker.init_coupon_tables", fake_init_coupon_tables
    )
    monkeypatch.setattr(
        "footstats.core.bankroll.get_current_bankroll", fake_get_current_bankroll
    )
    monkeypatch.setattr(
        "footstats.utils.admin_user.resolve_admin_user_id", fake_resolve_admin_user_id
    )
    monkeypatch.setattr("footstats.core.coupon_tracker.save_coupon", fake_save_coupon)
    monkeypatch.setattr(
        "footstats.core.coupon_tracker.get_draft_today", fake_get_draft_today
    )
    monkeypatch.setattr(
        "footstats.core.coupon_tracker.promote_to_active", fake_promote_to_active
    )
    monkeypatch.setattr(
        "footstats.core.coupon_tracker.update_coupon_status", fake_update_coupon_status
    )
    monkeypatch.setattr("footstats.core.bankroll.process_bet", fake_process_bet)

    return calls


def _kandydat(
    gospodarz: str = "Lech",
    goscie: str = "Legia",
    typ: str = "1",
    kurs: float = 1.8,
    decision_score: int = 70,
    data: str | None = "2026-06-20",
) -> dict[str, Any]:
    return {
        "gospodarz": gospodarz,
        "goscie": goscie,
        "typ": typ,
        "kurs": kurs,
        "decision_score": decision_score,
        "data": data,
    }


def test_draft_zapisuje_nowy_kupon_i_zwraca_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Faza DRAFT — zapisuje nowy rekord DRAFT, nie wywołuje promote/process_bet (stake=0)."""
    calls = _patch_common(monkeypatch, save_coupon_return=42)
    kandydaci = [_kandydat()]

    result = daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="draft", groq_resp="ok", stake=0.0, total_odds=1.8
    )

    assert result == 42
    assert len(calls["save_coupon"]) == 1
    assert calls["save_coupon"][0]["phase"] == "draft"
    assert calls["save_coupon"][0]["legs"][0]["home"] == "Lech"
    assert calls["save_coupon"][0]["legs"][0]["away"] == "Legia"
    assert calls["promote_to_active"] == []
    assert calls["process_bet"] == []


def test_final_z_istniejacym_draftem_promuje_do_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Faza FINAL z istniejącym dzisiejszym DRAFT — promote_to_active, brak nowego save_coupon."""
    draft_row = {"id": 7}
    calls = _patch_common(monkeypatch, draft_row=draft_row)
    kandydaci = [_kandydat()]

    result = daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="final", groq_resp="reasoning", stake=10.0, total_odds=1.8
    )

    assert result == 7
    assert len(calls["promote_to_active"]) == 1
    assert calls["promote_to_active"][0]["coupon_id"] == 7
    assert calls["save_coupon"] == []
    # promote_to_active nie idzie przez ścieżkę process_bet (return wcześniej)
    assert calls["process_bet"] == []


def test_final_bez_draftu_tworzy_nowy_kupon_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """Faza FINAL bez dzisiejszego DRAFT — fallback: nowy kupon + update_coupon_status(ACTIVE)."""
    calls = _patch_common(monkeypatch, draft_row=None, save_coupon_return=99)
    kandydaci = [_kandydat()]

    result = daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="final", groq_resp="r", stake=15.0, total_odds=2.1
    )

    assert result == 99
    assert len(calls["save_coupon"]) == 1
    assert calls["update_coupon_status"] == [(99, "ACTIVE")]
    assert calls["process_bet"] == [(15.0, "Kupon A ID=99 (final)", 1)]


def test_promote_to_active_blad_spada_do_nowego_kuponu_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gdy promote_to_active rzuca błąd — funkcja loguje i tworzy nowy kupon ACTIVE jako fallback."""
    draft_row = {"id": 3}
    calls = _patch_common(
        monkeypatch,
        draft_row=draft_row,
        save_coupon_return=55,
        promote_side_effect=RuntimeError("DB error"),
    )
    kandydaci = [_kandydat()]

    result = daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="final", groq_resp="r", stake=5.0, total_odds=1.5
    )

    assert result == 55
    assert len(calls["promote_to_active"]) == 1
    assert len(calls["save_coupon"]) == 1
    assert calls["update_coupon_status"] == [(55, "ACTIVE")]


def test_stake_zero_nie_wywoluje_process_bet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stake=0 (np. analiza bez realnego zakładu) — process_bet nie jest wywoływane."""
    calls = _patch_common(monkeypatch, save_coupon_return=1)
    kandydaci = [_kandydat()]

    daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="draft", groq_resp=None, stake=0.0, total_odds=1.5
    )

    assert calls["process_bet"] == []


def test_pusta_lista_kandydatow_uzywa_daty_dzisiejszej_i_zerowego_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pusta lista kandydatów — brak crasha, avg_score=0, match_date=dziś, legs=[]."""
    calls = _patch_common(monkeypatch, save_coupon_return=10)

    result = daily_io._zapisz_kupon_do_db(
        kandydaci=[], phase="draft", groq_resp=None, stake=0.0, total_odds=1.0
    )

    assert result == 10
    saved = calls["save_coupon"][0]
    assert saved["legs"] == []
    assert saved["decision_score"] == 0


def test_parsowanie_meczu_z_separatora_vs_gdy_brak_gospodarz_goscie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kandydat bez 'gospodarz'/'goscie' ale z polem 'mecz' (separator ' vs ') — parsuje home/away."""
    calls = _patch_common(monkeypatch, save_coupon_return=2)
    kandydaci = [{"mecz": "Wisla vs Cracovia", "typ": "X", "kurs": 3.2, "decision_score": 50}]

    daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="draft", groq_resp=None, stake=0.0, total_odds=3.2
    )

    leg = calls["save_coupon"][0]["legs"][0]
    assert leg["home"] == "Wisla"
    assert leg["away"] == "Cracovia"


def test_parsowanie_meczu_z_separatora_myslnik_gdy_brak_vs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kandydat z polem 'mecz' używającym separatora ' - ' (brak ' vs ') — też parsuje home/away."""
    calls = _patch_common(monkeypatch, save_coupon_return=3)
    kandydaci = [{"mecz": "Pogon - Slask", "typ": "2", "kurs": 2.5, "decision_score": 40}]

    daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="draft", groq_resp=None, stake=0.0, total_odds=2.5
    )

    leg = calls["save_coupon"][0]["legs"][0]
    assert leg["home"] == "Pogon"
    assert leg["away"] == "Slask"


def test_blad_save_coupon_jest_przechwytywany_i_zwraca_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wyjątek (ValueError/KeyError/TypeError/OSError) w trakcie zapisu — funkcja łapie i zwraca None."""
    _patch_common(monkeypatch)

    def fake_save_coupon_raises(**kwargs: Any) -> int | None:
        raise ValueError("zly format")

    monkeypatch.setattr(
        "footstats.core.coupon_tracker.save_coupon", fake_save_coupon_raises
    )
    kandydaci = [_kandydat()]

    result = daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="draft", groq_resp=None, stake=0.0, total_odds=1.5
    )

    assert result is None


def test_save_coupon_zwraca_none_nie_wywoluje_process_bet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gdy save_coupon zwróci None (zapis nieudany) — process_bet i update_coupon_status nie są wołane."""
    calls = _patch_common(monkeypatch, save_coupon_return=None)
    kandydaci = [_kandydat()]

    result = daily_io._zapisz_kupon_do_db(
        kandydaci=kandydaci, phase="final", groq_resp=None, stake=20.0, total_odds=1.5
    )

    assert result is None
    assert calls["process_bet"] == []
    assert calls["update_coupon_status"] == []
