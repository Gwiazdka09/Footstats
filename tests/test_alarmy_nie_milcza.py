"""Alarm, który milczy przy własnej awarii, jest gorszy niż jego brak.

ZNALEZIONE 2026-08-24 przy J1 (audyt milczących `except`). Dwie funkcje zdrowia
w `telegram_notify` kończyły się dosłownie tak:

    except (OSError, ValueError, RuntimeError):
        pass
    return False

`False` znaczy „nie wysłano alertu", czyli w praktyce „jest dobrze". Więc gdy
zapytanie do bazy padło — brak migracji, zerwane połączenie, dryf schematu —
`check_and_alert_agent_down` i `check_and_alert_accuracy` odpowiadały „wszystko gra"
i nie zostawiały po sobie ANI JEDNEJ linijki w logach.

To ten sam kształt, który 24.08 wyszedł pięć razy w ciągu jednego dnia: kupony stały
osiem dni przy `exit=0`, próg selekcji nigdy nie działał, football-data nigdy nie
odpowiadało. Różnica jest taka, że tutaj milczy sam czujnik dymu.

Wymagamy: przy awarii własnego sprawdzenia funkcja **loguje** i dopiero wtedy zwraca
`False`. Log jest jedynym śladem, jaki zostaje — Cloud Logging go zbierze, a
`pipeline-health` i raport dzienny pytają o inne sygnały, więc bez tej linijki
awaria czujnika jest niewidoczna dla wszystkiego.
"""
from __future__ import annotations

import logging

import pytest

import footstats.utils.telegram_notify as tg


class _RzucajacaBaza:
    """Kontekst bazy, który wysypuje się dokładnie tam, gdzie robi to produkcja."""

    def __init__(self, wyjatek: BaseException) -> None:
        self._wyjatek = wyjatek

    def __enter__(self):
        raise self._wyjatek

    def __exit__(self, *a):
        return False


@pytest.fixture
def bez_wysylki(monkeypatch):
    """Żaden test nie może dotknąć realnego bota."""
    wyslane: list[str] = []
    monkeypatch.setattr(tg, "_send", lambda *a, **k: wyslane.append("x") or True)
    monkeypatch.setattr(tg, "send_alert",
                        lambda *a, **k: wyslane.append("alert") or True)
    return wyslane


def _podstaw_baze(monkeypatch, wyjatek: BaseException) -> None:
    import footstats.utils.db as db
    monkeypatch.setattr(db, "connect", lambda *a, **k: _RzucajacaBaza(wyjatek))


WYJATKI = [OSError("zerwane polaczenie"), RuntimeError("brak DATABASE_URL"),
           ValueError("dryf schematu")]


# ── agent down ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("wyjatek", WYJATKI)
def test_agent_down_loguje_wlasna_awarie(monkeypatch, caplog, bez_wysylki, wyjatek):
    _podstaw_baze(monkeypatch, wyjatek)

    with caplog.at_level(logging.WARNING, logger=tg.log.name):
        wynik = tg.check_and_alert_agent_down()

    assert wynik is False
    assert caplog.records, (
        "sprawdzenie 'agent down' padlo i nie zostawilo sladu — "
        "brak alertu wyglada wtedy identycznie jak zdrowy stan"
    )


def test_agent_down_nie_udaje_ze_sprawdzil(monkeypatch, caplog, bez_wysylki):
    """W logu ma byc widac, ze to awaria SPRAWDZENIA, nie brak problemu."""
    _podstaw_baze(monkeypatch, OSError("zerwane polaczenie"))

    with caplog.at_level(logging.WARNING, logger=tg.log.name):
        tg.check_and_alert_agent_down()

    tresc = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "zerwane polaczenie" in tresc, tresc


# ── accuracy drop ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("wyjatek", WYJATKI)
def test_accuracy_loguje_wlasna_awarie(monkeypatch, caplog, bez_wysylki, wyjatek):
    _podstaw_baze(monkeypatch, wyjatek)

    with caplog.at_level(logging.WARNING, logger=tg.log.name):
        wynik = tg.check_and_alert_accuracy()

    assert wynik is False
    assert caplog.records, "sprawdzenie accuracy padlo w ciszy"


# ── powiadomienie per-user ─────────────────────────────────────────────────

def test_wiadomosc_do_uzytkownika_loguje_blad_bazy(monkeypatch, caplog, bez_wysylki):
    """Łapało `except Exception` i zwracało False bez słowa — użytkownik nie dostaje
    powiadomienia, a w logach pusto."""
    _podstaw_baze(monkeypatch, OSError("baza padla"))

    with caplog.at_level(logging.WARNING, logger=tg.log.name):
        wynik = tg.send_message_to_user(1, "test")

    assert wynik is False
    assert caplog.records, "wysylka do uzytkownika padla w ciszy"


def test_wiadomosc_do_uzytkownika_nie_lapie_wszystkiego(monkeypatch, bez_wysylki):
    """`except Exception` ukrywalby tez blad w NASZYM kodzie (literowka, zly typ).
    Takie maja krzyczec, nie znikac w 'return False'."""
    _podstaw_baze(monkeypatch, KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        tg.send_message_to_user(1, "test")


# ── stan zdrowy zostaje bez zmian ──────────────────────────────────────────

def test_zdrowa_baza_nie_generuje_szumu(monkeypatch, caplog, bez_wysylki):
    """Alarm, ktory loguje przy KAZDYM przebiegu, tez przestaje cokolwiek znaczyc."""
    from datetime import datetime

    wiersz = {"last": datetime.now(), "cnt": 0, "won": 0}

    class _Conn:
        def execute(self, *a, **k):
            class _C:
                def fetchone(self):
                    return wiersz
            return _C()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import footstats.utils.db as db
    monkeypatch.setattr(db, "connect", lambda *a, **k: _Conn())

    with caplog.at_level(logging.WARNING, logger=tg.log.name):
        assert tg.check_and_alert_agent_down() is False

    assert not caplog.records, [r.getMessage() for r in caplog.records]
