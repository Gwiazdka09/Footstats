#!/usr/bin/env python
"""cena_plus_korekta.py — czy model poprawia CENĘ, zamiast z nią konkurować.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED policzeniem czegokolwiek.

DLACZEGO TO PYTANIE NIE PADŁO WCZEŚNIEJ, MIMO ŻE JEST OCZYWISTE. Każdy pomiar
tego projektu pytał „czy model bije cenę". Odpowiedź brzmi nie, 39 lig na 39.
Ale to jest inne pytanie niż „czy cena POPRAWIONA o model bije samą cenę" —
a właśnie tam mieszka jedyny znany nam dodatni sygnał: model łapie 31%
osiągalnego ruchu linii (`sygnal_czy_artefakt.py`, R² cząstkowe 0.00158
kontra 0.00495).

Wybór wagi ensemble odpowiadał na to częściowo i dał `w* = 1.0` — ale liczył
mieszankę LINIOWĄ ze średnią bukmacherów, na wszystkich 39 ligach, bez ceny
otwarcia w ogóle. Tutaj bazą jest konkretna cena Pinnacle, dopasowanie jest
logistyczne (nie liniowe), a pytanie ma trzy warianty, z których dwa nigdy
nie były zadane.

TRZY POROWNANIA ZAGNIEŻDŻONE, wszystkie na tych samych meczach:
  A. baza = OTWARCIE            kontra  otwarcie + model
  B. baza = ZAMKNIĘCIE          kontra  zamknięcie + model
  C. baza = ZAMKNIĘCIE          kontra  zamknięcie + model + otwarcie

A odpowiada: czy dałoby się poprawić cenę, po której realnie można postawić
wcześniej niż rynek się dowie. B: czy model wnosi cokolwiek do najostrzejszej
ceny, jaka istnieje. C jest testem OSTRYM na to samo, co dało dodatni wynik
w teście ruchu linii: jeśli nasza NIEZGODA Z OTWARCIEM niesie coś ponad
zamknięcie, to fit dostaje oba składniki osobno i może zbudować z nich
różnicę. Jeśli C nie bije B, to znaczy, że zamknięcie już całą tę informację
zawiera — czyli wyprzedzamy rynek tylko do momentu, w którym on nas dogania.

METODA — ta sama, co w `cechy_darmowe.py`, żeby wyniki były porównywalne:
wielomianowa regresja logistyczna (bazowe wyjście = remis), własny softmax
na scipy, L2 = 1e-6, współczynniki dopasowane WYŁĄCZNIE na treningu.
Każda cena wchodzi jako para log-ilorazów log(pH/pD), log(pA/pD).

PODZIAŁ USTALONY Z GÓRY: trening < 2023-01-01, holdout >= 2023-01-01.

MIARA ROZSTRZYGAJĄCA: sparowana różnica log-loss na holdoucie (baza −
rozszerzona; dodatnie = model pomaga), SE ze sparowanych różnic. Brier obok,
jako kontrola spójności kierunku.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * A dodatnie przy z >= 2 → model poprawia cenę otwarcia. To NIE jest jeszcze
    zarobek: trzeba by móc postawić po otwarciu i pobić marżę, a ROI po
    najlepszej cenie przedmeczowej wynosi −15.99% po podatku. Ale byłby to
    pierwszy przypadek, w którym model coś DODAJE do ceny, a nie z nią przegrywa.
  * B dodatnie przy z >= 2 → model wnosi coś do zamknięcia Pinnacle. Byłoby
    to sprzeczne z `w* = 1.0` i wymagałoby wyjaśnienia, zanim cokolwiek dalej.
  * C dodatnie przy z >= 2, przy B nieistotnym → informacja siedzi w RÓŻNICY
    między modelem a otwarciem, nie w samym modelu. Wynik najciekawszy z trzech.
  * wszystkie |z| < 2 → cena jest kompletna względem tego, co mamy. Kierunek
    „poprawiać cenę" zamknięty tak samo jak „bić cenę".

CZEGO TO NIE ZMIENIA: model sam w sobie dalej jest gorszy od ceny w każdej
lidze. Poprawka do ceny i konkurent ceny to dwie różne rzeczy.
=============================================================================

    python scripts/cena_plus_korekta.py --zrzut z/*.parquet --otwarcia otw.parquet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from cechy_darmowe import PODZIAL, brier, dopasuj, log_loss, przewiduj  # noqa: E402
from przewaga_nad_rynkiem import p_jednostronne, sparowana_roznica  # noqa: E402
from ruch_linii import OTW, ZAM, devig, wczytaj  # noqa: E402

WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}


def log_ilorazy(p: np.ndarray) -> np.ndarray:
    """Para log(pH/pD), log(pA/pD) — kanoniczna postać prognozy dla softmaxu."""
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.column_stack([np.log(p[:, 0] / p[:, 1]), np.log(p[:, 2] / p[:, 1])])


def porownaj(nazwa: str, baza: np.ndarray, dodatek: np.ndarray,
             y: np.ndarray, tren: np.ndarray) -> dict:
    """Zagnieżdżone porównanie: baza kontra baza+dodatek, oceniane na holdoucie."""
    hold = ~tren
    X0 = np.column_stack([np.ones(len(y)), baza])
    X1 = np.column_stack([X0, dodatek])

    W0 = dopasuj(X0[tren], y[tren])
    W1 = dopasuj(X1[tren], y[tren])
    p0, p1 = przewiduj(W0, X0[hold]), przewiduj(W1, X1[hold])
    yh = y[hold]
    return {
        "nazwa": nazwa, "n": int(hold.sum()),
        "logloss": sparowana_roznica(log_loss(p0, yh), log_loss(p1, yh)),
        "brier": sparowana_roznica(brier(p0, yh), brier(p1, yh)),
        "b0": float(log_loss(p0, yh).mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zrzut", nargs="+", required=True)
    ap.add_argument("--otwarcia", required=True)
    args = ap.parse_args()

    d = wczytaj(args.zrzut, args.otwarcia)
    p_otw = devig(d[list(OTW)].to_numpy(dtype=float))
    p_zam = devig(d[list(ZAM)].to_numpy(dtype=float))
    p_mod = d[["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0
    ok = np.isfinite(p_otw).all(axis=1) & np.isfinite(p_zam).all(axis=1)
    d, p_otw, p_zam, p_mod = d[ok], p_otw[ok], p_zam[ok], p_mod[ok]

    y = d["actual_res"].map(WYNIK_NA_INDEKS).to_numpy(dtype=int)
    tren = (d["match_date"] < PODZIAL).to_numpy()
    print(f"n={len(y)}  trening {int(tren.sum())}  holdout {int((~tren).sum())}"
          f"  {d['league'].nunique()} lig")
    if tren.sum() < 2000 or (~tren).sum() < 2000:
        raise SystemExit("Za malo danych po podziale.")

    L_otw, L_zam, L_mod = (log_ilorazy(p_otw), log_ilorazy(p_zam),
                           log_ilorazy(p_mod))

    wyniki = [
        porownaj("A  otwarcie  ->  otwarcie + model", L_otw, L_mod, y, tren),
        porownaj("B  zamkniecie -> zamkniecie + model", L_zam, L_mod, y, tren),
        porownaj("C  zamkniecie -> zamkniecie + model + otwarcie",
                 L_zam, np.column_stack([L_mod, L_otw]), y, tren),
    ]

    print("\n" + "=" * 100)
    print("  CZY MODEL POPRAWIA CENE. Dodatnie = model POMAGA."
          "  Holdout od " + PODZIAL + ".")
    print("=" * 100)
    print(f"  {'porownanie':<46}{'logloss bazy':>14}{'d logloss':>12}"
          f"{'SE':>10}{'z':>8}{'z Brier':>9}")
    print("  " + "-" * 96)
    for w in wyniki:
        ll, br = w["logloss"], w["brier"]
        print(f"  {w['nazwa']:<46}{w['b0']:>14.5f}{ll['roznica']:>+12.5f}"
              f"{ll['se']:>10.5f}{ll['z']:>+8.2f}{br['z']:>+9.2f}")

    a, b, c = (w["logloss"]["z"] or 0.0 for w in wyniki)
    print(f"\n  p jednostronne: A {p_jednostronne(a):.4f}"
          f"   B {p_jednostronne(b):.4f}   C {p_jednostronne(c):.4f}")
    print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
    if max(a, b, c) < 2:
        # Regula byla spisana pod wynik dodatni i milczala, gdy WSZYSTKIE `z`
        # sa ujemne — a to jest osobny stan, nie to samo co "nieistotne".
        print("    Zadne z trzech porownan nie jest dodatnie -> cena jest")
        print("    KOMPLETNA wzgledem tego, co mamy. Kierunek 'poprawiac cene'")
        print("    zamkniety tak samo jak 'bic cene'.")
        if min(a, b, c) <= -2:
            print("    Wiecej: dolozenie modelu do ceny out-of-sample SZKODZI")
            print("    (najmocniej w C). Model wnosi do ceny wlasny blad,")
            print("    a uzyteczna czesc jest od niego o rzad wielkosci mniejsza.")
    else:
        if a >= 2:
            print("    A dodatnie -> model POPRAWIA cene otwarcia. Pierwszy raz,")
            print("    gdy model cos do ceny DODAJE. To nadal nie jest zarobek.")
        if b >= 2:
            print("    B dodatnie -> model wnosi cos do zamkniecia Pinnacle.")
            print("    Sprzeczne z w*=1.0 — wymaga wyjasnienia przed czymkolwiek.")
        if c >= 2 and b < 2:
            print("    C dodatnie przy B nieistotnym -> informacja siedzi")
            print("    w ROZNICY model-otwarcie, nie w samym modelu.")
    print("\n  Model SAM dalej jest gorszy od ceny w kazdej lidze. Poprawka")
    print("  do ceny i konkurent ceny to dwie rozne rzeczy.")


if __name__ == "__main__":
    main()
