"""`model_log.lambda_h/lambda_a` byly puste w 100% historii — 1231 z 1231 wierszy.

STAN ZASTANY (2026-09-10, pomiar prod):

    model_source   wierszy   z lambda_h
    bzzoiro-ml         934            0
    poisson-dc         295            0

`zapisz_ocene` czyta `kandydat["lambda_h"]`, ale to pole ustawia dopiero KROK 2
(`_apply_injury_corrections`, `bet_builder`) — a dziennik zapisuje sie w fazie
final, PRZED KROKIEM 2. Ta sama kolejnosc, ktora zabila team-news 07.09.

Tymczasem `poisson.predict_match` zwraca `lambda_g/lambda_a` — quick_picks
wyrzucal je razem z reszta `_pred_p`. Bez nich z dziennika nie da sie zmierzyc
obciazenia λ na zywo (Bias = gole faktyczne / λ przewidziane), tylko odtwarzac
λ z prawdopodobienstw, co jest stratne — patrz `feedback_lambda_sie_czyta`.

DLACZEGO OSOBNY KLUCZ, a nie `lambda_h`. `daily_phases` czyta `w["lambda_h"]`
jako punkt wyjscia korekty absencji i dopiero przy jego braku estymuje λ
z KONCOWYCH prawdopodobienstw (po ensemble z rynkiem). λ ramienia Poissona to
inna liczba — podstawienie jej pod ten klucz zmieniloby korekte absencji
na produkcji, a to nie jest cel tej zmiany.

ZNACZENIE KOLUMNY: λ ramienia Poissona PRZED blendem Dixon-Coles i PRZED
ensemble z Bzzoiro/rynkiem. Dla `bzzoiro-ml` zostaje NULL — ten model λ nie ma.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from footstats.core.quick_picks import szybkie_pewniaczki_2dni

_SOON = datetime.now() + timedelta(hours=6)
_EVENT = {
    "gosp": "Arsenal", "gosc": "Chelsea", "liga": "Premier League",
    "data": _SOON.strftime("%Y-%m-%d"), "godzina": _SOON.strftime("%H:%M"),
    "pred_ml": {"percent": {"home": "60%", "draw": "20%", "away": "20%"},
                "btts": "50%", "over_2_5": "55%"},
    "odds": {"home": 1.8, "draw": 3.5, "away": 4.0},
}
_POISSON_PRED = {
    "lambda_g": 1.62, "lambda_a": 1.08,
    "p_wygrana": 50.0, "p_remis": 30.0, "p_przegrana": 20.0,
    "btts": 40.0, "over25": 45.0, "under25": 55.0,
}
_DF = pd.DataFrame([{"gospodarz": "A", "goscie": "B", "gole_g": 1, "gole_a": 0,
                     "data": "2026-01-01"}])


def _uruchom(df_mecze):
    klient = MagicMock()
    klient._valid = True
    klient.predykcje_tygodnia.return_value = [_EVENT]
    mock = MagicMock()
    mock.analiza.return_value = None
    mock_klas = MagicMock()
    mock_klas.klasyfikuj.return_value = None
    brak_historii = patch(
        "footstats.data.historical_loader.load_cached",
        side_effect=ImportError("Unable to find a usable engine"),
    )
    with brak_historii if df_mecze is None else contextlib.nullcontext(), patch(
        "footstats.core.poisson.predict_match", return_value=_POISSON_PRED
    ), patch("footstats.core.fortress.HomeFortress", return_value=mock), patch(
        "footstats.core.h2h.AnalizaH2H", return_value=mock
    ), patch("footstats.core.fatigue.HeurystaZmeczeniaRotacji", return_value=mock), patch(
        "footstats.core.classifier.KlasyfikatorMeczu", return_value=mock_klas
    ):
        wyniki = szybkie_pewniaczki_2dni(klient, prog=0.0, df_mecze=df_mecze)
    assert wyniki, "quick_picks nie zwrocil zadnego meczu"
    return wyniki[0]


# ── quick_picks niesie λ ramienia Poissona ──────────────────────────────────

def test_poisson_niesie_lambdy_do_kandydata():
    r = _uruchom(_DF)
    assert r["poisson_blend"] is True, "test bezwartosciowy — Poisson nie wystartowal"
    assert r["lambda_poisson_h"] == 1.62
    assert r["lambda_poisson_a"] == 1.08


def test_bzzoiro_nie_ma_lambdy_None_a_nie_zero():
    """Zero znaczyloby "model przewiduje zero goli" — to inny stan niz brak λ."""
    r = _uruchom(None)
    assert r["poisson_blend"] is False
    assert r["lambda_poisson_h"] is None
    assert r["lambda_poisson_a"] is None


def test_lambda_h_kandydata_NIE_jest_ustawiana():
    """`daily_phases` traktuje `lambda_h` jako baze korekty absencji — nie ruszamy."""
    r = _uruchom(_DF)
    assert "lambda_h" not in r
    assert "lambda_a" not in r


# ── zapisz_ocene utrwala λ ──────────────────────────────────────────────────

def _zapisz(monkeypatch, kandydat: dict) -> dict:
    from footstats.core import kalibracja_log as kl

    zapisane: dict = {}

    class _Conn:
        def execute(self, sql, params=()):
            wstawia = "INSERT INTO model_log" in sql
            if wstawia:
                zapisane["sql"] = " ".join(sql.split())
                zapisane["params"] = params

            class _R:
                @staticmethod
                def fetchone():
                    return {"id": 1} if wstawia else None
            return _R()

        def executescript(self, _s): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr(kl, "_connect", lambda: _Conn())
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)
    kl.zapisz_ocene({"data": "2026-09-10", "gospodarz": "Como", "goscie": "RB Leipzig",
                     "pw": 51.3, "pr": 23.3, "pp": 25.4, **kandydat})

    kolumny = zapisane["sql"].split("(", 1)[1].split(")", 1)[0]
    nazwy = [k.strip() for k in kolumny.split(",")]
    return dict(zip(nazwy, zapisane["params"]))


def test_zapis_bierze_lambde_poissona(monkeypatch):
    wiersz = _zapisz(monkeypatch, {"lambda_poisson_h": 1.98, "lambda_poisson_a": 1.36})
    assert wiersz["lambda_h"] == 1.98
    assert wiersz["lambda_a"] == 1.36


def test_jawna_lambda_h_wygrywa(monkeypatch):
    """`national_lambda` ustawia `lambda_h` wprost (Poisson kadr) — to tez λ modelu."""
    wiersz = _zapisz(monkeypatch, {"lambda_h": 2.1, "lambda_a": 0.9,
                                   "lambda_poisson_h": 1.0, "lambda_poisson_a": 1.0})
    assert wiersz["lambda_h"] == 2.1
    assert wiersz["lambda_a"] == 0.9


def test_bez_lambdy_zostaje_NULL(monkeypatch):
    wiersz = _zapisz(monkeypatch, {})
    assert wiersz["lambda_h"] is None
    assert wiersz["lambda_a"] is None
