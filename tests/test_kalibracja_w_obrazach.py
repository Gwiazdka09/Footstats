"""Plik kalibracji musi jechać do repo i do obrazów, tak jak aliasy nazw.

PO CO: `data/model_calibration.json` był ignorowany razem z całym `/data/`
i żaden Dockerfile go nie kopiował. Na produkcji `load_calibration()` nie
znajdowało pliku i zwracało neutralne `(1.0, 1.0)` — czyli CAŁA warstwa
kalibracji była tam dekoracją. Gorzej: lokalnie plik istniał z factorami
0.9715/0.9545, więc pomiary robione na dysku dewelopera opisywały INNY model
niż ten, który realnie liczył predykcje w kontenerze.

Dokładnie ta sama klasa co `data/team_mappings.json` (patrz
`test_aliasy_w_obrazach.py`) i co brakujący `pyarrow`: lokalnie zielono,
w produkcji cicho inaczej.

Uwaga na `/data/*` w `.gitignore`: git NIE potrafi odzyskać pliku, którego
katalog jest wykluczony — negacja działa tylko przy wzorcu z gwiazdką.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLIK = "data/model_calibration.json"


def test_plik_kalibracji_jest_sledzony_przez_git() -> None:
    wynik = subprocess.run(
        ["git", "check-ignore", PLIK],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert wynik.returncode != 0, (
        f"{PLIK} jest ignorowany przez gita — kalibracja nie trafi do obrazu"
    )


def test_plik_kalibracji_kopiowany_do_obu_obrazow() -> None:
    """API liczy predykcje, joby rozliczaja — obie strony musza znac te same factory."""
    for dockerfile in ("Dockerfile.api", "Dockerfile.jobs"):
        tresc = (ROOT / dockerfile).read_text(encoding="utf-8")
        assert PLIK in tresc, f"{dockerfile} nie kopiuje {PLIK}"


def test_filtry_budowania_nie_wycinaja_pliku() -> None:
    """`COPY` nie pomoze, jesli plik odpadnie z kontekstu budowania."""
    for nazwa, prefiks in ((".dockerignore", ""), (".gcloudignore", "/")):
        linie = [
            w.strip() for w in (ROOT / nazwa).read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.startswith("#")
        ]
        wycinajace = [w for w in linie if w in ("data/", "data", "data/*", "/data/*")]
        assert not wycinajace or f"!{prefiks}{PLIK}" in linie, (
            f"{nazwa} wycina data ({wycinajace}) bez negacji dla {PLIK}"
        )


def test_zapisane_factory_sa_w_szynach_bezpieczenstwa() -> None:
    """Plik jedzie na produkcje, wiec jego zawartosc tez musi byc pilnowana.

    Safety rail [0.85, 1.15] istnieje po to, zeby jeden dziwny przebieg
    walk-forward nie rozjechal wszystkich przyszlych predykcji.
    """
    dane = json.loads((ROOT / PLIK).read_text(encoding="utf-8"))
    for klucz in ("factor_home", "factor_away"):
        wartosc = dane.get(klucz)
        assert wartosc is not None, f"brak {klucz} w {PLIK}"
        assert 0.85 <= wartosc <= 1.15, f"{klucz}={wartosc} poza szynami"


def test_kalibracja_opisuje_na_ilu_meczach_powstala() -> None:
    """Bez `n_matches` nie da sie odroznic kalibracji z 200 meczow od tej z 3000."""
    dane = json.loads((ROOT / PLIK).read_text(encoding="utf-8"))
    assert int(dane.get("n_matches", 0)) > 0
