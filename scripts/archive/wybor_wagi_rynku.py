#!/usr/bin/env python
"""wybor_wagi_rynku.py — ile głosu ma mieć model w 1X2, sprawdzone na holdoucie.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED zobaczeniem jakiejkolwiek liczby z siatki wag.

CO JUŻ WIEMY (pomiar z 04.09, n=120 351, 39 lig):
  * model SAM jest gorszy od zdewigowanej ceny w każdej lidze (−0.018..−0.052);
  * mieszanka jest gorsza od samej ceny w każdej lidze przy OBU wagach, jakie
    ten system ma w konfiguracji: 0.3 (kod) i 0.7 (produkcja);
  * szkoda maleje monotonicznie, im więcej głosu ma rynek: zbiorczo −0.0145
    przy 0.3 i −0.0027 przy 0.7.

CZEGO NIE WIEMY: czy przy jakiejś wadze POMIĘDZY 0.7 a 1.0 model dokłada jednak
tyle informacji ortogonalnej, że mieszanka bije samą cenę. Dwa punkty i trend
nie rozstrzygają, co jest w tej luce. To jest jedyne pytanie tego skryptu.

DLACZEGO HOLDOUT, A NIE SAM ARGMIN. Wybranie wagi minimalizującej Brier na tych
samych danych, na których ją oglądamy, to dopasowanie jednego parametru do szumu
— dokładnie klasa błędu, przez którą 14.08 padło 52 z 52 podzbiorów. Waga jest
skalarem, więc ryzyko jest mniejsze niż tam, ale nie zerowe, a koszt holdoutu
tutaj to zero (te same dane, jeden podział).

PODZIAŁ, USTALONY Z GÓRY:
  TRENING  mecze z datą <  2023-01-01
  HOLDOUT  mecze z datą >= 2023-01-01
Po dacie, nie losowo: chcemy wiedzieć, czy waga wybrana na przeszłości działa
na PÓŹNIEJSZYCH meczach, bo tak właśnie zostanie użyta.

SIATKA WAG RYNKU, ustalona z góry i pełna (raportujemy wszystkie, nie tylko
najlepszą): 0.0, 0.3, 0.5, 0.7, 0.85, 0.95, 1.0.
0.3 i 0.7 są w niej, bo to konfiguracje, które ten system realnie miał.
1.0 to sama cena — punkt odniesienia.

PROCEDURA, ZAMROŻONA:
  1. Na TRENINGU policz zbiorczy Brier dla każdej wagi. Wybierz `w*` = argmin.
     To jest JEDYNA decyzja podjęta na treningu.
  2. Na HOLDOUCIE policz sparowaną różnicę Brier(1.0) − Brier(w*), z SE ze
     sparowanych różnic. To jest JEDYNA liczba, która rozstrzyga.
  3. Osobno, bez wpływu na decyzję, raportuj Brier(1.0) − Brier(0.7) na
     holdoucie — czyli koszt ustawienia, które stoi na produkcji dzisiaj.
     To nie jest szukanie: 0.7 jest wdrożone, oceniamy stan zastany.

REGUŁA DECYZYJNA:
  * `w*` == 1.0                     → model nie dokłada nic do 1X2 przy żadnej
                                       wadze; rekomendacja: sama cena.
  * `w*` < 1.0 i z >= 2 na holdoucie → `w*` jest kandydatem do wdrożenia.
  * `w*` < 1.0 i z <  2 na holdoucie → wybór nie przeżył; traktujemy jak 1.0.
    Trening znalazł minimum, którego na nowych meczach nie ma.

DLACZEGO BRIER, A NIE ROI — skoro celem jest obstawianie. ROI wymaga reguły
selekcji, progu i stawkowania; każde z tych trzech to kolejny stopień swobody,
a przy 39 ligach i kilku progach wracamy dokładnie do 52 podzbiorów. Brier nie
ma ani jednego wolnego parametru. Kolejność jest też logiczna: jeśli model nie
dokłada INFORMACJI ponad cenę, żadna reguła stawkowania nie wyciągnie z niego
pieniędzy — nie ma z czego. Pytanie o ROI ma sens dopiero po dodatnim wyniku
tego pomiaru.

CZEGO TEN POMIAR NIE ZMIENIA: werdyktu, że model nie bije rynku. Nawet
najlepsza waga może co najwyżej zbliżyć mieszankę do samej ceny.
=============================================================================

    python scripts/wybor_wagi_rynku.py --zrzut sciezka/*.parquet
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from przewaga_nad_rynkiem import (  # noqa: E402
    brier_wieloklasowy, p_jednostronne, sparowana_roznica,
)

PODZIAL = "2023-01-01"
WAGI = (0.0, 0.3, 0.5, 0.7, 0.85, 0.95, 1.0)
WAGA_PRODUKCJI = 0.7
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}


def wczytaj(wzorce: list[str]) -> pd.DataFrame:
    pliki: list[str] = []
    for w in wzorce:
        pliki += sorted(glob.glob(w))
    if not pliki:
        raise SystemExit(f"Zero plikow dla {wzorce}")
    df = pd.concat([pd.read_parquet(p) for p in pliki], ignore_index=True)
    df = df[df["actual_res"].isin(WYNIK_NA_INDEKS)]
    df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
    return df.dropna(subset=["match_date"])


def rozklady(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(model, rynek, indeks wyniku). Wiersze bez ceny odpadają — nie ma z czym
    porownywac, a zostawienie ich mieszaloby dwa rozne pytania."""
    from footstats.core.wf_harness import devig_1x2

    model, rynek, y = [], [], []
    for r in df.itertuples(index=False):
        p = devig_1x2(r.odds_h, r.odds_d, r.odds_a)
        if p is None:
            continue
        model.append([r.pw, r.pr, r.pp])
        rynek.append([p["pw"], p["pr"], p["pp"]])
        y.append(WYNIK_NA_INDEKS[r.actual_res])
    return (np.array(model) / 100.0, np.array(rynek) / 100.0, np.array(y))


def brier_przy_wadze(model: np.ndarray, rynek: np.ndarray, y: np.ndarray,
                     w: float) -> np.ndarray:
    """Brier per mecz przy wadze rynku `w`. Liniowy blend, jak `ensemble_probs`."""
    return brier_wieloklasowy((1.0 - w) * model + w * rynek, y)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--zrzut", nargs="+", required=True)
    args = p.parse_args()

    df = wczytaj(args.zrzut)
    tren = df[df["match_date"] < PODZIAL]
    hold = df[df["match_date"] >= PODZIAL]
    print(f"Wczytane: {len(df)} meczow | trening {len(tren)} | holdout {len(hold)}")
    if len(tren) < 1000 or len(hold) < 1000:
        raise SystemExit("Za malo danych po podziale — nie liczę.")

    m_t, r_t, y_t = rozklady(tren)
    m_h, r_h, y_h = rozklady(hold)

    # ── KROK 1: wybor wagi, wylacznie na treningu ──────────────────────────
    print(f"\nKROK 1 — TRENING (mecze < {PODZIAL}), n={len(y_t)}")
    print(f"{'waga rynku':>12}{'Brier':>12}")
    brier_tren = {}
    for w in WAGI:
        b = float(brier_przy_wadze(m_t, r_t, y_t, w).mean())
        brier_tren[w] = b
        print(f"{w:>12.2f}{b:>12.5f}")
    w_gwiazdka = min(brier_tren, key=lambda k: brier_tren[k])
    print(f"\n  w* = {w_gwiazdka} (argmin na treningu — jedyna decyzja podjeta tutaj)")

    # ── KROK 2: jedyna liczba, ktora rozstrzyga ────────────────────────────
    print(f"\nKROK 2 — HOLDOUT (mecze >= {PODZIAL}), n={len(y_h)}")
    b_rynek = brier_przy_wadze(m_h, r_h, y_h, 1.0)

    def _ocen(w: float, etykieta: str) -> None:
        b_w = brier_przy_wadze(m_h, r_h, y_h, w)
        d = sparowana_roznica(b_rynek, b_w)   # dodatnie = `w` lepsze od ceny
        # w=1.0 porownuje cene SAMA ZE SOBA: roznice sa zerami co do bitu, wiec
        # SE=0 i `z` nie istnieje. To nie awaria, tylko definicja punktu
        # odniesienia — wiersz ma sie wypisac, zeby bylo widac wartosc Briera.
        if d["z"] is None:
            print(f"  {etykieta:<34} Brier {float(b_w.mean()):.5f}"
                  f"  (punkt odniesienia)")
            return
        print(f"  {etykieta:<34} Brier {float(b_w.mean()):.5f}"
              f"  vs cena {d['roznica']:+.5f}  SE {d['se']:.5f}"
              f"  z {d['z']:+.2f}  p {p_jednostronne(d['z']):.4f}")

    _ocen(1.0, "sama cena (odniesienie)")
    _ocen(w_gwiazdka, f"w* = {w_gwiazdka} (wybrane na treningu)")
    _ocen(WAGA_PRODUKCJI, f"produkcja = {WAGA_PRODUKCJI} (stan zastany)")

    b_w = brier_przy_wadze(m_h, r_h, y_h, w_gwiazdka)
    d = sparowana_roznica(b_rynek, b_w)
    z = d["z"] or 0.0

    print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
    if w_gwiazdka >= 1.0:
        print("    w* = 1.0 -> model nie doklada nic do 1X2 przy ZADNEJ wadze.")
        print("    Rekomendacja: sama cena. Bez ROI, bez podzbiorow.")
    elif z >= 2:
        print(f"    w* = {w_gwiazdka} przezylo holdout (z={z:+.2f}) -> KANDYDAT do wdrozenia.")
        print("    Dopiero teraz pytanie o ROI ma sens.")
    else:
        print(f"    w* = {w_gwiazdka} NIE przezylo holdoutu (z={z:+.2f}) -> traktujemy jak 1.0.")
        print("    Trening znalazl minimum, ktorego na nowych meczach nie ma.")
    print("\n  To i tak nie zmienia werdyktu, ze model nie bije rynku —")
    print("  najlepsza waga moze co najwyzej zblizyc mieszanke do samej ceny.")


if __name__ == "__main__":
    main()
