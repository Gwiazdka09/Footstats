#!/usr/bin/env python
"""przewaga_nad_rynkiem.py — czy model niesie informację, której nie ma w cenie.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED pierwszym przebiegiem. Powód: 14.08.2026 przetestowano
52 podzbiory na n=15 460 i ZERO przeżyło holdout. Tamto badanie szukało
podzbioru po tym, jak zobaczyło wyniki — czyli mierzyło własną swobodę wyboru,
nie model. Tu kolejność jest odwrotna: pytania, miary i reguła decyzyjna są
zamrożone poniżej i commitowane przed uruchomieniem.

CO SIĘ ZMIENIŁO I DLACZEGO W OGÓLE PYTAMY PONOWNIE
--------------------------------------------------
Werdykt „model nie bije rynku" zapadł na próbie, w której kurs w ogóle
istniał — a to było 63% datasetu i NIE losowe 63%. 22 ligi `fdco_season`
(Anglia, Niemcy, Hiszpania, Włochy, Francja, Holandia, Belgia, Portugalia,
Turcja, Grecja, Szkocja) miały kursy w ~100% meczów. 16 lig `fdco_new`
(Polska, Brazylia, MLS, Argentyna, Meksyk, Japonia, Chiny, Skandynawia,
Rumunia, Rosja) miało ~7%, bo parser brał kolumnę kursów po ISTNIENIU, nie po
POKRYCIU (naprawione 2026-09-03, `historical_loader._wpisz_kursy`). Pytanie
„czy model bije rynek" zostało więc zadane wyłącznie tam, gdzie rynek wycenia
najostrzej, i nigdy tam, gdzie jest najbardziej prawdopodobne, że jest leniwy.

TRZY WEKTORY NA TYM SAMYM MECZU
-------------------------------
* `model` — pw/pr/pp z ramienia BEZ ensembla, BEZ Dixona-Colesa, BEZ kalibracji
  (kalibracja OFF, bo `model_calibration.json` jest dopasowany na danych
  pokrywających okno replay → lookahead).
* `rynek` — `wf_harness.devig_1x2` na kursie, KTÓREGO UŻYŁ `predict_one` na tym
  wierszu (kolumny `odds_h/d/a` w rekordzie; join po nazwach odpada, bo gubi
  wiersze nielosowo).
* `mix`   — `ensemble.ensemble_probs(model, rynek, liga)`, czyli DOKŁADNIE waga
  produkcyjna. Zero wolnych parametrów — nie dobieramy wagi pod wynik.

MIARA
-----
Brier wieloklasowy: suma po trzech wyjściach (p_i - y_i)^2, y one-hot z wyniku.
Skala 0..2, mniej = lepiej. Wybrany zamiast trafności, bo trafność zależy tylko
od argmax i ignoruje całą resztę rozkładu — a pytanie dotyczy informacji, nie
liczby trafionych typów.

DWA TESTY, OBA SPAROWANE PO MECZACH
-----------------------------------
  T1: Brier(rynek) - Brier(model)  > 0  → model sam jest ostrzejszy niż cena
  T2: Brier(rynek) - Brier(mix)    > 0  → model dokłada COKOLWIEK ponad cenę

T2 jest właściwym pytaniem o edge informacyjny. Model może być indywidualnie
gorszy od rynku i wciąż nieść informację ortogonalną — wtedy T1 wychodzi ujemne,
a T2 dodatnie. Odwrotnie się nie da.

Błąd standardowy liczony ZE SPAROWANYCH RÓŻNIC (odch.std. różnic / sqrt(n)), nie
z dwóch niezależnych prób — te same mecze, więc różnice są skorelowane i
niesparowane SE zawyżałoby niepewność. Patrz `feedback_kubelki_bez_se`: dwa
fałszywe wnioski jednego dnia wzięły się z tabel bez błędu standardowego.

JEDNA HIPOTEZA GŁÓWNA — JEDNO PORÓWNANIE, NIE 40
------------------------------------------------
  H: średnie T2 w grupie `fdco_new` (16 lig nigdy niemierzonych) jest WYŻSZE
     niż w grupie `fdco_season` (22 ligi, gdzie werdykt już zapadł).

Ligi raportujemy pojedynczo dla czytelności, ale każde p pojedynczej ligi jest
korygowane Šidákiem na liczbę lig w wyniku (`testy_przewagi.korekta_sidaka`) —
bez tego „najlepsza z 40" jest zwykłym efektem szukania.

CZEGO NIE ROBIMY (to jest część rejestracji, nie komentarz)
-----------------------------------------------------------
* zero podzbiorów: żadnych progów pewności, pasm kursów, faworyt/underdog,
  filtrów na ligę po zobaczeniu wyniku;
* zero strojenia wagi ensembla;
* zero raportowania ROI/EV — do tego trzeba reguły selekcji, a każda reguła to
  kolejny stopień swobody. ROI wchodzi dopiero, gdy T2 przejdzie.

REGUŁA DECYZYJNA, ZAMROŻONA
---------------------------
* T2 nie przechodzi nigdzie po korekcie  → pytanie o edge ZAMKNIĘTE. Nie
  wchodzimy w podzbiory, nie szukamy „gdzie jednak działa". Idziemy do punktów
  2-3 (rozszczepione kluby, martwe ścieżki).
* T2 przechodzi w którejś lidze → to jest HIPOTEZA, nie wynik. Wtedy i tylko
  wtedy: holdout po dacie (trening do 2023-12-31, walidacja 2024-01-01+),
  pre-rejestrowany osobno, zanim zobaczymy jego wynik.

Okno oceny: 2016-08-01+. `fdco_season` zaczyna się w 2016, `fdco_new` w 2012 —
bez wspólnego okna porównanie GRUP mieszałoby efekt ligi z efektem epoki.
Historia do liczenia λ zostaje PEŁNA (run_walkforward filtruje tylko mecze
oceniane, nie bazę historyczną) — obcięcie historii byłoby stratą bez powodu.
=============================================================================

    python scripts/przewaga_nad_rynkiem.py --od 2016-08-01
    python scripts/przewaga_nad_rynkiem.py --ligi "POL-Ekstraklasa,BRA-Serie A"
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

OKNO_OD = "2016-08-01"
MIN_MECZOW = 100          # liga poniżej tego nie wchodzi do raportu — SE bez sensu
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}


def brier_wieloklasowy(p: np.ndarray, y_idx: np.ndarray) -> np.ndarray:
    """Suma (p_i - y_i)^2 po trzech wyjściach, per mecz. `p` w skali 0..1."""
    y = np.zeros_like(p)
    y[np.arange(len(y_idx)), y_idx] = 1.0
    return ((p - y) ** 2).sum(axis=1)


def sparowana_roznica(a: np.ndarray, b: np.ndarray) -> dict:
    """Średnia z a-b, jej SE ze sparowanych różnic, oraz z.

    SE liczone z odchylenia różnic, bo `a` i `b` to te same mecze. Dwie
    niezależne próby dałyby tu zawyżoną niepewność.
    """
    d = a - b
    n = len(d)
    if n < 2:
        return {"n": n, "roznica": None, "se": None, "z": None}
    se = float(d.std(ddof=1) / np.sqrt(n))
    sr = float(d.mean())
    return {"n": n, "roznica": sr, "se": se, "z": (sr / se if se > 0 else None)}


def p_jednostronne(z: float | None) -> float | None:
    """P(Z >= z) dla rozkładu normalnego — test jednostronny (szukamy przewagi)."""
    if z is None:
        return None
    from math import erfc, sqrt
    return 0.5 * erfc(z / sqrt(2.0))


def wektory_ligi(rekordy: pd.DataFrame, liga: str) -> dict | None:
    """Z rekordów walk-forward robi trzy rozkłady + wynik. None gdy brak danych."""
    from footstats.core.ensemble import ensemble_probs
    from footstats.core.wf_harness import devig_1x2

    df = rekordy[rekordy["actual_res"].isin(WYNIK_NA_INDEKS)].copy()
    if df.empty:
        return None

    model, rynek, mix, wyniki = [], [], [], []
    for _, r in df.iterrows():
        p_rynek = devig_1x2(r["odds_h"], r["odds_d"], r["odds_a"])
        if p_rynek is None:
            # Mecz bez ceny nie da się porównać z ceną. Liczymy je, żeby
            # w raporcie było widać, ile próby odpada i czy to nie jest
            # przypadkiem cała liga.
            continue
        p_model = {"pw": r["pw"], "pr": r["pr"], "pp": r["pp"]}
        p_mix = ensemble_probs(p_model, p_rynek, liga=liga)
        model.append([p_model["pw"], p_model["pr"], p_model["pp"]])
        rynek.append([p_rynek["pw"], p_rynek["pr"], p_rynek["pp"]])
        mix.append([p_mix["pw"], p_mix["pr"], p_mix["pp"]])
        wyniki.append(WYNIK_NA_INDEKS[r["actual_res"]])

    if not wyniki:
        return None
    return {
        "model": np.array(model) / 100.0,
        "rynek": np.array(rynek) / 100.0,
        "mix": np.array(mix) / 100.0,
        "y": np.array(wyniki),
        "bez_ceny": len(df) - len(wyniki),
    }


def zmierz_lige(df, liga: str, od: str) -> dict | None:
    from footstats.core.wf_harness import ModelFlags, run_walkforward

    flagi = ModelFlags(use_bayesian=False, use_ensemble=False, use_calibration=False)
    rek = run_walkforward(df, league=liga, flags=flagi, run_tag="przewaga",
                          min_date=od, verbose=False)
    if len(rek) < MIN_MECZOW:
        return None

    w = wektory_ligi(rek, liga)
    if w is None:
        return None

    b_model = brier_wieloklasowy(w["model"], w["y"])
    b_rynek = brier_wieloklasowy(w["rynek"], w["y"])
    b_mix = brier_wieloklasowy(w["mix"], w["y"])

    return {
        "liga": liga,
        "n": len(w["y"]),
        "bez_ceny": w["bez_ceny"],
        "brier_model": float(b_model.mean()),
        "brier_rynek": float(b_rynek.mean()),
        "brier_mix": float(b_mix.mean()),
        # T1/T2 dodatnie = przewaga nad rynkiem (rynek ma WYZSZY Brier, czyli gorszy)
        "T1": sparowana_roznica(b_rynek, b_model),
        "T2": sparowana_roznica(b_rynek, b_mix),
        # Suma i suma kwadratow roznic per mecz. Z tej trojki (n, suma, suma
        # kwadratow) srednia i wariancja POLACZONEJ proby odtwarzaja sie
        # DOKLADNIE, wiec hipoteze grupowa mozna policzyc po scaleniu shardow
        # bez przenoszenia 100k liczb przez plik.
        "d_n": int(len(b_rynek)),
        "d_sum": float((b_rynek - b_mix).sum()),
        "d_sumsq": float(((b_rynek - b_mix) ** 2).sum()),
    }


def _polacz(czesci: list[dict]) -> tuple[int, float, float] | None:
    """(n, srednia, SE) połączonej próby z trójek (n, suma, suma kwadratów)."""
    n = sum(c["d_n"] for c in czesci)
    if n < 2:
        return None
    s = sum(c["d_sum"] for c in czesci)
    sq = sum(c["d_sumsq"] for c in czesci)
    srednia = s / n
    war = (sq - s * s / n) / (n - 1)
    return n, srednia, float(np.sqrt(max(war, 0.0) / n))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--od", default=OKNO_OD)
    p.add_argument("--ligi", default=None, help="po przecinku; domyslnie wszystkie")
    p.add_argument("--wynik", default=None, help="sciezka JSON z pelnym wynikiem")
    p.add_argument("--scal", nargs="+", default=None,
                   help="zamiast liczyc: wczytaj te JSON-y i wypisz raport zbiorczy")
    args = p.parse_args()

    from footstats.core.testy_przewagi import korekta_sidaka

    if args.scal:
        wyniki = []
        for sciezka in args.scal:
            wyniki += json.loads(Path(sciezka).read_text(encoding="utf-8"))["ligi"]
        raport(wyniki, args.od, korekta_sidaka)
        return

    from footstats.data.historical_loader import load_cached

    df = load_cached()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    zrodlo = df.groupby("league")["source"].agg(
        lambda s: s.mode().iat[0] if len(s.mode()) else "?").to_dict()

    ligi = ([x.strip() for x in args.ligi.split(",")] if args.ligi
            else sorted(df["league"].unique()))

    wyniki = []
    for i, liga in enumerate(ligi, 1):
        print(f"[{i}/{len(ligi)}] {liga} ...", flush=True)
        try:
            w = zmierz_lige(df, liga, args.od)
        except (ValueError, KeyError) as e:
            print(f"    POMINIETA: {e}", flush=True)
            continue
        if w is None:
            print(f"    pominieta (< {MIN_MECZOW} meczow albo brak cen)", flush=True)
            continue
        w["grupa"] = zrodlo.get(liga, "?")
        wyniki.append(w)
        print(f"    n={w['n']}  T2={w['T2']['roznica']:+.5f}"
              f"  z={w['T2']['z']:.2f}", flush=True)

    if not wyniki:
        raise SystemExit("Zero lig w wyniku.")

    if args.wynik:
        Path(args.wynik).write_text(
            json.dumps({"od": args.od, "ligi": wyniki}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nZapisane: {args.wynik}")

    raport(wyniki, args.od, korekta_sidaka)


def raport(wyniki: list[dict], od: str, korekta_sidaka) -> None:
    """Tabela lig + hipoteza grupowa.

    Wspolna dla przebiegu jednoprocesowego i dla `--scal`, zeby scalanie
    shardow nie liczylo niczego innym kodem niz przebieg pojedynczy.
    """
    ile = len(wyniki)
    print("\n" + "=" * 104)
    print(f"  PRZEWAGA NAD RYNKIEM — Brier wieloklasowy, sparowany. Okno od {od}.")
    print("  T1 = rynek - model (model sam)   |   T2 = rynek - mix (model PONAD cene)")
    print("  Dodatnie = model lepszy. p po korekcie Sidaka na", ile, "lig.")
    print("=" * 104)
    print(f"{'liga':<32}{'grupa':<13}{'n':>6}{'Brier rynek':>13}"
          f"{'T1':>10}{'T2':>10}{'SE':>9}{'z':>7}{'p_kor':>9}")
    print("-" * 104)
    for w in sorted(wyniki, key=lambda x: -(x["T2"]["z"] or -99)):
        t2 = w["T2"]
        pk = korekta_sidaka(p_jednostronne(t2["z"]), ile) if t2["z"] is not None else None
        print(f"{w['liga']:<32}{w['grupa']:<13}{w['n']:>6}{w['brier_rynek']:>13.4f}"
              f"{w['T1']['roznica']:>+10.4f}{t2['roznica']:>+10.4f}"
              f"{t2['se']:>9.4f}{t2['z']:>7.2f}"
              f"{(f'{pk:.4f}' if pk is not None else '-'):>9}")
    print("-" * 104)

    print("\nHIPOTEZA GLOWNA (jedno porownanie, pre-rejestrowane):")
    print("  srednie T2 w `fdco_new` (nigdy niemierzone) > srednie T2 w `fdco_season`")
    grupy: dict[str, tuple[int, float, float] | None] = {}
    for g in ("fdco_new", "fdco_season"):
        czesci = [w for w in wyniki if w["grupa"] == g]
        grupy[g] = _polacz(czesci) if czesci else None
        if grupy[g]:
            n, sr, se = grupy[g]  # type: ignore[misc]
            print(f"  {g:<14} n={n:>6}  T2={sr:+.5f}  SE={se:.5f}  z={sr/se:+.2f}"
                  f"  (lig: {len(czesci)})")

    a, b = grupy.get("fdco_new"), grupy.get("fdco_season")
    if a and b:
        # Dwie ROZLACZNE proby meczow — tu SE niesparowane jest wlasciwe.
        se = float(np.sqrt(a[2] ** 2 + b[2] ** 2))
        roz = a[1] - b[1]
        z = roz / se if se > 0 else None
        print(f"\n  ROZNICA GRUP: {roz:+.5f}  SE={se:.5f}"
              f"  z={z:+.2f}  p={p_jednostronne(z):.4f}" if z is not None else "")
        print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
        print("    p_kor >= 0.05 we WSZYSTKICH ligach -> pytanie o edge ZAMKNIETE,")
        print("    zadnych podzbiorow. Inaczej: holdout po dacie, pre-rejestrowany osobno.")


if __name__ == "__main__":
    main()
