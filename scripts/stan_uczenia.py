"""Raport stanu pętli uczenia — co realnie wchodzi, a co stoi. TYLKO ODCZYT.

PO CO: pętla ma cztery ogniwa i każde potrafi paść po cichu, dając ten sam
objaw co „jeszcze za mało danych":

    predykcja z `factors` → rozliczenie → lekcja w `ai_feedback` → wzorzec z RAG

Historia projektu to lista takich cichych awarii: `json_each` nie istnieje na
PostgreSQL (RAG milczał zawsze), `data_full` w heurystyce zmęczenia (tagi nie
zapalały się ani razu), brak `sentence-transformers` wywalający CAŁY blok
lekcji. Wszystkie z zielonymi testami. Ten raport pyta produkcję wprost.

Użycie:
    python -m scripts.stan_uczenia
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Próg z `scripts/porownaj_modele.py` — poniżej niego werdykt nie zapada.
MIN_ROZLICZONYCH = 30


def _licz(conn, zapytanie: str) -> list[dict]:
    return [dict(r) for r in conn.execute(zapytanie).fetchall()]


def raport_predykcji(conn) -> dict:
    """Ile predykcji ma niepuste `factors` — kryterium odbioru U1."""
    wiersze = _licz(conn, """
        SELECT model_source,
               COUNT(*) AS wszystkie,
               COUNT(*) FILTER (WHERE factors <> '[]' AND factors <> '') AS z_faktorami,
               COUNT(tip_correct) AS rozliczone,
               COALESCE(SUM(tip_correct), 0) AS trafione
        FROM predictions
        GROUP BY model_source
        ORDER BY wszystkie DESC
    """)
    print("=== PREDYKCJE ===")
    print(f"{'model':14} {'razem':>7} {'z factors':>10} {'rozliczone':>11} {'trafione':>9}")
    for w in wiersze:
        print(f"{str(w['model_source'] or '(brak)'):14} {w['wszystkie']:7}"
              f" {w['z_faktorami']:10} {w['rozliczone']:11} {w['trafione']:9}")
    return {w["model_source"]: w for w in wiersze}


def raport_lekcji(conn) -> None:
    """Lekcje uczą się TYLKO z porażek — pokazujemy skalę tego przechyłu."""
    wiersz = _licz(conn, """
        SELECT COUNT(*) AS lekcji,
               COUNT(DISTINCT match_id) AS meczow
        FROM ai_feedback
    """)[0]
    rozliczone = _licz(conn, """
        SELECT COALESCE(SUM(CASE WHEN tip_correct = 0 THEN 1 ELSE 0 END), 0) AS porazki,
               COALESCE(SUM(CASE WHEN tip_correct = 1 THEN 1 ELSE 0 END), 0) AS sukcesy
        FROM predictions WHERE tip_correct IS NOT NULL
    """)[0]

    print("\n=== LEKCJE (ai_feedback) ===")
    print(f"  lekcji: {wiersz['lekcji']} | dotyczą {wiersz['meczow']} meczów")
    print(f"  rozliczone predykcje: {rozliczone['porazki']} porażek"
          f" / {rozliczone['sukcesy']} trafień")
    if rozliczone["porazki"]:
        pokrycie = wiersz["meczow"] / rozliczone["porazki"] * 100
        print(f"  pokrycie porażek lekcjami: {pokrycie:.0f}%")
    print("  UWAGA: `_pobierz_porazki` bierze wyłącznie tip_correct = 0 —"
          " baza lekcji jest z definicji jednostronna.")


def raport_wzorcow(conn) -> None:
    """Czy RAG ma z czego liczyć wzorzec: rozliczone predykcje Z czynnikami."""
    wiersz = _licz(conn, """
        SELECT COUNT(*) AS gotowe
        FROM predictions
        WHERE tip_correct IS NOT NULL
          AND factors <> '[]' AND factors <> ''
    """)[0]
    print("\n=== WZORCE RAG ===")
    print(f"  rozliczonych predykcji z czynnikami: {wiersz['gotowe']}")
    if not wiersz["gotowe"]:
        print("  → `pobierz_rag_wzorce` zwróci pusty string niezależnie od zapytania.")
        print("    To NIE jest awaria — to brak paliwa.")


def raport_gotowosci(pred: dict) -> None:
    """Ile brakuje do werdyktu `porownaj_modele`."""
    print("\n=== GOTOWOŚĆ DO WERDYKTU ===")
    for model in ("poisson-dc", "bzzoiro-ml"):
        n = pred.get(model, {}).get("rozliczone", 0)
        brakuje = max(0, MIN_ROZLICZONYCH - n)
        stan = "gotowe" if not brakuje else f"brakuje {brakuje}"
        print(f"  {model:12} rozliczonych {n:4} / {MIN_ROZLICZONYCH} — {stan}")


def main() -> None:
    from footstats.utils.db import connect

    with connect() as conn:
        pred = raport_predykcji(conn)
        raport_lekcji(conn)
        raport_wzorcow(conn)
        raport_gotowosci(pred)


if __name__ == "__main__":
    main()
