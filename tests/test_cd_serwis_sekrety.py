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


def _linie_bloku_sekretow() -> list[str]:
    """Surowe, niepuste linie wcięte wewnątrz `secrets: |`, bez żadnej filtracji."""
    # Szukamy LINII bedacej kluczem YAML, nie podciagu — komentarz nad blokiem
    # cytuje `secrets: |` slownie i naiwny `split` lapal wlasnie jego.
    wiersze = CD.read_text(encoding="utf-8").splitlines()
    start = next((i for i, w in enumerate(wiersze)
                  if re.match(r"^\s*secrets:\s*\|\s*$", w)), None)
    assert start is not None, "cd.yml nie ma bloku `secrets: |`"

    wciecie = len(wiersze[start]) - len(wiersze[start].lstrip()) + 2
    linie = []
    for surowa in wiersze[start + 1:]:
        if not surowa.strip():
            continue
        if len(surowa) - len(surowa.lstrip()) < wciecie:
            break          # koniec literal scalara (kolejny klucz YAML)
        linie.append(surowa.strip())
    return linie


def _sekrety_z_cd() -> set[str]:
    """Nazwy z bloku `secrets:` deployu serwisu (`NAZWA=SECRET:latest`)."""
    return {m.group(1) for m in
            (re.match(r"^([A-Z0-9_]+)=", s) for s in _linie_bloku_sekretow()) if m}


def test_blok_sekretow_nie_zawiera_komentarzy():
    """`secrets: |` to literal scalar — linia z `#` NIE jest komentarzem YAML.

    Trafia do `deploy-cloudrun` jako treść i wywala deploy. Kosztowało mnie to dwa
    położone deploye 2026-08-24, a poprzednia wersja tego strażnika przepuszczała
    błąd, bo sama pomijała linie z `#` — modelowała parser, którego akcja nie ma.
    Objaśnienia mają stać NAD blokiem, gdzie `#` jest prawdziwym komentarzem.
    """
    smieci = [s for s in _linie_bloku_sekretow()
              if not re.match(r"^[A-Z0-9_]+=[A-Za-z0-9_.-]+:[A-Za-z0-9]+$", s)]

    assert not smieci, (
        f"w bloku `secrets: |` sa linie, ktore nie sa mapowaniem sekretu: {smieci}"
    )


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
