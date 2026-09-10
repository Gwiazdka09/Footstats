"""Ramie Dixon-Coles dostawalo SUROWE nazwy z Bzzoiro — jedna regula w dwoch wejsciach.

`quick_picks` wola dwie funkcje z tymi samymi `g, a`:

    predict_match(g, a, df_mecze)            -> `_kanoniczne_nazwy` tlumaczy nazwe
    blend_dixon_coles(_p_pois, g, a, df)     -> `_compute_ratings`: df["gospodarz"] == g

Druga porownywala nazwe DOKLADNIE. "Manchester United" to w datasecie
"Man United" (alias w `utils/normalize`), wiec classic Poisson liczyl, a ramie
DC po cichu oddawalo `p_model` bez zmian. Walk-forward, na ktorym strojona byla
waga `W_BAYESIAN`, podaje nazwy WPROST z datasetu — tam ramie dziala zawsze.
Produkcja miala wiec inny model niz zmierzony.
"""
from __future__ import annotations

import pandas as pd

from footstats.core.poisson_bayesian import blend_dixon_coles

_P_MODEL = {"pw": 50.0, "pr": 25.0, "pp": 25.0, "bt": 55.0, "o25": 52.0}


def _df() -> pd.DataFrame:
    """Man United mocny u siebie, Chelsea slaba na wyjezdzie — DC musi to widziec."""
    wiersze = []
    for i in range(10):
        wiersze.append({"gospodarz": "Man United", "goscie": f"R{i}",
                        "gole_g": 3, "gole_a": 0, "data": pd.Timestamp("2026-08-01")})
        wiersze.append({"gospodarz": f"R{i}", "goscie": "Chelsea",
                        "gole_g": 2, "gole_a": 0, "data": pd.Timestamp("2026-08-02")})
    return pd.DataFrame(wiersze)


def test_nazwa_historii_uruchamia_ramie():
    """Punkt odniesienia: nazwy wprost z datasetu — ramie DC dziala."""
    wynik = blend_dixon_coles(dict(_P_MODEL), "Man United", "Chelsea", _df())
    assert wynik["pw"] > _P_MODEL["pw"]


def test_nazwa_z_bzzoiro_uruchamia_ramie_tak_samo():
    surowa = blend_dixon_coles(dict(_P_MODEL), "Manchester United", "Chelsea FC", _df())
    wzorzec = blend_dixon_coles(dict(_P_MODEL), "Man United", "Chelsea", _df())
    assert surowa["pw"] == wzorzec["pw"]
    assert surowa["pp"] == wzorzec["pp"]


def test_nieznana_druzyna_dalej_zostawia_p_model():
    wynik = blend_dixon_coles(dict(_P_MODEL), "Sabah FK", "Chelsea", _df())
    assert wynik == _P_MODEL


def test_bt_i_o25_nietkniete():
    wynik = blend_dixon_coles(dict(_P_MODEL), "Manchester United", "Chelsea", _df())
    assert wynik["bt"] == _P_MODEL["bt"] and wynik["o25"] == _P_MODEL["o25"]
