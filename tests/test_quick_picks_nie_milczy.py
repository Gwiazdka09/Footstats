"""J1 w ścieżce selekcji: kandydat, który wypada z puli, ma zostawić ślad.

`quick_picks` decyduje, KTÓRE mecze w ogóle trafią pod model i pod Groqa. Cicha
utrata kandydata jest tu nie do odróżnienia od „tego meczu nie było" — a to
dokładnie ten kształt, który 28.08 zostawiał puste `factors` w całym przebiegu
(systemy λ padały pod `except`, o czym nikt się nie dowiadywał).

Jeden handler w tym pliku ZOSTAJE milczący i jest to świadome: fallback
formatowania nagłówka dnia do konsoli pokazuje surową datę, więc użytkownik i tak
widzi, że coś jest nietypowe. Log dublowałby to, co już jest na ekranie.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from footstats.core.quick_picks import szybkie_pewniaczki_2dni

_SOON = datetime.now() + timedelta(hours=6)


def _event(**nadpisz) -> dict:
    baza = {
        "gosp": "Arsenal",
        "gosc": "Chelsea",
        "liga": "Premier League",
        "data": _SOON.strftime("%Y-%m-%d"),
        "godzina": _SOON.strftime("%H:%M"),
        "pred_ml": {
            "percent": {"home": "60%", "draw": "20%", "away": "20%"},
            "btts": "50%",
            "over_2_5": "55%",
        },
        "odds": {"home": 1.8, "draw": 3.5, "away": 4.0},
    }
    baza.update(nadpisz)
    return baza


def _klient(events: list) -> MagicMock:
    c = MagicMock()
    c._valid = True
    c.predykcje_tygodnia.return_value = events
    return c


def _uruchom(events: list):
    """Odcina Poissona i kalibrację — testujemy głośność, nie liczby."""
    with patch("footstats.core.quick_picks.calibrate_confidence",
               side_effect=lambda x: x / 100), \
         patch("footstats.data.historical_loader.load_cached",
               side_effect=FileNotFoundError("brak cache")):
        return szybkie_pewniaczki_2dni(_klient(events), prog=0.0)


# ── utrata kandydata ────────────────────────────────────────────────────────

def test_data_nie_do_sparsowania_mowi_ktory_mecz_wypadl(caplog):
    """Cicho znaczyło: mecz nie istnieje. Przy 40 kandydatach nikt nie zauważy,
    że pula skurczyła się o dwa."""
    with caplog.at_level(logging.WARNING):
        wyniki = _uruchom([_event(data="wczoraj", godzina="–")])

    assert wyniki == []
    assert "wypada z puli kandydatow" in caplog.text
    assert "Arsenal" in caplog.text, "log ma nazwac MECZ, nie tylko fakt bledu"


def test_poprawny_mecz_nie_generuje_szumu(caplog):
    """Kontrola. Ta pętla chodzi po WSZYSTKICH wydarzeniach z okna — jedno zbędne
    ostrzeżenie na mecz utopiłoby log przy każdym przebiegu."""
    with caplog.at_level(logging.WARNING):
        wyniki = _uruchom([_event()])

    assert len(wyniki) == 1
    assert "wypada z puli" not in caplog.text


def test_sama_data_bez_godziny_dalej_dziala(caplog):
    """Fallback na format bez godziny jest POPRAWNY i ma zostać cichy —
    ostrzeżenie należy się dopiero, gdy oba formaty zawiodą."""
    with caplog.at_level(logging.WARNING):
        wyniki = _uruchom([_event(godzina="–")])

    assert len(wyniki) == 1
    assert "nie do sparsowania" not in caplog.text


# ── utrata podsystemów ──────────────────────────────────────────────────────

def test_brak_walidatora_mowi_ze_dataset_idzie_NIESPRAWDZONY(caplog, monkeypatch):
    """Kierunek skutku jest tu odwrotny do intuicji: bez walidatora `df_mecze`
    NIE jest pomijany, tylko idzie do Poissona nieprzefiltrowany. Log musi mówić
    o braku sprawdzenia, nie o braku Poissona."""
    import builtins
    import pandas as pd

    prawdziwy = builtins.__import__

    def _bez_walidatora(nazwa, *a, **k):
        if nazwa == "footstats.utils.logging":
            raise ImportError("brak modulu")
        return prawdziwy(nazwa, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _bez_walidatora)

    df = pd.DataFrame({
        "date": ["2026-01-01"], "home": ["Arsenal"], "away": ["Chelsea"],
        "hg": [2], "ag": [1],
    })
    with caplog.at_level(logging.WARNING), \
         patch("footstats.core.quick_picks.calibrate_confidence",
               side_effect=lambda x: x / 100), \
         patch("footstats.core.wf_harness.adapt_to_prod_schema",
               side_effect=lambda d: d), \
         patch("footstats.data.historical_loader.load_cached", return_value=df):
        szybkie_pewniaczki_2dni(_klient([_event()]), prog=0.0)

    assert "BEZ sprawdzenia" in caplog.text


# ── EV bez kursu ────────────────────────────────────────────────────────────

def test_nieczytelny_kurs_mowi_ze_EV_nie_powstanie(caplog):
    """`kurs = None` cicho znaczyło „brak przewagi", a znaczy „nie policzyliśmy".
    Te dwa stany wyglądają identycznie w wyniku i tylko log je rozróżnia."""
    from footstats.core.quick_picks import _scout_bot_ocen

    with caplog.at_level(logging.WARNING):
        _scout_bot_ocen(
            [("1", 60.0)], {"home": "nie-liczba"},
            60.0, 20.0, 20.0, 50.0, 55.0, 45.0,
        )

    assert "EV dla tego typu NIE zostanie policzone" in caplog.text


def test_poprawny_kurs_nie_generuje_szumu(caplog):
    from footstats.core.quick_picks import _scout_bot_ocen

    with caplog.at_level(logging.WARNING):
        _scout_bot_ocen(
            [("1", 60.0)], {"home": 1.85},
            60.0, 20.0, 20.0, 50.0, 55.0, 45.0,
        )

    assert caplog.text == ""
