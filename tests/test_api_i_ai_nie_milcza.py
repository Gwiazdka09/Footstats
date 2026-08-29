"""J1: health udający wynik pomiaru, zapis typów znikający bez śladu.

Trzy różne kształty tej samej choroby:

`api/main.health` — `auth.ok=false` znaczyło DWIE rzeczy naraz: „nie ma aktywnych
userów" (stan normalny) oraz „nie udało się sprawdzić" (awaria bazy). Endpoint
zdrowia, który przy własnej awarii melduje wynik pomiaru zamiast braku pomiaru,
jest gorszy niż jego brak. Kontraktu JSON nie ruszam — czyta go monitoring —
ale log te dwa stany rozróżnia.

`analyzer_helpers._auto_zapisz_backtest` — brak `save_prediction` znaczył, że
analiza kończy się sukcesem, a do bazy NIE trafia ani jeden typ. To ERROR,
nie WARNING: nie ma tu żadnej częściowej degradacji, jest całkowita utrata.

`_wzbogac_forme` / `wyciagnij_faktory` — utrata całego etapu wzbogacania i puste
`factors`, czyli dokładnie to, co 28.08 badaliśmy w `quick_picks`.

CISZA, KTÓRA ZOSTAJE: łańcuch naprawczy JSON-a od modelu. Kroki pośrednie
milczą z założenia — głośny jest WYNIK (udana naprawa → WARNING, nieodwracalna
porażka → ERROR), i to jest opisane w docstringu funkcji.
"""
from __future__ import annotations

import logging

from footstats.ai import analyzer_helpers as ah


# ── health: „nie wiadomo" ≠ „nie ma" ────────────────────────────────────────

def test_health_rozroznia_awarie_bazy_od_pustej_bazy(caplog, monkeypatch):
    """`auth.ok=false` przy padniętej bazie znaczy NIE WIADOMO. Bez logu
    monitoring widzi to samo, co przy realnie pustej tabeli userów."""
    from footstats.api import main as am

    def _wybuch(*_a, **_k):
        raise RuntimeError("baza niedostepna")

    monkeypatch.setattr("footstats.utils.db.connect", _wybuch)

    with caplog.at_level(logging.WARNING):
        odp = am.health()

    assert odp["status"] == "ok", "health nie ma prawa zwrocic 5xx"
    assert odp["auth"]["ok"] is False
    assert "NIE WIADOMO" in caplog.text


def test_health_mowi_osobno_o_userach_i_o_swiezosci_predykcji(caplog, monkeypatch):
    """Dwa niezależne sprawdzenia — log ma pozwolić ustalić, które padło."""
    from footstats.api import main as am

    def _wybuch(*_a, **_k):
        raise RuntimeError("baza niedostepna")

    monkeypatch.setattr("footstats.utils.db.connect", _wybuch)

    with caplog.at_level(logging.WARNING):
        am.health()

    assert "userow" in caplog.text
    assert "swiezosci predykcji" in caplog.text


# ── utrata zapisu typów ─────────────────────────────────────────────────────

def test_brak_save_prediction_to_ERROR_a_nie_warning(caplog, monkeypatch):
    """Nie ma tu częściowej degradacji: analiza kończy się sukcesem, a do bazy
    nie trafia ANI JEDEN typ. To całkowita utrata, więc poziom ERROR."""
    import builtins

    prawdziwy = builtins.__import__

    def _bez_backtestu(nazwa, *a, **k):
        if nazwa == "footstats.core.backtest":
            raise ImportError("brak modulu")
        return prawdziwy(nazwa, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _bez_backtestu)

    with caplog.at_level(logging.WARNING):
        ah._auto_zapisz_backtest({"top3": []}, [])

    assert "NIE" in caplog.text and "zapisane" in caplog.text
    assert any(r.levelno >= logging.ERROR for r in caplog.records), (
        "calkowita utrata zapisu to ERROR, nie WARNING"
    )


# ── łańcuch naprawczy JSON-a: cisza w krokach, głos w wyniku ────────────────

def test_uszkodzony_json_naprawiony_zglasza_sie_glosno(caplog):
    """Kroki pośrednie milczą, ale UDANA naprawa musi zostawić ślad — inaczej
    nie wiadomo, że model oddaje popsuty JSON."""
    tekst = '{"top3": [{"mecz": "A - B"}]} nadmiarowy ogon }'

    with caplog.at_level(logging.WARNING):
        dane = ah._wyciagnij_json(tekst)

    assert isinstance(dane, dict)


def test_poprawny_json_nie_generuje_szumu(caplog):
    """Kontrola: `_wyciagnij_json` leci po KAŻDEJ odpowiedzi modelu."""
    with caplog.at_level(logging.WARNING):
        dane = ah._wyciagnij_json('{"top3": []}')

    assert dane == {"top3": []}
    assert caplog.text == ""


def test_kroki_lancucha_naprawczego_maja_uzasadnienie_w_kodzie():
    """Te dwa `pass` ZOSTAJĄ milczące. Komentarz jest jedyną rzeczą, która
    odróżnia świadomą decyzję od przeoczenia — i ma nie zniknąć."""
    import inspect

    zrodlo = inspect.getsource(ah._wyciagnij_json)
    assert zrodlo.count("CISZA CELOWA") == 2, (
        "znikl komentarz uzasadniajacy cisze w krokach lancucha naprawczego"
    )
