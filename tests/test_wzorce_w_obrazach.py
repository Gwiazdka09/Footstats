"""Tablica wzorców musi jechać do repo i do obrazów — inaczej RAG nie ma paliwa.

PO CO: trzeci plik danych w tym projekcie, który ginął po drodze do produkcji.
Poprzednie dwa: `data/team_mappings.json` (aliasy nazw drużyn — produkcja
startowała z domyślnej garstki) i `data/model_calibration.json` (kalibracja
w kontenerze była dekoracją, bo `load_calibration()` czytało (1.0, 1.0)).
Za każdym razem objaw był ten sam: lokalnie zielono, w produkcji cicho inaczej.

Tu stawka jest wyższa: własnych rozliczonych predykcji z czynnikami jest na
produkcji ZERO, więc bez tego pliku `pobierz_rag_wzorce` zwraca pusty string
zawsze — a to nie do odróżnienia od "za mało danych historycznych".
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLIK = "data/rag_wzorce_historyczne.json"


def test_plik_wzorcow_jest_sledzony_przez_git() -> None:
    wynik = subprocess.run(
        ["git", "check-ignore", PLIK],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert wynik.returncode != 0, f"{PLIK} ignorowany — RAG zostanie bez paliwa"


def test_plik_wzorcow_kopiowany_do_obu_obrazow() -> None:
    """API liczy `/cron/draft`, joby licza predykcje dzienne — obie strony pytaja RAG."""
    for dockerfile in ("Dockerfile.api", "Dockerfile.jobs"):
        tresc = (ROOT / dockerfile).read_text(encoding="utf-8")
        assert PLIK in tresc, f"{dockerfile} nie kopiuje {PLIK}"


def test_filtry_budowania_nie_wycinaja_pliku() -> None:
    for nazwa, prefiks in ((".dockerignore", ""), (".gcloudignore", "/")):
        linie = [
            w.strip() for w in (ROOT / nazwa).read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.startswith("#")
        ]
        wycinajace = [w for w in linie if w in ("data/", "data", "data/*", "/data/*")]
        assert not wycinajace or f"!{prefiks}{PLIK}" in linie, (
            f"{nazwa} wycina data ({wycinajace}) bez negacji dla {PLIK}"
        )


def test_tablica_ma_tresc_a_nie_sam_szkielet() -> None:
    """Pusty plik przeszedlby poprzednie testy, a RAG dalej milczalby."""
    dane = json.loads((ROOT / PLIK).read_text(encoding="utf-8"))
    assert dane.get("wzorce"), "tablica bez wzorcow — RAG nadal bez paliwa"
    assert dane.get("n_meczow", 0) > 0


def test_kazdy_wzorzec_ma_sensowne_liczby() -> None:
    dane = json.loads((ROOT / PLIK).read_text(encoding="utf-8"))
    for klucz, w in dane["wzorce"].items():
        assert w["n"] > 0, f"{klucz}: n=0"
        assert 0 <= w["trafien"] <= w["n"], f"{klucz}: trafien poza zakresem"
        assert "->" in klucz, f"{klucz}: brak formatu czynnik->typ"


def test_tablica_niesie_date_zbudowania() -> None:
    """Bez `zbudowano_do` nie da sie wykryc lookaheadu w backtescie."""
    dane = json.loads((ROOT / PLIK).read_text(encoding="utf-8"))
    assert dane.get("zbudowano_do"), "brak daty — nie wiadomo, dokad siega tablica"
