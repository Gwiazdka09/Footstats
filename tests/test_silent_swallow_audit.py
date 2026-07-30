"""test_silent_swallow_audit.py — `except ...: pass` nie może się mnożyć.

Po co (incydent 2026-07-29): `/cron/draft` przez 9 dni zwracał `{'ok': False,
'error': 'brak BZZOIRO_KEY'}` przy HTTP 200, logując to na poziomie INFO. Pipeline
stał, scheduler raportował same sukcesy, nikt nic nie widział. Ta sama klasa błędu
— porażka nieodróżnialna od normalnej pracy — siedzi w każdym `except: pass`.

Nie da się (ani nie warto) usunąć wszystkich: w kodzie parsującym `except ValueError:
pass` przy opcjonalnej liczbie jest w porządku. Ale liczba nie ma prawa ROSNĄĆ bez
świadomej decyzji. Ten test zamraża stan i zmusza do uzasadnienia każdego nowego.

Gdy dodajesz uzasadnione połknięcie — podnieś PROG i opisz dlaczego w commicie.
Gdy usuwasz — obniż PROG, żeby nie zrobić miejsca na przyszły regres.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Stan zamrożony 2026-07-30, po dołożeniu logów w ścieżce rozliczeń
# (core/coupon_settlement.py — awaria DB nie może wyglądać jak „brak wyniku").
PROG = 72

# Ścieżki, gdzie ciche połknięcie jest wprost uzasadnione: teardown przeglądarki
# musi przeżyć każdy błąd, bo inaczej zostawia wiszący proces chromium.
ZWOLNIONE = ("scrapers/base_playwright.py",)


def _ciche_polkniecia(path: Path) -> int:
    """Liczy `except ...:` którego pierwszą instrukcją jest samo `pass`."""
    linie = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    ile = 0
    for i, ln in enumerate(linie):
        if not re.match(r"\s*except\b.*:\s*$", ln):
            continue
        for j in range(i + 1, min(i + 4, len(linie))):
            nast = linie[j].strip()
            if not nast or nast.startswith("#"):
                continue
            if nast == "pass":
                ile += 1
            break
    return ile


def _skan() -> dict[str, int]:
    wynik: dict[str, int] = {}
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC).as_posix()
        if any(rel.endswith(z) for z in ZWOLNIONE):
            continue
        if (n := _ciche_polkniecia(p)):
            wynik[rel] = n
    return wynik


def test_liczba_cichych_polkniec_nie_rosnie():
    per_plik = _skan()
    razem = sum(per_plik.values())
    assert razem <= PROG, (
        f"Liczba `except: pass` bez logu wzrosla do {razem} (prog {PROG}).\n"
        "Porazka polknieta bez sladu jest nieodrozialna od normalnej pracy — "
        "dokladnie tak ukryl sie 9-dniowy zastoj draftu.\n"
        "Dodaj log (choćby `log.debug`) albo swiadomie podnies PROG w tym pliku.\n\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(per_plik.items(), key=lambda x: -x[1])[:12])
    )


def test_prog_nie_jest_zawyzony():
    """Gdy ktoś posprząta, próg ma zejść — inaczej zostaje zapas na przyszły regres."""
    razem = sum(_skan().values())
    assert razem >= PROG - 5, (
        f"Cichych polkniec jest juz tylko {razem}, a PROG wynosi {PROG}. "
        "Obniz PROG do biezacej wartosci, zeby nie zostawiac marginesu na regres."
    )
