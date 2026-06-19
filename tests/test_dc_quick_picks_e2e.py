"""E2E test wpiecia Dixon-Coles w prawdziwa sciezke produkcyjna (P3 z review).

Naprawia dziure z test_dc_prod_integration.py: tamtejsze testy kopiuja
inline fragment wpiecia (symulacja), wiec przeszly nawet po usunieciu
realnego wpiecia z quick_picks.py. Ten test wola PRAWDZIWA
szybkie_pewniaczki_2dni z df_mecze majacym wystarczajaca historie obu
druzyn (jako gospodarz i jako gosc), zeby predict_match_bayesian (DC)
zwrocilo non-None i blend_dixon_coles realnie zmienilo wynik.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from footstats.core.quick_picks import szybkie_pewniaczki_2dni

_NOW = datetime.now()
_SOON = _NOW + timedelta(hours=6)
_DATE = _SOON.strftime("%Y-%m-%d")
_HOUR = _SOON.strftime("%H:%M")

_BZZ_EVENT = {
    "gosp": "Arsenal",
    "gosc": "Chelsea",
    "liga": "Premier League",
    "data": _DATE,
    "godzina": _HOUR,
    "pred_ml": {
        "percent": {"home": "60%", "draw": "20%", "away": "20%"},
        "btts": "50%",
        "over_2_5": "55%",
    },
    "odds": {"home": 1.8, "draw": 3.5, "away": 4.0},
}


def _make_bzzoiro(events: list) -> MagicMock:
    client = MagicMock()
    client._valid = True
    client.predykcje_tygodnia.return_value = events
    return client


def _df_historia_arsenal_chelsea() -> pd.DataFrame:
    """Realna historia obu druzyn (gospodarz + goscie), >=15 meczow kazda.

    Wymagane do non-None predict_match (>=4 mecze pary/historii) ORAZ
    non-None predict_match_bayesian/DC (oba zespoly musza miec mecze
    jako gospodarz I jako goscie w df, inaczej _compute_ratings zwroci att=None).
    """
    rows = []
    for i in range(20):
        rows.append({
            "gospodarz": "Arsenal", "goscie": "Chelsea",
            "gole_g": 2, "gole_a": 1,
            "liga": "Premier League", "data": f"2024-{(i % 12) + 1:02d}-05",
        })
        rows.append({
            "gospodarz": "Chelsea", "goscie": "Arsenal",
            "gole_g": 1, "gole_a": 1,
            "liga": "Premier League", "data": f"2024-{(i % 12) + 1:02d}-20",
        })
    return pd.DataFrame(rows)


def _run(monkeypatch, use_dc: bool, w_bayesian: float = 0.5) -> dict:
    """Wola prawdziwa szybkie_pewniaczki_2dni z flaga DC ustawiona przez monkeypatch."""
    import footstats.core.quick_picks as qp

    monkeypatch.setattr(qp, "USE_DIXON_COLES", use_dc, raising=False)
    monkeypatch.setattr(qp, "W_BAYESIAN", w_bayesian, raising=False)

    bzz = _make_bzzoiro([_BZZ_EVENT])
    df = _df_historia_arsenal_chelsea()

    mock_fort = MagicMock()
    mock_fort.analiza.return_value = None
    mock_h2h = MagicMock()
    mock_h2h.analiza.return_value = None
    mock_heur = MagicMock()
    mock_heur.analiza.return_value = None
    mock_klas = MagicMock()
    mock_klas.klasyfikuj.return_value = None

    with patch(
        "footstats.core.quick_picks.calibrate_confidence", side_effect=lambda x: x / 100
    ), patch(
        "footstats.core.fortress.HomeFortress", return_value=mock_fort
    ), patch(
        "footstats.core.h2h.AnalizaH2H", return_value=mock_h2h
    ), patch(
        "footstats.core.fatigue.HeurystaZmeczeniaRotacji", return_value=mock_heur
    ), patch(
        "footstats.core.classifier.KlasyfikatorMeczu", return_value=mock_klas
    ):
        wyniki = szybkie_pewniaczki_2dni(bzz, prog=0.0, df_mecze=df)

    assert len(wyniki) >= 1
    return wyniki[0]


def test_dc_wiring_e2e_on_vs_off_changes_1x2_via_real_function(monkeypatch):
    """Wpiecie DC w prawdziwej szybkie_pewniaczki_2dni musi zmienic pw/pr/pp.

    Wola prawdziwa funkcje produkcyjna (NIE symulacje inline) dwukrotnie:
    raz z USE_DIXON_COLES=True, raz z False — to samo df_mecze, ten sam mecz.
    Gdyby wpiecie blend_dixon_coles bylo usuniete z quick_picks.py, ON i OFF
    dalyby identyczny wynik -> test by FAILOWAL (RED), bo asercja wymaga roznicy.
    """
    r_on = _run(monkeypatch, use_dc=True)
    r_off = _run(monkeypatch, use_dc=False)

    assert r_on["poisson_blend"] is True
    assert r_off["poisson_blend"] is True

    # Klucz dowodowy: DC realnie zmienia 1X2 (inaczej ON==OFF -> wpiecie martwe).
    roznica = (
        abs(r_on["pw"] - r_off["pw"])
        + abs(r_on["pr"] - r_off["pr"])
        + abs(r_on["pp"] - r_off["pp"])
    )
    assert roznica > 0.05, (
        f"DC ON i OFF daja identyczny 1X2 (roznica={roznica}) — "
        "wpiecie blend_dixon_coles nie dziala w sciezce prod"
    )


def test_dc_wiring_e2e_bt_o25_untouched_by_dc(monkeypatch):
    """DC dotyka TYLKO 1X2 — bt/o25 musza byc identyczne ON vs OFF."""
    r_on = _run(monkeypatch, use_dc=True)
    r_off = _run(monkeypatch, use_dc=False)

    assert r_on["bt"] == r_off["bt"]
    assert r_on["o25"] == r_off["o25"]
