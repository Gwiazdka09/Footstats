#!/usr/bin/env python
"""warstwa_xg_ab.py — czy xG dokłada cokolwiek ponad strzały celne.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED pierwszym przebiegiem.

PYTANIE. Poprzedni pomiar (03.09, n=3568) pokazał, że strzały celne poprawiają
model: Brier +0.0043, z=2.93. Strzał celny to zgrubna miara jakości sytuacji.
xG mierzy TO SAMO ZJAWISKO lepiej — waży każdą sytuację prawdopodobieństwem
gola. Jeśli lepsza miara tego samego nie dokłada nic, to jest mocna przesłanka,
że wąskim gardłem nie jest jakość proxy, tylko sufit rozdzielczości modelu.
To jest test falsyfikujący tezę o suficie, nie próba ulepszenia modelu.

CZEGO TEN POMIAR NIE ROZSTRZYGNIE — I TO TRZEBA WIEDZIEĆ Z GÓRY. Pomiar
przewagi nad rynkiem (04.09, n=120 351) pokazał, że model sam jest gorszy od
zdewigowanej ceny w KAŻDEJ z 39 lig, o −0.018 do −0.052 Briera. Poprawa rzędu
tej ze strzałów (+0.0043) zamyka kilkanaście procent tej luki. Nawet dodatni
wynik NIE oznacza więc, że model zaczyna bić rynek, i nie wolno go tak
raportować.

RAMIONA. Dokładnie dwa, obie wagi ustalone z góry:
  A: WAGA_XG = 0.0  — dzisiejsza produkcja (gole ⊕ strzały przy 0.7)
  B: WAGA_XG = 0.7  — xG domieszane PO strzałach

Skąd 0.7, skoro to wolny parametr: to ta sama waga, jakiej projekt używa dla
strzałów (`WAGA_STRZALOW`). Wybór a priori znaczy „ufamy xG tak samo, jak
istniejącej warstwie proxy". Nie testujemy siatki wag — jedna wartość, ustalona
przed patrzeniem. Dobranie wagi z tych danych byłoby dopasowaniem i wymagałoby
własnego holdoutu.

xG PO strzałach, nie zamiast: pytanie brzmi „czy lepsza miara dokłada coś PONAD
gorszą". Podmiana odpowiadałaby na inne pytanie i mieszała dwie zmiany naraz.

LIGI. Dokładnie te 8, które mają backfill z API-Football — AUT, DNK, IRL, MEX,
NOR, POL, SWZ, USA. Lista wynika z tego, gdzie w ogóle są dane, a nie z tego,
gdzie wynik wygląda lepiej. Pokrycie xG jest nierówne (USA 99.7%, NOR 93%,
DNK 85%, SWZ 81%, POL 79%, AUT 40%, MEX 36%, IRL 27%) i raportujemy je obok
wyniku, bo liga z 27% pokrycia dostaje słabsze ramię B niż liga ze 100%.

OKNO. Od 2025-01-01. xG w `af_stats.parquet` zaczyna się 2024-07, więc wcześniej
żadna drużyna nie ma historii xG. Ta data daje ~3639 meczów, czyli tyle samo co
pomiar strzałów (n=3568, z=2.93) — moc jest porównywalna i znana z góry. Jedno
okno, ustalone przed patrzeniem; nie liczymy kilku i nie wybieramy.

MIARA. Brier wieloklasowy, sparowany po meczach. SE ze sparowanych różnic.
Dodatnie = ramię B lepsze. Trafność raportowana jako drugorzędna, bo zależy
tylko od argmax i ignoruje resztę rozkładu.

Ensemble OFF w obu ramionach: mierzymy warstwę modelu, a domieszka ceny
zalałaby efekt, którego szukamy (rynek jest o rząd wielkości silniejszy).
Kalibracja OFF: `model_calibration.json` jest dopasowany na danych pokrywających
okno replay → lookahead.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * zbiorcze z < 2 → xG nie dokłada nic ponad strzały. Teza o suficie
    rozdzielczości zostaje wzmocniona, `WAGA_XG` zostaje 0, kolumny zostają
    (są tanie i już opłacone). Nie szukamy podzbiorów ani innych wag.
  * zbiorcze z >= 2 → to jest HIPOTEZA, nie wdrożenie. Warunkiem flipa jest
    osobny holdout po dacie, pre-rejestrowany, plus sprawdzenie, czy efekt nie
    pochodzi z jednej ligi.
=============================================================================

    python scripts/warstwa_xg_ab.py
    python scripts/warstwa_xg_ab.py --ligi "POL-Ekstraklasa" --od 2025-01-01
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from przewaga_nad_rynkiem import (  # noqa: E402
    _polacz, brier_wieloklasowy, p_jednostronne, sparowana_roznica,
)

OKNO_OD = "2025-01-01"
WAGA_XG_B = 0.7
MIN_MECZOW = 100
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}


def _wektory(rekordy: pd.DataFrame) -> tuple[np.ndarray, np.ndarray] | None:
    """(rozkłady 0..1, indeks wyniku) z rekordów walk-forward."""
    df = rekordy[rekordy["actual_res"].isin(WYNIK_NA_INDEKS)]
    if df.empty:
        return None
    p = df[["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0
    y = df["actual_res"].map(WYNIK_NA_INDEKS).to_numpy(dtype=int)
    return p, y


def _przebieg(df, liga: str, od: str, waga_xg: float) -> pd.DataFrame:
    """Walk-forward jednego ramienia. `WAGA_XG` wstrzykiwana przez config.

    Podmieniamy atrybut modułu `config`, bo `form.sily_ligowe` czyta go późno
    (`from footstats.config import WAGA_XG` w środku funkcji). Podmiana env po
    starcie procesu nie zadziałałaby — `config` czyta `os.getenv` przy imporcie.
    """
    import footstats.config as config
    from footstats.core.wf_harness import ModelFlags, run_walkforward

    stara = config.WAGA_XG
    config.WAGA_XG = waga_xg
    try:
        return run_walkforward(
            df, league=liga, run_tag=f"xg{waga_xg}", min_date=od, verbose=False,
            flags=ModelFlags(use_bayesian=False, use_ensemble=False,
                             use_calibration=False),
        )
    finally:
        config.WAGA_XG = stara


def zmierz_lige(df, liga: str, od: str) -> dict | None:
    a = _przebieg(df, liga, od, 0.0)
    b = _przebieg(df, liga, od, WAGA_XG_B)
    if len(a) < MIN_MECZOW or len(a) != len(b):
        return None

    wa, wb = _wektory(a), _wektory(b)
    if wa is None or wb is None:
        return None
    (pa, y), (pb, _) = wa, wb

    br_a = brier_wieloklasowy(pa, y)
    br_b = brier_wieloklasowy(pb, y)
    d = br_a - br_b                      # dodatnie = ramie B lepsze

    traf_a = float((pa.argmax(axis=1) == y).mean())
    traf_b = float((pb.argmax(axis=1) == y).mean())
    dt = (pb.argmax(axis=1) == y).astype(float) - (pa.argmax(axis=1) == y).astype(float)

    # Ile wierszy ramiona w ogole roznia sie miedzy soba. Zero znaczy, ze xG
    # nie dotknelo ANI JEDNEJ predykcji — czyli mierzylibysmy dwa identyczne
    # ramiona i dostali z=0 z powodu, ktory nie ma nic wspolnego z xG.
    ruszone = int((np.abs(pa - pb).max(axis=1) > 1e-9).sum())

    return {
        "liga": liga,
        "n": len(y),
        "ruszone": ruszone,
        "brier_bez": float(br_a.mean()),
        "brier_ze": float(br_b.mean()),
        "roznica": sparowana_roznica(br_a, br_b),
        "trafnosc_bez": traf_a,
        "trafnosc_ze": traf_b,
        "trafnosc_roznica": sparowana_roznica(
            (pb.argmax(axis=1) == y).astype(float),
            (pa.argmax(axis=1) == y).astype(float)),
        "d_n": int(len(d)),
        "d_sum": float(d.sum()),
        "d_sumsq": float((d ** 2).sum()),
        "_dt_sum": float(dt.sum()),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--od", default=OKNO_OD)
    p.add_argument("--ligi", default=None)
    p.add_argument("--wynik", default=None)
    args = p.parse_args()

    from footstats.core.testy_przewagi import korekta_sidaka
    from footstats.data.af_stats import wczytaj_af_stats
    from footstats.data.historical_loader import load_cached

    df = load_cached()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if args.ligi:
        ligi = [x.strip() for x in args.ligi.split(",")]
    else:
        af = wczytaj_af_stats()
        ligi = sorted(af["league"].dropna().unique()) if not af.empty else []
    if not ligi:
        raise SystemExit("Brak lig z backfillem AF — nie ma czego mierzyc.")

    # Pokrycie liczone od POCZATKU DANYCH AF, nie od poczatku historii ligi.
    # Liczone po calym datasecie dawaloby dla Ekstraklasy 13% i sugerowalo, ze
    # ramie B prawie nie dziala — a to tylko efekt 12 lat sprzed backfillu.
    poczatek_af = pd.Timestamp("2024-07-01")
    pokrycie = {}
    for liga in ligi:
        okno = df[(df["league"] == liga) & (df["date"] >= poczatek_af)]
        pokrycie[liga] = float(okno["xg_home"].notna().mean()) if len(okno) else 0.0

    wyniki = []
    for i, liga in enumerate(ligi, 1):
        print(f"[{i}/{len(ligi)}] {liga} ...", flush=True)
        w = zmierz_lige(df, liga, args.od)
        if w is None:
            print("    pominieta (za malo meczow albo ramiona sie rozjechaly)", flush=True)
            continue
        w["pokrycie_xg"] = pokrycie.get(liga, 0.0)
        wyniki.append(w)
        print(f"    n={w['n']} ruszone={w['ruszone']}"
              f"  Brier {w['roznica']['roznica']:+.5f} (z={w['roznica']['z']:.2f})",
              flush=True)

    if not wyniki:
        raise SystemExit("Zero lig w wyniku.")
    if args.wynik:
        Path(args.wynik).write_text(
            json.dumps({"od": args.od, "waga_xg": WAGA_XG_B, "ligi": wyniki},
                       indent=2, ensure_ascii=False), encoding="utf-8")

    raport(wyniki, args.od, korekta_sidaka)


def raport(wyniki: list[dict], od: str, korekta_sidaka) -> None:
    ile = len(wyniki)
    print("\n" + "=" * 100)
    print(f"  WARSTWA xG (WAGA_XG={WAGA_XG_B}) kontra sama warstwa strzalow."
          f" Okno od {od}.")
    print("  Dodatnie = xG POMAGA. p po korekcie Sidaka na", ile, "lig.")
    print("=" * 100)
    print(f"{'liga':<26}{'pokr.xG':>9}{'n':>7}{'ruszone':>9}"
          f"{'Brier bez':>11}{'Brier ze':>10}{'roznica':>10}{'SE':>9}{'z':>7}{'p_kor':>8}")
    print("-" * 100)
    for w in sorted(wyniki, key=lambda x: -(x["roznica"]["z"] or -99)):
        r = w["roznica"]
        pk = korekta_sidaka(p_jednostronne(r["z"]), ile) if r["z"] is not None else None
        print(f"{w['liga']:<26}{100*w['pokrycie_xg']:>8.0f}%{w['n']:>7}{w['ruszone']:>9}"
              f"{w['brier_bez']:>11.4f}{w['brier_ze']:>10.4f}{r['roznica']:>+10.5f}"
              f"{r['se']:>9.5f}{r['z']:>7.2f}"
              f"{(f'{pk:.4f}' if pk is not None else '-'):>8}")
    print("-" * 100)

    zbior = _polacz(wyniki)
    if zbior:
        n, sr, se = zbior
        z = sr / se if se else 0.0
        lo, hi = sr - 1.96 * se, sr + 1.96 * se
        print(f"\n  ZBIORCZO n={n}  Brier {sr:+.5f}  SE={se:.5f}  z={z:+.2f}")
        print(f"           95%: {lo:+.5f} .. {hi:+.5f}")
        print(f"  ruszonych predykcji: {sum(w['ruszone'] for w in wyniki)} z {n}")
        traf = sum(w["_dt_sum"] for w in wyniki) / n
        print(f"  trafnosc (drugorzedna): {100*traf:+.2f}pp")
        print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
        if z < 2:
            print("    z < 2 -> xG NIE doklada nic ponad strzaly. Teza o suficie")
            print("    rozdzielczosci wzmocniona. WAGA_XG zostaje 0, bez podzbiorow.")
        else:
            print("    z >= 2 -> HIPOTEZA, nie wdrozenie. Flip wymaga osobnego,")
            print("    pre-rejestrowanego holdoutu po dacie i sprawdzenia, czy efekt")
            print("    nie pochodzi z jednej ligi.")
        print("\n  I tak nie znaczy to, ze model zaczyna bic rynek: luka do")
        print("  zdewigowanej ceny to -0.018 .. -0.052 Briera w kazdej z 39 lig.")


if __name__ == "__main__":
    main()
