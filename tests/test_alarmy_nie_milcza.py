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


# ── Druga strona tego samego problemu: DORĘCZENIE alarmu ────────────────────
#
# Powyżej: czujnik, który milczy przy własnej awarii. Poniżej: wołający, który
# milczy, gdy alarm nie wyszedł. Znalezione 28.08 w `daily_agent.main()` —
# cztery miejsca o identycznym kształcie:
#
#     try:
#         from footstats.utils.telegram_notify import send_stop_loss_alert
#         send_stop_loss_alert(dd, bankroll)
#     except (ImportError, OSError, RuntimeError):
#         pass
#
# Najgorsze z nich siedziało pod `log.warning("ALERT cicha awaria: ...")`:
# wykrycie przebiegu BEZ EFEKTU logowało się poprawnie, a nieudane powiadomienie
# o tym wykryciu — już nie.

def test_nieudana_wysylka_alarmu_zostawia_slad(monkeypatch, caplog):
    from footstats import daily_agent
    import footstats.utils.telegram_notify as _tg

    def _padnij(*_a, **_k):
        raise OSError("timeout do API Telegrama")

    monkeypatch.setattr(_tg, "send_alert", _padnij, raising=False)
    with caplog.at_level(logging.WARNING):
        daily_agent._wyslij_alarm("send_alert", "stop-loss przeszedl niezauwazony", "t", "b")

    assert "ALARM NIEWYSLANY" in caplog.text
    assert "stop-loss przeszedl niezauwazony" in caplog.text


def test_brak_modulu_powiadomien_tez_zostawia_slad(monkeypatch, caplog):
    """Obraz bez `telegram_notify` wyglądał dotąd identycznie jak obraz,
    w którym po prostu nie było o czym alarmować."""
    import builtins
    from footstats import daily_agent

    prawdziwy = builtins.__import__

    def _bez(nazwa, *a, **k):
        if nazwa == "footstats.utils" or nazwa.startswith("footstats.utils.telegram"):
            raise ImportError("brak modulu w obrazie")
        return prawdziwy(nazwa, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _bez)
    with caplog.at_level(logging.WARNING):
        daily_agent._wyslij_alarm("send_alert", "skutek do zaraportowania", "t", "b")

    assert "ALARM NIEWYSLANY" in caplog.text


def test_literowka_w_nazwie_alarmu_to_blad_nie_cisza(caplog):
    """`getattr` po nazwie nie jest sprawdzany przez linter — gdyby ktoś zmienił
    nazwę funkcji w `telegram_notify`, wołanie zamieniłoby się w ciche nic.
    Ma być ERROR, bo to błąd w kodzie, nie awaria środowiska."""
    from footstats import daily_agent

    with caplog.at_level(logging.ERROR):
        daily_agent._wyslij_alarm("funkcja_ktorej_nie_ma", "skutek", "t", "b")

    assert "nie istnieje" in caplog.text


def test_udana_wysylka_nie_generuje_szumu(monkeypatch, caplog):
    """Kontrola: alarm, który doszedł, nie ma prawa nic logować — inaczej
    ostrzeżenie „ALARM NIEWYSLANY" przestaje cokolwiek znaczyć."""
    from footstats import daily_agent
    import footstats.utils.telegram_notify as _tg

    wolania = []
    monkeypatch.setattr(_tg, "send_alert", lambda *a, **k: wolania.append(a), raising=False)

    with caplog.at_level(logging.WARNING):
        daily_agent._wyslij_alarm("send_alert", "skutek", "tytul", "tresc")

    assert wolania == [("tytul", "tresc")]
    assert "ALARM NIEWYSLANY" not in caplog.text


def test_awaria_wysylki_nie_przerywa_przebiegu(monkeypatch):
    """Głośno ≠ fatalnie. Alarm jest powiadomieniem, nie warunkiem poprawności —
    padnięcie Telegrama nie może wywrócić przebiegu, który właśnie się pauzuje."""
    from footstats import daily_agent
    import footstats.utils.telegram_notify as _tg

    monkeypatch.setattr(
        _tg, "send_stop_loss_alert",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("padlo")), raising=False)

    daily_agent._wyslij_alarm("send_stop_loss_alert", "skutek", 0.2, 100.0)


def test_wszystkie_sciezki_alarmowe_ida_przez_helper():
    """Regres na przyszłość: nowy `try/except ImportError: pass` wokół wysyłki
    alarmu w `daily_agent` obchodzi wszystko powyżej.

    Sprawdzane po AST, nie po tekście — inaczej przykład starego kształtu
    w docstringu `_wyslij_alarm` wywracałby ten test.

    Zakres to WYŁĄCZNIE trzy funkcje alarmowe. `send_kupon`/`send_draft_kupon`
    to doręczenie kuponu, nie alarm, i mają własną obsługę; `check_and_alert_source_down`
    zostaje na miejscu, bo już loguje własną awarię.
    """
    import ast
    from pathlib import Path

    ALARMY = {"send_alert", "send_stop_loss_alert", "check_and_alert_accuracy"}
    zrodlo = (Path(__file__).resolve().parents[1] / "src" / "footstats"
              / "daily_agent.py").read_text(encoding="utf-8")

    winowajcy = []
    for wezel in ast.walk(ast.parse(zrodlo)):
        if not isinstance(wezel, ast.ImportFrom):
            continue
        if wezel.module != "footstats.utils.telegram_notify":
            continue
        for alias in wezel.names:
            if alias.name in ALARMY:
                winowajcy.append(f"{alias.name} (linia {wezel.lineno})")

    assert not winowajcy, (
        "funkcja alarmowa importowana z pominieciem `_wyslij_alarm` —"
        f" nieudana wysylka znowu bedzie cicha: {winowajcy}"
    )
