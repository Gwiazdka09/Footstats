"""test_rag_factors_quick_picks.py — P3/C: RAG dostaje faktory z quick_picks.

Bug: `factors='[]'` na 15/15 predykcji w Supabase → RAG nie miał się na czym uczyć.
Dwa niezależne przerwania łańcucha:
  1. `pred` budowany w quick_picks miał WYŁĄCZNIE prawdopodobieństwa, a
     `rag.wyciagnij_faktory` czyta `h2h_g`/`heur_g`/`heur_a`/`fortress_g` → zawsze [].
  2. quick_picks nie ustawiał `metoda`, a `rag.pobierz_rag_kontekst` zwraca ""
     dla wszystkiego poza "POISSON" → kontekst RAG nigdy nie trafiał do promptu.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from footstats.ai.rag import wyciagnij_faktory
from footstats.core.quick_picks import szybkie_pewniaczki_2dni

_NOW = datetime.now()
_SOON = _NOW + timedelta(hours=6)

_EVENT = {
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

_POISSON_PRED = {
    "p_wygrana": 50.0, "p_remis": 30.0, "p_przegrana": 20.0,
    "btts": 40.0, "over25": 45.0, "under25": 55.0,
}

_DF = pd.DataFrame([{"gospodarz": "A", "goscie": "B", "gole_g": 1, "gole_a": 0,
                     "data": "2026-01-01"}])


def _zrodlo(events: list) -> MagicMock:
    klient = MagicMock()
    klient._valid = True
    klient.predykcje_tygodnia.return_value = events
    return klient


def _uruchom(fortress=None, h2h=None, heur=None):
    """Odpala quick_picks z podstawionymi systemami λ. Zwraca pierwszy wynik."""
    mock_fort = MagicMock(); mock_fort.analiza.return_value = fortress
    mock_h2h = MagicMock(); mock_h2h.analiza.return_value = h2h
    mock_heur = MagicMock(); mock_heur.analiza.return_value = heur
    mock_klas = MagicMock(); mock_klas.klasyfikuj.return_value = None

    with patch(
        "footstats.core.poisson.predict_match", return_value=_POISSON_PRED
    ), patch(
        "footstats.core.fortress.HomeFortress", return_value=mock_fort
    ), patch(
        "footstats.core.h2h.AnalizaH2H", return_value=mock_h2h
    ), patch(
        "footstats.core.fatigue.HeurystaZmeczeniaRotacji", return_value=mock_heur
    ), patch(
        "footstats.core.classifier.KlasyfikatorMeczu", return_value=mock_klas
    ):
        wyniki = szybkie_pewniaczki_2dni(_zrodlo([_EVENT]), prog=0.0, df_mecze=_DF)

    assert wyniki, "quick_picks nie zwrócił żadnego meczu"
    return wyniki[0]


# ── 1. pred musi nieść faktory, nie tylko prawdopodobieństwa ────────────────


def test_pred_niesie_faktory_do_rag():
    """PATENT + TWIERDZA + ROTACJA muszą wyjść z pred zbudowanego przez quick_picks."""
    r = _uruchom(
        fortress={"fortress": True},
        h2h={"patent": True},
        heur={"rotacja": True},
    )
    faktory = wyciagnij_faktory(r["pred"])
    assert "PATENT" in faktory
    assert "TWIERDZA" in faktory
    assert "ROTACJA" in faktory


def test_brak_sygnalow_to_puste_faktory():
    """Bez realnych sygnałów faktory zostają puste — żadnych fałszywych tagów."""
    r = _uruchom(fortress=None, h2h=None, heur=None)
    assert wyciagnij_faktory(r["pred"]) == []


def test_pred_zachowuje_prawdopodobienstwa():
    """Regresja Cel B bug 1: pred nadal musi nieść prob dla pewnosc_z_modelu."""
    r = _uruchom(fortress={"fortress": True})
    for klucz in ("p_wygrana", "p_remis", "p_przegrana", "btts", "over25", "under25"):
        assert klucz in r["pred"], f"pred stracił {klucz}"


# ── 2. metoda odblokowuje kontekst RAG w prompcie ───────────────────────────


def test_metoda_poisson_gdy_model_policzyl():
    """pobierz_rag_kontekst przepuszcza tylko metoda=='POISSON'."""
    r = _uruchom(fortress={"fortress": True})
    assert r["poisson_blend"] is True
    assert r["metoda"] == "POISSON"


def test_metoda_ml_gdy_poisson_niedostepny():
    """Bez historii zostaje samo ML — nie oznaczaj tego jako POISSON."""
    with patch(
        "footstats.data.historical_loader.load_cached",
        side_effect=FileNotFoundError("brak cache"),
    ):
        wyniki = szybkie_pewniaczki_2dni(_zrodlo([_EVENT]), prog=0.0)
    assert wyniki[0]["poisson_blend"] is False
    assert wyniki[0]["metoda"] == "ML"


def test_rag_kontekst_widzi_mecz_z_quick_picks():
    """End-to-end bramki: pobierz_rag_kontekst nie odrzuca już wpisu z quick_picks."""
    from footstats.ai.rag import pobierz_rag_kontekst

    r = _uruchom(fortress={"fortress": True}, h2h={"patent": True})
    with patch("footstats.ai.rag.pobierz_rag_wzorce", return_value="HISTORIA: 7/10"):
        kontekst = pobierz_rag_kontekst(r)
    assert kontekst != "", "wpis z quick_picks nadal odrzucany przez bramkę metoda/faktory"


# ── 3. awaria systemów λ nie może być cicha ─────────────────────────────────


def test_padniete_systemy_lambda_zglaszaja_sie_glosno(caplog):
    """Te cztery systemy to JEDYNE źródło tagów PATENT/ZEMSTA/TWIERDZA. Gdy nie
    wstaną, `factors` są puste w CAŁYM przebiegu — a puste `factors` wyglądają
    dokładnie tak samo jak stan normalny (zmierzone 28.08: 246 z 255 predykcji
    na produkcji ma `factors='[]'`, bo typujemy ligi spoza naszej historii).
    Cichy `except ... : pass` chował więc awarię w miejscu, w którym nikt by jej
    nie zauważył.

    `KeyError` nie jest hipotetyczny: systemy czytają kolumny po nazwie
    (`gospodarz`/`goscie`), więc nieprzeadaptowany schemat parquetu (`home`/`away`)
    wysypuje je właśnie nim.
    """
    with patch(
        "footstats.core.fortress.HomeFortress",
        side_effect=KeyError("gospodarz"),
    ), caplog.at_level("WARNING"):
        wyniki = szybkie_pewniaczki_2dni(_zrodlo([_EVENT]), prog=0.0, df_mecze=_DF)

    assert "factors" in caplog.text.lower(), "awaria systemów λ musi być GŁOŚNA"
    assert wyniki, "awaria systemów λ nie może zatrzymać całego przebiegu"
    assert wyciagnij_faktory(wyniki[0]["pred"]) == []
