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


# ── streak i mnoznik stawki ─────────────────────────────────────────────────
#
# Drugi przystanek tej samej podrozy: po naprawie bankrolla przebieg padl
# linie nizej, na `get_loss_streak`. Te odczyty sa niegrozne dla produkcji
# (SELECT), ale wymuszaja polaczenie z baza, wiec caly potok dalej nie dawal
# sie sprawdzic bez produkcji.

def test_dry_run_nie_pyta_bazy_o_streak(monkeypatch):
    def _wybuch(**kw):
        raise AssertionError("dry-run nie ma prawa dotknac bazy dla streaka")

    monkeypatch.setattr("footstats.core.bankroll.get_loss_streak", _wybuch)
    monkeypatch.setattr("footstats.core.bankroll.get_stake_multiplier", _wybuch)

    assert da._streak_do_przebiegu(_Args(dry_run=True), admin_uid=1) == (0, 1.0)


def test_zwykly_przebieg_czyta_streak(monkeypatch):
    """Kontrola: redukcja stawek po serii porazek musi dzialac na produkcji."""
    monkeypatch.setattr("footstats.core.bankroll.get_loss_streak",
                        lambda user_id: 4)
    monkeypatch.setattr("footstats.core.bankroll.get_stake_multiplier",
                        lambda user_id: 0.5)

    assert da._streak_do_przebiegu(_Args(dry_run=False), admin_uid=3) == (4, 0.5)


def test_dry_run_nie_udaje_serii_porazek(monkeypatch):
    """Neutralne wartosci, nie wymyslone: 0 przegranych i mnoznik 1.0 nie
    zmieniaja stawek, wiec podglad pokazuje stawki takie, jak je podano."""
    monkeypatch.setattr("footstats.core.bankroll.get_loss_streak",
                        lambda user_id: pytest.fail("nie wolno"))
    monkeypatch.setattr("footstats.core.bankroll.get_stake_multiplier",
                        lambda user_id: pytest.fail("nie wolno"))

    streak, mult = da._streak_do_przebiegu(_Args(dry_run=True), admin_uid=1)

    assert streak < 3, "prog redukcji stawek to 3 — podglad nie moze go przekroczyc"
    assert mult == 1.0


# ── Krok 0d: odswiezenie sedziow z ZawodTyper ───────────────────────────────
#
# Trzeci przypadek tej samej klasy. `fetch_referees_zawodtyper` woła
# `upsert_referee`, czyli INSERT/UPDATE do bazy — i chodziło to takze w dry-run,
# poza jakakolwiek bramka. Do tego Playwright, wiec podglad placil za scraping,
# ktorego wynik i tak nie mial gdzie trafic.

def test_dry_run_nie_odswieza_sedziow(monkeypatch):
    def _wybuch():
        raise AssertionError("dry-run nie ma prawa pisac do bazy sedziow")

    monkeypatch.setattr(
        "footstats.scrapers.zawodtyper_referees.fetch_referees_zawodtyper", _wybuch)

    da._odswiez_sedziow(_Args(dry_run=True))   # nie moze rzucic


def test_zwykly_przebieg_dalej_odswieza_sedziow(monkeypatch):
    """Kontrola: statystyki sedziow maja sie aktualizowac raz dziennie."""
    wywolano = []
    monkeypatch.setattr(
        "footstats.scrapers.zawodtyper_referees.fetch_referees_zawodtyper",
        lambda: wywolano.append(True))

    da._odswiez_sedziow(_Args(dry_run=False))

    assert wywolano == [True]


def test_awaria_zrodla_sedziow_nie_zatrzymuje_przebiegu(monkeypatch):
    """ZawodTyper to zewnetrzna strona — jej padniecie nie moze kosztowac
    calego dziennego przebiegu."""
    def _wybuch():
        raise OSError("zawodtyper nie odpowiada")

    monkeypatch.setattr(
        "footstats.scrapers.zawodtyper_referees.fetch_referees_zawodtyper", _wybuch)

    da._odswiez_sedziow(_Args(dry_run=False))   # nie moze rzucic
