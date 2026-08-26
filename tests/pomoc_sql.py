"""Wspólny helper testowy do bezpiecznego czytania parametrów UPDATE-a.

WSPÓLNE, BO WCZEŚNIEJ ZDUPLIKOWANE: `test_remisy_mierzone.py` i
`test_model_log_rynki_golowe.py` mockują to samo `UPDATE model_log` i obie
potrzebują sprawdzić, KTÓRA wartość trafiła pod KTÓRĄ kolumnę — nie tylko
czy dana wartość gdzieś w krotce parametrów wystąpiła.
"""
from __future__ import annotations


def kolumny_do_wartosci(sql: str, params: tuple) -> dict:
    """Mapuje `SET kolumna = ?` na wartość z krotki parametrów, PO NAZWIE.

    `assert 1 in params` przechodzi niezależnie od kolejności, jeśli dwie
    kolumny mają tę samą wartość (np. "3-1": over25_correct=1 I btts_correct=1
    I tip_correct=1) — zamiana kolumn miejscami zostałaby niezauważona.
    Odczyt po nazwie kolumny wykrywa taką zamianę niezależnie od wyniku,
    którym testujemy (zweryfikowane mutacją w obu plikach wywołujących).
    """
    czesc_set = sql.split("SET", 1)[1].split("WHERE")[0]
    kolumny = [k.split("=")[0].strip() for k in czesc_set.split(",")]
    return dict(zip(kolumny, params))
