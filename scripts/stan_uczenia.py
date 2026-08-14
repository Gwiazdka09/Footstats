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
    _raport_kursow(conn)
    return {w["model_source"]: w for w in wiersze}


def _raport_kursow(conn) -> None:
    """Ile predykcji ma kurs POTWIERDZONY, a ile tylko zaproponowany przez Groqa.

    Zapis do `predictions` dzieje sie w KROKU 3 `daily_agent`, a anty-halucynacyjna
    podmiana kursu dopiero w KROKU 4 — wiersze sprzed uzgodnienia (migracja 13)
    trzymaja kurs od modelu jezykowego. Na prodzie oznaczalo to ten sam kurs 52.58
    na trzech roznych meczach jednego dnia. ROI i CLV z takich wierszy nie znacza nic.
    """
    try:
        wiersze = _licz(conn, """
            SELECT COUNT(*) AS wszystkie,
                   COALESCE(SUM(CASE WHEN COALESCE(odds_verified, 0) = 1 THEN 1 ELSE 0 END), 0)
                       AS zweryfikowane,
                   COALESCE(SUM(CASE WHEN odds IS NOT NULL AND (odds < 1.2 OR odds > 4.0)
                                     THEN 1 ELSE 0 END), 0) AS poza_filtrem
            FROM predictions
        """)
    except Exception as e:                                   # noqa: BLE001
        # Skrypt chodzi lokalnie przeciw produkcji, a migracja 13 wchodzi dopiero
        # z nowym obrazem — brak kolumny to stan przejsciowy, nie awaria. Ale musi
        # byc WIDOCZNY, inaczej raport milczy o tym, ze kursy sa niezweryfikowane.
        if "odds_verified" in str(e):
            # Postgres zostawia transakcje w stanie aborted — bez rollbacku KAZDY
            # kolejny raport w tym polaczeniu pada, i to na cudzym zapytaniu.
            try:
                conn.rollback()
            except Exception:                                # noqa: BLE001
                pass
            print("\n  kurs zweryfikowany: BRAK KOLUMNY — migracja 13 niewdrozona."
                  "\n  → wszystkie kursy w `predictions` pochodza sprzed weryfikacji (KROK 4).")
            return
        raise
    if not wiersze:
        return
    w = wiersze[0]
    if not w.get("wszystkie"):
        return
    udzial = 100.0 * w["zweryfikowane"] / w["wszystkie"]
    print(f"\n  kurs zweryfikowany: {w['zweryfikowane']}/{w['wszystkie']} ({udzial:.0f}%)")
    if w["poza_filtrem"]:
        print(f"  kurs poza filtrem longshotow 1.2-4.0: {w['poza_filtrem']}"
              f" — te wiersze opisuja PROPOZYCJE, nie zagrane typy")
    if udzial < 100.0:
        print("  → ROI i CLV licz wylacznie na zweryfikowanych"
              " (reszta to kurs zaproponowany przez Groqa).")


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


def raport_dziennika(conn) -> dict:
    """Skuteczność z `model_log` — dziennika zapisywanego PRZED filtrami wartości.

    PO CO OSOBNO OD `predictions`: tamta tabela dostaje wiersz dopiero wtedy, gdy
    mecz przejdzie filtry i nadaje się do obstawienia. 2026-08-13 produkcja:
    `kandydaci=45, po filtrach=0` — trzeci dzień z rzędu zero predykcji, więc
    raport pokazywał pętlę jako martwą. `model_log` w tym samym tygodniu zebrał
    202 oceny, z czego 105 rozliczonych. Dane były, tylko nikt ich nie czytał.
    """
    wiersze = _licz(conn, """
        SELECT model_source,
               COUNT(*) AS wpisow,
               COUNT(actual_result) AS rozliczone,
               COALESCE(SUM(tip_correct), 0) AS trafione
        FROM model_log
        GROUP BY model_source
        ORDER BY wpisow DESC
    """)
    print("\n=== DZIENNIK MODELU (model_log — przed filtrami) ===")
    if not wiersze:
        print("  PUSTY — to AWARIA, nie brak paliwa.")
        print("  `model_log` zapisuje się przed filtrami, więc pustka znaczy,")
        print("  że przebieg nie doszedł nawet do oceny modelu.")
        return {}

    print(f"{'model':14} {'wpisow':>7} {'rozliczone':>11} {'trafione':>9} {'skutecznosc':>12}")
    for w in wiersze:
        rozl = w["rozliczone"] or 0
        skut = f"{100.0 * w['trafione'] / rozl:.1f}%" if rozl else "—"
        print(f"{str(w['model_source'] or '(brak)'):14} {w['wpisow']:7}"
              f" {rozl:11} {w['trafione']:9} {skut:>12}")
    return {w["model_source"]: w for w in wiersze}


def raport_gotowosci(pred: dict, dziennik: dict | None = None) -> None:
    """Ile brakuje do werdyktu `porownaj_modele`.

    Liczy z WIĘKSZEJ z dwóch prób. `predictions` widzi wyłącznie mecze, które
    przeszły filtry wartości, więc samo z siebie każe czekać na dane, które
    już mamy w `model_log` (10 vs 23 rozliczonych dla poisson-dc na 13.08).
    """
    dziennik = dziennik or {}
    print("\n=== GOTOWOŚĆ DO WERDYKTU ===")
    for model in ("poisson-dc", "bzzoiro-ml"):
        n_pred = pred.get(model, {}).get("rozliczone", 0)
        n_dzien = dziennik.get(model, {}).get("rozliczone", 0)
        n = max(n_pred, n_dzien)
        zrodlo = "model_log" if n_dzien > n_pred else "predictions"
        brakuje = max(0, MIN_ROZLICZONYCH - n)
        stan = "gotowe" if not brakuje else f"brakuje {brakuje}"
        print(f"  {model:12} rozliczonych {n:4} / {MIN_ROZLICZONYCH} — {stan} ({zrodlo})")


def main() -> None:
    from footstats.utils.db import connect

    with connect() as conn:
        pred = raport_predykcji(conn)
        raport_lekcji(conn)
        raport_wzorcow(conn)
        dziennik = raport_dziennika(conn)
        raport_gotowosci(pred, dziennik)


if __name__ == "__main__":
    main()
