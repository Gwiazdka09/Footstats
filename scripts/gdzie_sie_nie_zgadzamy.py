#!/usr/bin/env python
"""gdzie_sie_nie_zgadzamy.py — 18% meczów, w których model odchodzi od rynku.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED policzeniem czegokolwiek z podziału na zgodę i niezgodę.

DLACZEGO. Typ modelu zgadza się z faworytem rynku w 82.1% meczów. Wszystko,
co model wnosi ponad cenę — dobrego albo złego — siedzi więc w pozostałych
18%. Dotąd mierzyliśmy model na całej próbie, gdzie te 18% jest rozcieńczone
czterokrotnie przez mecze, w których i tak mówimy to samo co cena.

To jest najtańsze możliwe pytanie diagnostyczne: nie „czy model jest gorszy"
(wiemy, że tak), tylko „GDZIE dokładnie się myli".

PODZIAŁ, USTALONY Z GÓRY. `zgodne` = argmax modelu równy argmaksowi
zdewigowanego zamknięcia Pinnacle. `niezgodne` = reszta. Zamknięcie Pinnacle,
nie średnia — to najostrzejsza cena i to wobec niej mierzy się reszta projektu.

MIARY:
  1. Trafność modelu i trafność rynku, osobno w obu podzbiorach.
  2. W podzbiorze NIEZGODY oba typy wskazują różne wyniki, więc co najwyżej
     jeden może trafić. Test McNemara na parze (model trafił / rynek trafił):
     z = (a − b) / sqrt(a + b). To jest test rozstrzygający.
  3. Sparowany Brier model kontra cena, osobno w obu podzbiorach — mówi, czy
     nasza strata bierze się z niezgody, czy jest rozłożona równo.
  4. CHARAKTERYSTYKA niezgody, opisowo i bez testów: jak często odchodzimy
     w stronę gospodarza / remisu / gościa, przy jakim poziomie ceny, i jak
     duża jest nasza przewaga nad ceną na spornym wyniku.
  5. Trafność w decylach „siły niezgody" (p_model − p_cena na wyniku, który
     wybraliśmy). ŻADEN PRÓG NIE ZOSTANIE Z TEGO WYBRANY — decyle są po to,
     żeby zobaczyć kształt, a nie żeby znaleźć miejsce, w którym wychodzi.
     Wybranie progu po zobaczeniu tabeli to dokładnie 52 podzbiory z 14.08.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * w niezgodzie rynek trafia częściej niż model przy z >= 2
        → nasze odejścia od ceny są systematycznie błędne. Wniosek praktyczny
          jest wtedy twardy: samodzielny wkład modelu jest UJEMNY, a nie zerowy.
  * |z| < 2 → odejścia są rzutem monetą; model ani nie dodaje, ani nie odejmuje,
        kiedy odchodzi od ceny.
  * model trafia częściej przy z >= 2 → wartość modelu siedzi właśnie tam,
        co byłoby sprzeczne z całą resztą pomiarów i wymagałoby wyjaśnienia
        przed jakimkolwiek wnioskiem.

CZEGO TO NIE ROZSTRZYGA: dlaczego się mylimy. To pomiar lokalizujący, nie
wyjaśniający.
=============================================================================

    python scripts/gdzie_sie_nie_zgadzamy.py --zrzut sciezka/zrzut*.parquet
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

from przewaga_nad_rynkiem import brier_wieloklasowy, sparowana_roznica  # noqa: E402

WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}
NAZWY = ("gospodarz", "remis", "gosc")
KOL_PINN = ("odds_h_pinn", "odds_d_pinn", "odds_a_pinn")


def wczytaj(wzorce: list[str]) -> pd.DataFrame:
    pliki: list[str] = []
    for w in wzorce:
        pliki += sorted(glob.glob(w))
    if not pliki:
        raise SystemExit(f"Zero plikow dla {wzorce}")
    df = pd.concat([pd.read_parquet(p) for p in pliki], ignore_index=True)
    df = df[df["actual_res"].isin(WYNIK_NA_INDEKS)]
    k = df[list(KOL_PINN)].to_numpy(dtype=float)
    return df[np.isfinite(k).all(axis=1) & (k > 1.0).all(axis=1)].reset_index(drop=True)


def mcnemar(model_ok: np.ndarray, rynek_ok: np.ndarray) -> dict:
    """Test na parze: ile razy trafil model, a ile rynek, na tych samych meczach."""
    a, b = int(model_ok.sum()), int(rynek_ok.sum())
    if a + b == 0:
        return {"a": a, "b": b, "z": None}
    return {"a": a, "b": b, "z": (a - b) / np.sqrt(a + b)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zrzut", nargs="+", required=True)
    args = ap.parse_args()

    d = wczytaj(args.zrzut)
    inv = 1.0 / d[list(KOL_PINN)].to_numpy(dtype=float)
    p_ryn = inv / inv.sum(axis=1, keepdims=True)
    p_mod = d[["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0
    y = d["actual_res"].map(WYNIK_NA_INDEKS).to_numpy(dtype=int)

    typ_mod, typ_ryn = p_mod.argmax(axis=1), p_ryn.argmax(axis=1)
    zgoda = typ_mod == typ_ryn
    print(f"n={len(y)}  {d['league'].nunique()} lig"
          f"  |  zgoda {100 * zgoda.mean():.1f}%  niezgoda {100 * (~zgoda).mean():.1f}%")

    b_mod = brier_wieloklasowy(p_mod, y)
    b_ryn = brier_wieloklasowy(p_ryn, y)

    print("\n" + "=" * 96)
    print("  ZGODA I NIEZGODA Z FAWORYTEM RYNKU (zamkniecie Pinnacle)")
    print("=" * 96)
    print(f"  {'podzbior':<14}{'n':>8}{'traf. model':>13}{'traf. rynek':>13}"
          f"{'Brier model':>13}{'Brier cena':>12}{'d Brier':>10}{'z':>8}")
    print("  " + "-" * 92)
    for nazwa, m in (("zgoda", zgoda), ("niezgoda", ~zgoda)):
        dm = sparowana_roznica(b_ryn[m], b_mod[m])
        print(f"  {nazwa:<14}{int(m.sum()):>8}"
              f"{100 * (typ_mod[m] == y[m]).mean():>12.2f}%"
              f"{100 * (typ_ryn[m] == y[m]).mean():>12.2f}%"
              f"{float(b_mod[m].mean()):>13.4f}{float(b_ryn[m].mean()):>12.4f}"
              f"{dm['roznica']:>+10.5f}{dm['z']:>+8.2f}")

    nz = ~zgoda
    mn = mcnemar(typ_mod[nz] == y[nz], typ_ryn[nz] == y[nz])
    print("\n  TEST ROZSTRZYGAJACY — McNemar w podzbiorze NIEZGODY")
    print(f"    model trafil {mn['a']}   rynek trafil {mn['b']}"
          f"   ani jeden {int(nz.sum()) - mn['a'] - mn['b']}"
          f"   z={mn['z']:+.2f}")
    print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
    if mn["z"] is not None and mn["z"] <= -2:
        print("    Rynek trafia CZESCIEJ przy z <= -2 -> nasze odejscia od ceny sa")
        print("    systematycznie bledne. Samodzielny wklad modelu jest UJEMNY,")
        print("    a nie zerowy.")
    elif mn["z"] is not None and mn["z"] >= 2:
        print("    Model trafia czesciej -> wartosc modelu siedzi wlasnie tam.")
        print("    Sprzeczne z reszta pomiarow, wymaga wyjasnienia.")
    else:
        print("    |z| < 2 -> odejscia od ceny sa rzutem moneta. Model ani nie")
        print("    dodaje, ani nie odejmuje, kiedy odchodzi od ceny.")

    print("\n" + "=" * 96)
    print("  CHARAKTERYSTYKA NIEZGODY (opisowo, bez testow)")
    print("=" * 96)
    print(f"  {'model wybral':<14}{'n':>8}{'udzial':>9}{'traf. model':>13}"
          f"{'traf. rynek':>13}{'sr. p_cena':>12}")
    print("  " + "-" * 70)
    for k, nazwa in enumerate(NAZWY):
        m = nz & (typ_mod == k)
        if m.sum() < 50:
            continue
        print(f"  {nazwa:<14}{int(m.sum()):>8}{100 * m.sum() / nz.sum():>8.1f}%"
              f"{100 * (typ_mod[m] == y[m]).mean():>12.2f}%"
              f"{100 * (typ_ryn[m] == y[m]).mean():>12.2f}%"
              f"{100 * p_ryn[m, k].mean():>11.1f}%")

    print(f"\n  {'sila niezgody (decyl)':<24}{'n':>8}{'p_mod-p_cena':>14}"
          f"{'traf. model':>13}{'traf. rynek':>13}")
    print("  " + "-" * 72)
    sila = p_mod[np.arange(len(y)), typ_mod] - p_ryn[np.arange(len(y)), typ_mod]
    s_nz = sila[nz]
    progi = np.quantile(s_nz, np.linspace(0, 1, 11))
    for i in range(10):
        lo, hi = progi[i], progi[i + 1]
        m = (s_nz >= lo) & (s_nz <= hi if i == 9 else s_nz < hi)
        if m.sum() < 100:
            continue
        print(f"  {f'{i + 1}. {lo:+.3f}..{hi:+.3f}':<24}{int(m.sum()):>8}"
              f"{s_nz[m].mean():>+14.3f}"
              f"{100 * (typ_mod[nz][m] == y[nz][m]).mean():>12.2f}%"
              f"{100 * (typ_ryn[nz][m] == y[nz][m]).mean():>12.2f}%")
    print("\n  Decyle sa po to, zeby zobaczyc KSZTALT. Zaden prog nie zostanie")
    print("  z tej tabeli wybrany — to bylby dokladnie mechanizm 52 podzbiorow.")


if __name__ == "__main__":
    main()
