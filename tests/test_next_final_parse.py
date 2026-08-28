"""Regresja: _zapisz_next_final_txt musi parsować kickoff ISO 'T' (wcześniej
fmt[:len] psuł format → ISO nigdy nie parsował → fallback 13:30 → zły -70min).

28.08: testy pisały do PRAWDZIWEGO `data/next_final.txt` w repo i przywracały
backup w `finally`. Zmierzone na dwóch równoległych przebiegach pytest: jeden
proces przywracał backup, gdy drugi już czytał — 2 z 3 testów tego pliku padały,
a w izolacji przechodziły zawsze. To była jedna z dwóch odtworzonych przyczyn
„niestabilnej suity". Teraz każdy test pisze do własnego `tmp_path` i prawdziwy
plik produkcyjny nie jest w ogóle dotykany.
"""
from pathlib import Path

from footstats.core.daily_phases import _zapisz_next_final_txt

_PRAWDZIWY = Path(__file__).resolve().parents[1] / "data" / "next_final.txt"


def _run_and_read(wyniki, katalog: Path) -> str:
    _zapisz_next_final_txt(wyniki, katalog=katalog)
    return (katalog / "next_final.txt").read_text(encoding="utf-8").strip()


def test_iso_t_kickoff_parsuje(tmp_path):
    # 18:00 − 70 min = 16:50 (NIE fallback 13:30)
    assert _run_and_read([{"kickoff": "2026-06-26T18:00:00"}], tmp_path) == "16:50"


def test_spacja_datetime_parsuje(tmp_path):
    assert _run_and_read([{"datetime": "2026-06-26 20:00:00"}], tmp_path) == "18:50"


def test_brak_godziny_fallback(tmp_path):
    # Sama data (bez godziny) → brak czasów → fallback 13:30
    assert _run_and_read([{"data": "2026-06-26"}], tmp_path) == "13:30"


def test_domyslnie_dalej_pisze_do_data_next_final(monkeypatch):
    """Parametr `katalog` jest udogodnieniem TESTOWYM — nie wolno mu zmienić
    ścieżki produkcyjnej. Bez niego cel to nadal `data/next_final.txt` w repo.

    Zapis jest PRZECHWYTYWANY, nie wykonywany: ten test istnieje po to, żeby
    suita nie dotykała prawdziwego pliku, więc sam też go nie dotyka."""
    zapisane: dict[str, Path] = {}
    prawdziwy_write = Path.write_text

    def _przechwyc(self, *a, **k):
        if Path(self).name == "next_final.txt":
            zapisane["cel"] = Path(self)
            return None
        return prawdziwy_write(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", _przechwyc)
    _zapisz_next_final_txt([{"kickoff": "2026-06-26T18:00:00"}])

    assert zapisane.get("cel") == _PRAWDZIWY
