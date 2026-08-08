"""Przenosi historię predykcji i lekcji AI z Neona do Supabase.

PO CO: Neon był produkcyjną bazą do 20.07, potem zablokowała go quota i cała
historia — 195 predykcji, w tym 108 rozliczonych, oraz 117 lekcji `ai_feedback`
— przestała być dostępna. Supabase ma własne wiersze dopiero od 20.07, więc
kalibracja i RAG uczyły się z garstki danych. Neon odblokował się 08.08.

CZEGO TEN SKRYPT NIE ROBI: nie przenosi kuponów, bankrollu ani userów. Kupony
Neona wiszą na 7 kontach, których w Supabase nie ma, a 11 z nich ma status
ACTIVE sprzed miesięcy — wskrzeszanie ich zafałszowałoby bieżący bankroll.
To osobna decyzja.

BEZPIECZEŃSTWO:
  * domyślnie `--dry`, czyli pokazuje co BY zrobił i nic nie zapisuje;
  * dedup po kluczu naturalnym (drużyny + data + typ), więc powtórne
    uruchomienie jest bezczynne;
  * `id` NIE są przenoszone — zakresy obu baz kolidują (Neon 1-242,
    Supabase 1-26). Nowe nadaje sekwencja, a `ai_feedback.match_id` jest
    przemapowywany na te nowe wartości;
  * każdy wiersz dostaje `model_source='bzzoiro-ml'`, bo cała ta historia
    powstała, zanim Poisson zaczął działać na produkcji (07.08). Bez stempla
    wpadłaby do porównania jako predykcja naszego modelu.

Użycie:
    python -m scripts.import_neon_do_supabase           # podgląd
    python -m scripts.import_neon_do_supabase --zapisz  # realny zapis
"""
from __future__ import annotations

import argparse
import sys

# Era sprzed naprawy Poissona — patrz docstring.
ZRODLO_HISTORYCZNE = "bzzoiro-ml"

# Kolumny predykcji przenoszone 1:1. Bez `id` (kolizja zakresów) i bez
# `coupon_id` (wskazywałby na kupon z innej bazy; w Neonie pusty we wszystkich).
KOLUMNY_PREDYKCJI = (
    "created_at", "match_date", "team_home", "team_away", "league",
    "ai_tip", "ai_confidence", "ai_reasoning", "odds", "actual_result",
    "tip_correct", "kupon_type", "kodeks_rules_checked", "prompt_version",
    "factors", "match_stats", "prob_home", "prob_draw", "prob_away",
    "model_source",
)

KOLUMNY_LEKCJI = ("created_at", "match_id", "prediction_details", "reason_for_failure")


def klucz_predykcji(p: dict) -> tuple[str, str, str, str]:
    """Klucz naturalny meczu i typu — ten sam, którego używa `save_prediction`.

    Data ucinana do dnia, bo źródła zapisują ją raz z godziną, raz bez.
    """
    return (
        str(p.get("team_home") or "").strip(),
        str(p.get("team_away") or "").strip(),
        str(p.get("match_date") or "")[:10],
        str(p.get("ai_tip") or "").strip(),
    )


def wiersze_do_wstawienia(zrodlo: list[dict], istniejace: set) -> list[dict]:
    """Predykcje, których w celu jeszcze nie ma, gotowe do INSERT-a.

    Odsiewa też duplikaty w samym źródle — inaczej jedno uruchomienie
    wstawiłoby ten sam mecz dwa razy i dopiero drugie byłoby bezczynne.
    """
    widziane = set(istniejace)
    wynik: list[dict] = []
    for p in zrodlo:
        k = klucz_predykcji(p)
        if k in widziane:
            continue
        widziane.add(k)
        wiersz = {kol: p.get(kol) for kol in KOLUMNY_PREDYKCJI if kol in p}
        wiersz["model_source"] = p.get("model_source") or ZRODLO_HISTORYCZNE
        wynik.append(wiersz)
    return wynik


def remapuj_lekcje(lekcje: list[dict], mapa_id: dict) -> tuple[list[dict], int]:
    """Podmienia `match_id` na nowe id predykcji. Zwraca (gotowe, liczba sierot).

    Lekcja bez odpowiadającej predykcji jest pomijana: `match_id` jest NOT NULL,
    a podpięcie jej pod cudzy mecz byłoby gorsze niż utrata jednego wniosku.
    """
    gotowe: list[dict] = []
    sieroty = 0
    for lekcja in lekcje:
        nowe = mapa_id.get(lekcja.get("match_id"))
        if nowe is None:
            sieroty += 1
            continue
        wiersz = {kol: lekcja.get(kol) for kol in KOLUMNY_LEKCJI if kol in lekcja}
        wiersz["match_id"] = nowe
        gotowe.append(wiersz)
    return gotowe, sieroty


# ─────────────────────────── wykonanie ────────────────────────────────────

def _polacz(zmienna: str):
    import psycopg2
    from dotenv import dotenv_values
    url = (dotenv_values(".env").get(zmienna) or "").strip()
    if not url:
        sys.exit(f"BLAD: brak {zmienna} w .env")
    return psycopg2.connect(url, connect_timeout=30)


def _wstaw(cur, tabela: str, wiersze: list[dict], dozwolone: tuple[str, ...]) -> list[int]:
    """Wstawia wiersze pojedynczo, zwracając nadane id w tej samej kolejności.

    Nazwy tabeli i kolumn składane przez `psycopg2.sql.Identifier`, nie f-stringiem:
    identyfikatory pochodzą z drugiej bazy, a wartości i tak lecą parametrami.
    `dozwolone` domyka to od drugiej strony — kolumna spoza białej listy
    przerywa import zamiast trafić do zapytania.
    """
    from psycopg2 import sql

    nowe: list[int] = []
    for w in wiersze:
        kolumny = list(w)
        obce = [k for k in kolumny if k not in dozwolone]
        if obce:
            raise ValueError(f"kolumny spoza bialej listy dla {tabela}: {obce}")
        zapytanie = sql.SQL("INSERT INTO {tab} ({kols}) VALUES ({param}) RETURNING id").format(
            tab=sql.Identifier(tabela),
            kols=sql.SQL(", ").join(sql.Identifier(k) for k in kolumny),
            param=sql.SQL(", ").join(sql.Placeholder() * len(kolumny)),
        )
        cur.execute(zapytanie, [w[k] for k in kolumny])
        nowe.append(cur.fetchone()[0])
    return nowe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zapisz", action="store_true",
                        help="realny zapis do Supabase (domyslnie tylko podglad)")
    args = parser.parse_args()

    import psycopg2.extras

    neon = _polacz("DATABASE_URL_NEON")
    cel = _polacz("DATABASE_URL_SUPABASE")
    try:
        c_neon = neon.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c_neon.execute("SELECT * FROM predictions ORDER BY id")
        predykcje = [dict(r) for r in c_neon.fetchall()]
        c_neon.execute("SELECT * FROM ai_feedback ORDER BY id")
        lekcje = [dict(r) for r in c_neon.fetchall()]

        c_cel = cel.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c_cel.execute("SELECT team_home, team_away, match_date, ai_tip FROM predictions")
        istniejace = {klucz_predykcji(dict(r)) for r in c_cel.fetchall()}

        do_wstawienia = wiersze_do_wstawienia(predykcje, istniejace)
        print(f"predykcje w Neonie: {len(predykcje)} | juz w Supabase: {len(istniejace)}")
        print(f"predykcje do wstawienia: {len(do_wstawienia)}")

        if not args.zapisz:
            # Bez realnych id nie da się przemapować lekcji — pokaż ile ich jest.
            klucze = {klucz_predykcji(p): p["id"] for p in predykcje}
            wstawiane = {klucz_predykcji(w) for w in do_wstawienia}
            mozliwe = {i for k, i in klucze.items() if k in wstawiane}
            trafne = sum(1 for lekcja in lekcje if lekcja.get("match_id") in mozliwe)
            print(f"lekcje w Neonie: {len(lekcje)} | z predykcja w tej partii: {trafne}")
            print("\nPODGLAD — nic nie zapisano. Powtorz z --zapisz.")
            return

        cur = cel.cursor()
        nowe_id = _wstaw(cur, "predictions", do_wstawienia, KOLUMNY_PREDYKCJI)
        mapa = {}
        for wiersz, nid in zip(do_wstawienia, nowe_id):
            for p in predykcje:
                if klucz_predykcji(p) == klucz_predykcji(wiersz):
                    mapa[p["id"]] = nid
                    break

        gotowe_lekcje, sieroty = remapuj_lekcje(lekcje, mapa)
        wstawione_lekcje = _wstaw(cur, "ai_feedback", gotowe_lekcje, KOLUMNY_LEKCJI)
        cel.commit()

        print(f"ZAPISANO: predykcje {len(nowe_id)} | lekcje {len(wstawione_lekcje)}"
              f" | lekcje bez predykcji (pominiete): {sieroty}")
    finally:
        neon.close()
        cel.close()


if __name__ == "__main__":
    main()
