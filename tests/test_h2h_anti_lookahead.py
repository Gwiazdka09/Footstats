"""Anty-lookahead H2H: okno 24 mies. musi być kotwiczone do DATY MECZU, nie now().

Bug: _filtruj_h2h używało datetime.now() → w backteście okno [now-730, now]
zawierało mecze H2H ROZEGRANE PO przewidywanym meczu → leak przyszłości do
features. Fix: opcjonalny data_meczu (anchor); okno [anchor-730d, anchor) →
wyklucza mecz analizowany i przyszłe. Brak data_meczu → now (live bez zmian).
"""
from datetime import datetime, timedelta

import pandas as pd

from footstats.core.h2h import AnalizaH2H


def _df(rows):
    return pd.DataFrame(rows)


def test_anchor_wyklucza_przyszle_h2h():
    # Mecz analizowany 2024-06-01: H2H z 2024-08-01 jest PRZYSZŁY → nie liczony.
    df = _df([
        {"gospodarz": "A", "goscie": "B", "gole_g": 2, "gole_a": 0, "data": "2024-05-01"},
        {"gospodarz": "A", "goscie": "B", "gole_g": 0, "gole_a": 3, "data": "2024-08-01"},
    ])
    wynik = AnalizaH2H(df).analiza("A", "B", data_meczu="2024-06-01")
    daty = set(wynik["h2h_df"]["data"])
    assert "2024-08-01" not in daty   # przyszłość odcięta (anty-lookahead)
    assert "2024-05-01" in daty


def test_anchor_okno_730_od_daty_meczu():
    # Mecz 2024-06-01: H2H z 2021-01-01 >730 dni wstecz → odrzucone.
    df = _df([
        {"gospodarz": "A", "goscie": "B", "gole_g": 1, "gole_a": 1, "data": "2021-01-01"},
        {"gospodarz": "A", "goscie": "B", "gole_g": 2, "gole_a": 0, "data": "2023-12-01"},
    ])
    wynik = AnalizaH2H(df).analiza("A", "B", data_meczu="2024-06-01")
    daty = set(wynik["h2h_df"]["data"])
    assert wynik["n_h2h"] == 1
    assert "2023-12-01" in daty and "2021-01-01" not in daty


def test_bez_daty_meczu_uzywa_now():
    # Fallback live: brak data_meczu → anchor=now. Mecz sprzed 10 dni liczony.
    recent = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    df = _df([{"gospodarz": "A", "goscie": "B", "gole_g": 2, "gole_a": 0, "data": recent}])
    wynik = AnalizaH2H(df).analiza("A", "B")
    assert wynik["n_h2h"] == 1
