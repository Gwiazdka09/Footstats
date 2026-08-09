"""Wzorce czynnik→typ z historii — paliwo dla RAG, którego w bazie nie ma.

PO CO: `rag.pobierz_rag_wzorce` liczy skuteczność czynników z tabeli
`predictions`. Zmierzone na produkcji 09.08.2026: **0 rozliczonych predykcji
z niepustymi `factors`**. Funkcja zwraca więc pusty string niezależnie od
zapytania i będzie tak robić tygodniami — przy ~4 predykcjach dziennie i 29%
szansie, że jakikolwiek czynnik się zapali.

Obok leży 139 102 mecze historii. Zmierzone walk-forwardem na 2492 meczach
10 lig (baza: trafność typu modelu 47,5%):

    PATENT    n=170  57,6%  (+10,1 pp)
    TWIERDZA  n=496  53,4%  (+5,9 pp)
    ZEMSTA    n=199  45,7%  (−1,8 pp), ale gospodarz wygrywa 31,7% vs 43,0%

Czynniki niosą realny sygnał, więc tablica historyczna nie jest protezą —
jest lepszym źródłem niż garstka własnych predykcji.

LOOKAHEAD: tablica agreguje mecze DO daty budowy i służy meczom PÓŹNIEJSZYM.
Stąd pole `zbudowano_do` — bez niego nie da się stwierdzić, czy backtest na
starym oknie nie czyta własnej przyszłości.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SCIEZKA = Path(__file__).resolve().parents[3] / "data" / "rag_wzorce_historyczne.json"

# Poniżej tylu meczów odsetek trafień jest szumem. 30 spójne z progiem
# werdyktu w `scripts/porownaj_modele.py`.
MIN_PROBEK = 30

# Ile wzorców trafia do promptu. Prompt pękł 09.08 na limicie tokenów, więc
# warstwa RAG ma być zwięzła: trzy najlepiej udokumentowane wystarczą.
MAX_W_PROMPCIE = 3

# Kombinacje dłuższe niż to dzielą próbkę na kawałki bez wartości statystycznej.
MAX_CZYNNIKOW_W_KOMBINACJI = 2


def buduj_tablice(
    mecze: list[dict],
    min_probek: int = MIN_PROBEK,
    zbudowano_do: str | None = None,
) -> dict:
    """Z rekordów walk-forwardu buduje {"PATENT->H": {"n": …, "trafien": …}}.

    Rekord: {"typ": typ modelu, "czynniki": [...], "wynik": faktyczny}.
    Rekordy niepełne są pomijane — lepiej mniejsza tablica niż wzorzec zbudowany
    na domyślnych wartościach.
    """
    zliczenia: dict[str, dict[str, int]] = {}

    for m in mecze:
        typ, wynik = m.get("typ"), m.get("wynik")
        czynniki = m.get("czynniki") or []
        if not typ or not wynik or not czynniki:
            continue

        posortowane = sorted(czynniki)
        klucze = [f"{c}->{typ}" for c in posortowane]
        if len(posortowane) >= 2:
            for i in range(len(posortowane)):
                for j in range(i + 1, len(posortowane)):
                    klucze.append(f"{posortowane[i]}+{posortowane[j]}->{typ}")

        for klucz in klucze:
            wpis = zliczenia.setdefault(klucz, {"n": 0, "trafien": 0})
            wpis["n"] += 1
            wpis["trafien"] += int(typ == wynik)

    wzorce = {k: v for k, v in zliczenia.items() if v["n"] >= min_probek}
    return {
        "wzorce": wzorce,
        "n_meczow": len(mecze),
        "min_probek": min_probek,
        "zbudowano_do": zbudowano_do,
    }


def wczytaj_tablice() -> dict:
    """Tablica z dysku. Brak albo uszkodzony plik → {} (RAG degraduje, nie pada)."""
    if not SCIEZKA.exists():
        return {}
    try:
        dane = json.loads(SCIEZKA.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("[RAG] Nie moge wczytac wzorcow historycznych: %s", e)
        return {}
    return dane if isinstance(dane, dict) else {}


def formatuj_wzorce(tablica: dict, czynniki: list[str], tip: str) -> str:
    """Linia do promptu: "PATENT->1: 98/170(58%) | TWIERDZA->1: 265/496(53%)".

    Zwraca "" gdy nic nie pasuje — wołający ma wtedy zachować się dokładnie tak,
    jak przy braku danych, a nie wstawiać do promptu pustych nawiasów.
    """
    wzorce = (tablica or {}).get("wzorce") or {}
    if not wzorce or not czynniki:
        return ""

    posortowane = sorted(czynniki)
    kandydaci = [f"{c}->{tip}" for c in posortowane]
    for i in range(len(posortowane)):
        for j in range(i + 1, len(posortowane)):
            kandydaci.append(f"{posortowane[i]}+{posortowane[j]}->{tip}")

    trafione = []
    for klucz in kandydaci:
        w = wzorce.get(klucz)
        if not w or not w.get("n"):
            continue
        trafione.append((w["n"], klucz, w["trafien"]))

    # Najlepiej udokumentowane najpierw — przy limicie tokenów liczy się to,
    # co ma najmocniejszą podstawę, nie to, co brzmi najciekawiej.
    trafione.sort(reverse=True)
    czesci = [
        f"{klucz}: {trafien}/{n}({round(trafien / n * 100)}%)"
        for n, klucz, trafien in trafione[:MAX_W_PROMPCIE]
    ]
    return " | ".join(czesci)
