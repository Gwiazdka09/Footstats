"""Serwis API musi dostać KAŻDY klucz, którego czyta jego własny kod.

ZNALEZIONE 2026-08-24: `FOOTBALL_API_KEY` był w Secret Managerze i na obu jobach,
ale **nie na serwisie `footstats-api`**. A to serwis obsługuje `/cron/settle` —
scheduler `footstats-settle-morning`/`-evening` uderza pod jego URL. Skutek:
`settle_active_coupons` czytało `os.getenv("FOOTBALL_API_KEY")`, dostawało pustkę
i `_get_matches_fdb` kończyło się `return []` bez jednego zapytania.

Czyli football-data.org — JEDYNE źródło z pełną historią, pozostałe sięgają
1 dnia (API-Football, plan darmowy) i ~7 dni (FlashScore) — nigdy nie brało
udziału w codziennym rozliczaniu. Dlatego zawieszenie konta API-Football 16.08
zatrzymało rozliczanie na osiem dni: warstwa, która miała być zapasem, nie
istniała, choć klucz do niej leżał obok.

To ten sam kształt co incydent logowania z 27.07 — brakujący sekret na Cloud Run,
awaria wyglądająca na coś zupełnie innego. Wtedy odpowiedzią było re-asertowanie
sekretów przy każdym deployu (`cd.yml`). Ten test pilnuje, żeby lista w `cd.yml`
nadążała za tym, co kod naprawdę czyta.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]
CD = KORZEN / ".github" / "workflows" / "cd.yml"
ROZLICZANIE = KORZEN / "src" / "footstats" / "core" / "coupon_settlement.py"


def _sekrety_z_cd() -> set[str]:
    """Nazwy z bloku `secrets:` deployu serwisu (`NAZWA=SECRET:latest`)."""
    tresc = CD.read_text(encoding="utf-8")
    blok = tresc.split("secrets: |", 1)
    assert len(blok) == 2, "cd.yml nie ma bloku `secrets: |`"
    nazwy = set()
    for linia in blok[1].splitlines():
        s = linia.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([A-Z0-9_]+)=", s)
        if not m:
            break          # koniec bloku (kolejny klucz YAML)
        nazwy.add(m.group(1))
    return nazwy


@pytest.mark.parametrize("klucz", ["FOOTBALL_API_KEY", "APISPORTS_KEY"])
def test_klucze_zrodel_wynikow_sa_reasertowane(klucz: str):
    """Bez nich `_find_leg_result` cicho traci źródło i zwraca None jak przy remisie."""
    assert klucz in _sekrety_z_cd(), (
        f"{klucz} nie jest re-asertowany w cd.yml — serwis może go nie mieć, "
        "a rozliczanie milczy o brakującym źródle"
    )


def test_kazdy_klucz_czytany_przez_rozliczanie_jest_w_cd():
    """Strażnik rośnie razem z kodem: nowy `os.getenv("*_KEY")` w rozliczaniu
    bez wpisu w cd.yml zapala się tutaj, a nie po ośmiu dniach ciszy."""
    czytane = set(re.findall(r'os\.getenv\(\s*"([A-Z0-9_]*KEY)"',
                             ROZLICZANIE.read_text(encoding="utf-8")))
    assert czytane, "nie znaleziono zadnego odczytu klucza — wzorzec sie rozjechal"

    brakujace = czytane - _sekrety_z_cd()
    assert not brakujace, (
        f"rozliczanie czyta {sorted(brakujace)}, ale cd.yml tego nie re-asertuje"
    )


def test_secrets_update_strategy_to_merge():
    """`merge` chroni zmienne ustawione ręcznie na serwisie (np. flagi).
    Zamiana na `overwrite` zdmuchnęłaby je przy najbliższym deployu."""
    assert "secrets_update_strategy: merge" in CD.read_text(encoding="utf-8")
