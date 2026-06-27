"""Regresja: _zapisz_next_final_txt musi parsować kickoff ISO 'T' (wcześniej
fmt[:len] psuł format → ISO nigdy nie parsował → fallback 13:30 → zły -70min)."""
from pathlib import Path

from footstats.core.daily_phases import _zapisz_next_final_txt

_NEXT = Path(__file__).resolve().parents[1] / "data" / "next_final.txt"


def _run_and_read(wyniki):
    backup = _NEXT.read_text(encoding="utf-8") if _NEXT.exists() else None
    try:
        _zapisz_next_final_txt(wyniki)
        return _NEXT.read_text(encoding="utf-8").strip()
    finally:
        if backup is not None:
            _NEXT.write_text(backup, encoding="utf-8")


def test_iso_t_kickoff_parsuje():
    # 18:00 − 70 min = 16:50 (NIE fallback 13:30)
    assert _run_and_read([{"kickoff": "2026-06-26T18:00:00"}]) == "16:50"


def test_spacja_datetime_parsuje():
    assert _run_and_read([{"datetime": "2026-06-26 20:00:00"}]) == "18:50"


def test_brak_godziny_fallback():
    # Sama data (bez godziny) → brak czasów → fallback 13:30
    assert _run_and_read([{"data": "2026-06-26"}]) == "13:30"
