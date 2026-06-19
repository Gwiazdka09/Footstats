"""Whitelist lig — aktywne ligi klubowe (lato) przechodzą, MŚ (kadry) odrzucone.

Regresja decyzji 2026-06-19: System paper-trading był zagłodzony bo top-ligi
europejskie off-season, a obecne fixtures (USL/Brasileirão B/Segunda/Botola) były
poza whitelist. World Cup celowo POZA (kadry != model λ klubowy).
"""
from footstats.core.daily_filters import _pre_filtruj_ligi


def _m(liga):
    return {"gospodarz": "A", "goscie": "B", "liga": liga, "data": "2026-06-21"}


def test_aktywne_ligi_klubowe_przechodza():
    przeszly = {m["liga"] for m in _pre_filtruj_ligi([
        _m("Brasileirão Serie B"), _m("Segunda División"),
        _m("USL Championship"), _m("Botola Pro"),
    ])}
    assert przeszly == {"Brasileirão Serie B", "Segunda División",
                        "USL Championship", "Botola Pro"}


def test_world_cup_odrzucone():
    assert _pre_filtruj_ligi([_m("World Cup 2026")]) == []
