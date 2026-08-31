"""`--dry-run` obiecuje "nie zapisuje do DB" — i musi tego dotrzymac.

Zmierzone 31.08 przy probie odpalenia fazy final lokalnie z wyzerowanym
DATABASE_URL: przebieg padl na `get_current_bankroll` w linii 763, czyli
PRZED jakakolwiek bramka `if not args.dry_run`.

Gorzej niz padniecie: `get_current_bankroll` wola `init_bankroll_tables`,
ktore przy braku wiersza robi INSERT do `bankroll_state`. Podglad mial wiec
sciezke zapisu do prod DB, uruchamiana zanim ktorykolwiek warunek dry-run
zdazyl cokolwiek zablokowac.

Skutek dla pracy: nie da sie zweryfikowac calego potoku bez dotykania
produkcji, wiec kazda zmiana w fazie final jest sprawdzalna dopiero na
zywym przebiegu o 11:00 UTC.
"""
from __future__ import annotations

import pytest

from footstats import daily_agent as da
from footstats.config import AGENT_BANKROLL


class _Args:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run


def test_dry_run_nie_pyta_bazy_o_bankroll(monkeypatch):
    def _wybuch(**kw):
        raise AssertionError("dry-run nie ma prawa dotknac bazy dla bankrolla")

    monkeypatch.setattr("footstats.core.bankroll.get_current_bankroll", _wybuch)

    assert da._bankroll_do_przebiegu(_Args(dry_run=True), admin_uid=1) == AGENT_BANKROLL


def test_zwykly_przebieg_dalej_czyta_realne_saldo(monkeypatch):
    """Kontrola: naprawa nie moze odciac Kelly'ego od prawdziwego bankrolla."""
    monkeypatch.setattr("footstats.core.bankroll.get_current_bankroll",
                        lambda user_id: 1234.5)

    assert da._bankroll_do_przebiegu(_Args(dry_run=False), admin_uid=7) == 1234.5


def test_uzywa_podanego_user_id(monkeypatch):
    widziane = {}

    def _czytaj(user_id):
        widziane["uid"] = user_id
        return 100.0

    monkeypatch.setattr("footstats.core.bankroll.get_current_bankroll", _czytaj)
    da._bankroll_do_przebiegu(_Args(dry_run=False), admin_uid=99)

    assert widziane["uid"] == 99


def test_dry_run_zostawia_slad_w_logu(monkeypatch, caplog):
    """Liczba z configu zamiast realnego salda zmienia stawki Kelly'ego —
    czytajacy raport musi wiedziec, ze patrzy na podstawiona wartosc."""
    import logging

    monkeypatch.setattr("footstats.core.bankroll.get_current_bankroll",
                        lambda user_id: pytest.fail("nie wolno"))

    with caplog.at_level(logging.INFO):
        da._bankroll_do_przebiegu(_Args(dry_run=True), admin_uid=1)

    assert "dry" in caplog.text.lower()
