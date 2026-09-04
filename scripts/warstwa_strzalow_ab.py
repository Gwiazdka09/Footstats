#!/usr/bin/env python
"""warstwa_strzalow_ab.py — czy efekt strzałów celnych powtarza się na nowych ligach.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED zakończeniem backfillu sześciu nowych lig i PRZED
policzeniem czegokolwiek z nich.

CO JUŻ WIEMY. 03.09, na ośmiu ligach z backfillem API-Football (AUT, DNK, IRL,
MEX, NOR, POL, SWZ, USA), domieszanie strzałów celnych do sił ligowych
poprawiło Brier o +0.00430 przy SE 0.00147, czyli z=2.93, n=3568. Wynik był
raportowany jako pozytywny — ale nigdy nie był REPLIKOWANY. Trzy z ośmiu lig
miały z>2, dwie wyszły ujemnie.

CO SIĘ ZMIENIŁO. 04.09 backfill objął sześć kolejnych lig: ARG-Liga Profesional,
BRA-Serie A, RUS-Premier League, ROU-Superliga, JPN-J1 League, SWE-Allsvenskan.
To są dane, których pierwszy pomiar nie widział — a więc PRAWDZIWA próba
niezależna, rzecz, której temu projektowi brakowało najczęściej.

DLATEGO GRUPY SĄ ROZDZIELONE I NIE WOLNO ICH ZLAĆ:
  GRUPA A (8 lig, 03.09)  — odniesienie. NIE jest tu ponownie testowana;
                            wynik +0.00430 (z=2.93) jest znany i cytowany.
  GRUPA B (6 lig, 04.09)  — REPLIKACJA. To ona rozstrzyga.
Zlanie obu w jedną liczbę ukryłoby nieudaną replikację pod istniejącym efektem,
i to jest dokładnie ten sposób, w jaki wynik przeżywa dłużej, niż zasługuje.
Zbiorcza liczba po 14 ligach jest raportowana OSOBNO i wyłącznie poglądowo.

RAMIONA, identyczne z pomiarem z 03.09, żeby porównanie miało sens:
  bez:  `load_cached(z_af=False)` — dataset bez statystyk z API-Football
  ze:   `load_cached(z_af=True)`  — z nimi, `WAGA_STRZALOW` domieszana w `form`
Flagi replayu: bayesian OFF, ensemble ON, kalibracja OFF (jak 03.09).

OKNO: od 2025-01-01, jak w pomiarze strzałów i xG. Backfill sięga 2024-07,
więc wcześniej żadna drużyna nie ma historii strzałów.

MIARA: Brier wieloklasowy, sparowany po meczach, SE ze sparowanych różnic.
Dodatnie = strzały pomagają. Trafność drugorzędna — zależy tylko od argmaksu.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * GRUPA B zbiorczo z >= 2  → efekt strzałów REPLIKUJE SIĘ poza próbą,
    na której powstał. To najmocniejszy wynik, jaki ten pomiar może dać,
    i dopiero on czyni z niego ustalenie, a nie hipotezę.
  * GRUPA B |z| < 2  → NIE replikuje. Pierwotne z=2.93 zostaje wynikiem
    JEDNEJ próby i tak ma być cytowane. Nie szukamy podzbiorów grupy B ani
    innych okien; nie zlewamy grup, żeby „wyszło".
  * GRUPA B z <= -2  → efekt zaprzeczony. Strzały wyłączyć z rozważań.

CZEGO TEN POMIAR NIE ZMIENIA. Werdyktu „model nie bije rynku". Efekt rzędu
+0.004 Briera zamyka kilkanaście procent luki −0.018..−0.052, jaką model ma
do zdewigowanej ceny w każdej z 39 lig.
=============================================================================

    python scripts/warstwa_strzalow_ab.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from przewaga_nad_rynkiem import (  # noqa: E402
    brier_wieloklasowy, p_jednostronne, sparowana_roznica,
)

OKNO_OD = "2025-01-01"
MIN_MECZOW = 100
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}

GRUPA_A = ("AUT-Bundesliga", "DNK-Superliga", "IRL-Premier Division",
           "MEX-Liga MX", "NOR-Eliteserien", "POL-Ekstraklasa",
           "SWZ-Super League", "USA-MLS")
GRUPA_B = ("ARG-Liga Profesional", "BRA-Serie A", "RUS-Premier League",
           "ROU-Superliga", "JPN-J1 League", "SWE-Allsvenskan")
ODNIESIENIE_A = "+0.00430 (SE 0.00147, z=2.93, n=3568) — pomiar z 2026-09-03"


def _przebieg(df: pd.DataFrame, liga: str, od: str) -> pd.DataFrame:
    from footstats.core.wf_harness import ModelFlags, run_walkforward
    return run_walkforward(
        df, league=liga, run_tag="strzaly", min_date=od, verbose=False,
        flags=ModelFlags(use_bayesian=False, use_ensemble=True,
                         use_calibration=False))


def zmierz_lige(bez_df, ze_df, liga: str, od: str) -> dict | None:
    a = _przebieg(bez_df, liga, od)
    b = _przebieg(ze_df, liga, od)
    if len(a) < MIN_MECZOW or len(a) != len(b):
        return None

    maska = a["actual_res"].isin(WYNIK_NA_INDEKS).to_numpy()
    y = a.loc[maska, "actual_res"].map(WYNIK_NA_INDEKS).to_numpy(dtype=int)
    pa = a.loc[maska, ["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0
    pb = b.loc[maska, ["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0

    br_a, br_b = brier_wieloklasowy(pa, y), brier_wieloklasowy(pb, y)
    d = br_a - br_b
    # Zero ruszonych predykcji znaczyloby, ze mierzymy dwa identyczne ramiona
    # i dostajemy z=0 z powodu niemajacego nic wspolnego ze strzalami.
    ruszone = int((np.abs(pa - pb).max(axis=1) > 1e-9).sum())
    return {
        "liga": liga, "n": len(y), "ruszone": ruszone,
        "brier_bez": float(br_a.mean()), "brier_ze": float(br_b.mean()),
        "roznica": sparowana_roznica(br_a, br_b),
        "d_n": int(len(d)), "d_sum": float(d.sum()),
        "d_sumsq": float((d ** 2).sum()),
        "_traf": float(((pb.argmax(axis=1) == y).astype(float)
                        - (pa.argmax(axis=1) == y).astype(float)).sum()),
    }


def polacz(czesci: list[dict]) -> tuple[int, float, float] | None:
    n = sum(c["d_n"] for c in czesci)
    if n < 2:
        return None
    s = sum(c["d_sum"] for c in czesci)
    sq = sum(c["d_sumsq"] for c in czesci)
    war = (sq - s * s / n) / (n - 1)
    return n, s / n, float(np.sqrt(max(war, 0.0) / n))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--od", default=OKNO_OD)
    ap.add_argument("--wynik", default=None)
    args = ap.parse_args()

    from footstats.data.af_stats import wczytaj_af_stats
    from footstats.data.historical_loader import load_cached

    maja_dane = set(wczytaj_af_stats()["league"].dropna().unique())
    bez_df = load_cached(z_af=False)
    ze_df = load_cached(z_af=True)

    wyniki: dict[str, list[dict]] = {"A": [], "B": []}
    for nazwa, ligi in (("A", GRUPA_A), ("B", GRUPA_B)):
        for liga in ligi:
            if liga not in maja_dane:
                print(f"  [{nazwa}] {liga}: BRAK w af_stats — pomijam", flush=True)
                continue
            t0 = time.time()
            w = zmierz_lige(bez_df, ze_df, liga, args.od)
            if w is None:
                print(f"  [{nazwa}] {liga}: pominieta (za malo meczow)", flush=True)
                continue
            wyniki[nazwa].append(w)
            print(f"  [{nazwa}] {liga}: n={w['n']} ruszone={w['ruszone']}"
                  f"  {w['roznica']['roznica']:+.5f} (z={w['roznica']['z']:.2f})"
                  f"  ({time.time() - t0:.0f}s)", flush=True)

    if args.wynik:
        Path(args.wynik).write_text(
            json.dumps({"od": args.od, "grupy": wyniki}, indent=2, ensure_ascii=False),
            encoding="utf-8")

    raport(wyniki)


def _tabela(czesc: list[dict], korekta_sidaka) -> None:
    print(f"  {'liga':<24}{'n':>7}{'ruszone':>9}{'Brier bez':>11}{'Brier ze':>10}"
          f"{'roznica':>10}{'SE':>9}{'z':>7}{'p_kor':>8}")
    print("  " + "-" * 93)
    for w in sorted(czesc, key=lambda x: -(x["roznica"]["z"] or -99)):
        r = w["roznica"]
        pk = korekta_sidaka(p_jednostronne(r["z"]), len(czesc)) if r["z"] else None
        print(f"  {w['liga']:<24}{w['n']:>7}{w['ruszone']:>9}{w['brier_bez']:>11.4f}"
              f"{w['brier_ze']:>10.4f}{r['roznica']:>+10.5f}{r['se']:>9.5f}"
              f"{r['z']:>+7.2f}{(f'{pk:.4f}' if pk is not None else '-'):>8}")


def raport(wyniki: dict[str, list[dict]]) -> None:
    from footstats.core.testy_przewagi import korekta_sidaka

    print("\n" + "=" * 97)
    print("  WARSTWA STRZALOW CELNYCH. Dodatnie = strzaly POMAGAJA.")
    print("  Grupa B to REPLIKACJA na ligach, ktorych pierwszy pomiar nie widzial.")
    print("=" * 97)

    for nazwa, opis in (("A", "ODNIESIENIE — 8 lig zmierzonych 03.09"),
                        ("B", "REPLIKACJA — 6 lig dobackfillowanych 04.09")):
        czesc = wyniki.get(nazwa) or []
        if not czesc:
            print(f"\n  GRUPA {nazwa} ({opis}): brak wynikow")
            continue
        print(f"\n  GRUPA {nazwa} — {opis}")
        _tabela(czesc, korekta_sidaka)
        z = polacz(czesc)
        if z:
            n, sr, se = z
            print(f"  ZBIORCZO grupa {nazwa}: n={n}  Brier {sr:+.5f}  SE {se:.5f}"
                  f"  z={(sr / se if se else 0):+.2f}"
                  f"   95%: {sr - 1.96 * se:+.5f} .. {sr + 1.96 * se:+.5f}")

    print(f"\n  Pierwotny wynik grupy A (cytowany, nie przeliczany): {ODNIESIENIE_A}")

    b = polacz(wyniki.get("B") or [])
    print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
    if not b:
        print("    Grupa B pusta — replikacja NIE ZOSTALA wykonana.")
        return
    _nb, sb, seb = b
    zb = sb / seb if seb else 0.0
    if zb >= 2:
        print(f"    z={zb:+.2f} >= 2 -> efekt strzalow REPLIKUJE SIE poza probą,")
        print("    na ktorej powstal. To czyni z niego ustalenie, nie hipoteze.")
    elif zb <= -2:
        print(f"    z={zb:+.2f} <= -2 -> efekt ZAPRZECZONY na nowych ligach.")
    else:
        print(f"    |z|={abs(zb):.2f} < 2 -> NIE replikuje. Pierwotne z=2.93")
        print("    zostaje wynikiem JEDNEJ proby i tak ma byc cytowane.")
        print("    Bez zlewania grup i bez szukania podzbiorow grupy B.")

    laczne = polacz((wyniki.get("A") or []) + (wyniki.get("B") or []))
    if laczne:
        n, sr, se = laczne
        print(f"\n  POGLADOWO, 14 lig razem: n={n}  Brier {sr:+.5f}"
              f"  z={(sr / se if se else 0):+.2f}")
        print("  Ta liczba NIE rozstrzyga niczego — zawiera probe, na ktorej")
        print("  efekt zostal znaleziony.")


if __name__ == "__main__":
    main()
