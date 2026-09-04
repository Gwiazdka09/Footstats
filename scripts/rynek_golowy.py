#!/usr/bin/env python
"""rynek_golowy.py — czy Over/Under 2.5 to rynek, w którym jesteśmy mniej słabi.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED policzeniem czegokolwiek z rynku golowego.

DLACZEGO TO PYTANIE. Cały werdykt projektu — „model nie bije rynku" — stoi na
1X2: 39 lig na 39 ujemnych, z=−22..−27 przy wadze produkcyjnej. Ale 1X2 w top
ligach to najlepiej wyceniony rynek na świecie, więc przegrana tam nie mówi nic
o rynkach o cieńszej płynności. `model_log` sugeruje coś innego: na 718 żywych
meczach Over 2.5 trafia 56.2%, a 1X2 52.4%. Ta sugestia jest jednak BEZWARTOŚCIOWA
jako dowód — trafności dwóch różnych rynków nie da się porównywać (Over 2.5 ma
dwa wyjścia, 1X2 trzy), a ceny Over/Under nie było dotąd czym sprawdzić.

CO SIĘ ZMIENIŁO 04.09. Dataset dostał `odds_over25_pinn`/`odds_under25_pinn`
(zamknięcie Pinnacle) i `_max` (najlepszy kurs), a `wf_harness` zaczął nieść
`p_over25` w rekordzie. Pytanie stało się mierzalne.

GDZIE MIERZALNE, A GDZIE NIE — i to jest ograniczenie trwałe. Ceny Over/Under
ma wyłącznie sezonowy format football-data: **22 ligi europejskie, 48 510
meczów, od 2019-07**. Nowy format (17 lig pozaeuropejskich) nie ma kursów
golowych W OGÓLE — 25 kolumn, wszystkie 1X2. API-Football ich nie uzupełni:
zmierzone 04.09, kursy sięgają najwyżej **7 dni wstecz** (−3/−5/−7 dni: komplet
rynków; −10 i dalej: pusto). Ten pomiar odpowiada więc o Europie i nie wolno
przenosić wniosku na resztę.

RAMIĘ MODELU. `p_over25` pochodzi z czystego Poissona — `ensemble_probs` dotyka
wyłącznie 1X2. Porównanie jest uczciwe, bo drugie ramię (`pw/pr/pp` ze zrzutu)
też jest czyste: `przewaga_nad_rynkiem.zmierz_lige` liczy replay z
`use_ensemble=False`. Obie strony to model bez domieszki ceny.

MIARY:
  1. T_gole  = Brier(cena O/U) − Brier(model over25), sparowany po meczach.
     Dodatnie = model lepszy od ceny.
  2. T_1x2   = to samo na 1X2, NA TYCH SAMYCH MECZACH. Bez tego nie wiadomo,
     czy różnica bierze się z rynku, czy z próby.
  3. DEFICYT ZNORMALIZOWANY = (Brier_cena − Brier_model) / niepewność, gdzie
     niepewność to Brier prognozy stałej równej częstości bazowej TEJ próby.
     Orientacja jak w T_*: dodatnie = model lepszy od ceny.
     To JEDYNE dopuszczalne porównanie między rynkami i jest zadeklarowane
     z góry: surowe Briery dwóch rynków o różnej liczbie wyjść nie są tą samą
     liczbą, a porównywanie ich wprost to błąd, który wygląda poprawnie.
     Brier liczony wszędzie jako SUMA po wzajemnie wykluczających się wyjściach
     (dla dwóch wyjść: 2·(p−y)^2), żeby konwencja była jedna.
  4. EV PO NAJLEPSZEJ CENIE (`odds_over25_max`/`odds_under25_max`): płasko
     jedna jednostka na każdą stronę o EV > 0, podatek 12% od stawki, SE
     z rozkładu zwrotów pojedynczych zakładów. Reguła identyczna jak
     w `ev_po_najlepszej_cenie.py` — próg zero, bez strojenia.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * T_gole zbiorczo z <= −2  → rynek golowy też nas bije. Pytanie zamknięte;
    nie jest schronieniem. Bez szukania lig i progów, w których „jednak wyszło".
  * |z| < 2  → parytet z ceną golową. To jest jakościowo COŚ INNEGO niż 1X2
    (z=−22..−27) i wtedy deficyt znormalizowany mówi, o ile. Kierunek wart
    dalszej pracy, ale wciąż nie są to pieniądze bez dodatniego EV.
  * z >= +2  → bijemy ostrą cenę golową. Wynik nadzwyczajny, więc zanim
    cokolwiek z niego wyniknie: holdout po dacie, pre-rejestrowany osobno,
    plus sprawdzenie, czy nie stoi na jednej lidze.
  * EV po podatku dodatnie przy z >= 2 → HIPOTEZA, nie zielone światło.

CZEGO TEN POMIAR NIE ZMIENIA: werdyktu o 1X2. Dobry wynik na rynku golowym
znaczyłby, że szukaliśmy w złym miejscu — nie, że model jest lepszy niż był.
=============================================================================

    python scripts/rynek_golowy.py --zrzut sciezka/g*.parquet
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

PODATEK = 0.12
MIN_MECZOW = 200
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}
KOL_PINN = ("odds_over25_pinn", "odds_under25_pinn")
KOL_MAX = ("odds_over25_max", "odds_under25_max")


def wczytaj(wzorce: list[str]) -> pd.DataFrame:
    pliki: list[str] = []
    for w in wzorce:
        pliki += sorted(glob.glob(w))
    if not pliki:
        raise SystemExit(f"Zero plikow dla {wzorce}")
    df = pd.concat([pd.read_parquet(p) for p in pliki], ignore_index=True)
    brak = [k for k in ("p_over25", "actual_over25", *KOL_PINN)
            if k not in df.columns]
    if brak:
        raise SystemExit(f"Zrzut bez kolumn rynku golowego: {brak}."
                         " Potrzebny przebieg po 9dbd377d5.")
    return df


def devig_dwustronny(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Prawdopodobieństwo strony `a` z pary kursów, po zdjęciu marży."""
    ia, ib = 1.0 / a, 1.0 / b
    return ia / (ia + ib)


def brier_dwuwyjsciowy(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Brier jako SUMA po obu wyjściach — ta sama konwencja co wieloklasowy.

    Wersja jednostronna (p-y)^2 dałaby liczbę o połowę mniejszą i deficyt
    znormalizowany wyszedłby dwa razy lepszy, nie zmieniając niczego w danych.
    """
    return (p - y) ** 2 + ((1 - p) - (1 - y)) ** 2


def niepewnosc_dwuwyjsciowa(y: np.ndarray) -> float:
    p = float(y.mean())
    return 2 * p * (1 - p)


def niepewnosc_wieloklasowa(y: np.ndarray, k: int = 3) -> float:
    czest = np.array([(y == i).mean() for i in range(k)])
    return float((czest * (1 - czest)).sum())


def _fmt(z: float | None, szer: int) -> str:
    """`z` w kolumnie o stałej szerokości; None (SE=0) jako `n/d`."""
    return (f"{z:+.2f}" if z is not None else "n/d").rjust(szer)


def zmierz_lige(d: pd.DataFrame) -> dict | None:
    """Rynek golowy i 1X2 NA TYCH SAMYCH MECZACH jednej ligi."""
    # Kurs <= 1.0 nie jest cena, tylko dziura w danych: odwrotnosc wychodzi
    # nieskonczona i zatruwa CALA kolumne prawdopodobienstw. `devig_1x2`
    # w produkcji ma dokladnie ten sam warunek — tu byl go poczatkowo brak.
    kursy = ["odds_h", "odds_d", "odds_a", *KOL_PINN]
    ok = (d[list(KOL_PINN)].notna().all(axis=1)
          & d["p_over25"].notna() & d["actual_over25"].notna()
          & d["actual_res"].isin(WYNIK_NA_INDEKS)
          & d[kursy].notna().all(axis=1)
          & (d[kursy] > 1.0).all(axis=1))
    d = d[ok]
    if len(d) < MIN_MECZOW:
        return None

    y_g = d["actual_over25"].to_numpy(dtype=float)
    p_mod = d["p_over25"].to_numpy(dtype=float) / 100.0
    p_ryn = devig_dwustronny(d[KOL_PINN[0]].to_numpy(dtype=float),
                             d[KOL_PINN[1]].to_numpy(dtype=float))
    b_mod = brier_dwuwyjsciowy(p_mod, y_g)
    b_ryn = brier_dwuwyjsciowy(p_ryn, y_g)
    unc_g = niepewnosc_dwuwyjsciowa(y_g)

    # 1X2 na tej samej probie — inaczej roznica moglaby pochodzic z proby.
    y_m = d["actual_res"].map(WYNIK_NA_INDEKS).to_numpy(dtype=int)
    p_m_mod = d[["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0
    inv = 1.0 / d[["odds_h", "odds_d", "odds_a"]].to_numpy(dtype=float)
    p_m_ryn = inv / inv.sum(axis=1, keepdims=True)
    bm_mod = brier_wieloklasowy(p_m_mod, y_m)
    bm_ryn = brier_wieloklasowy(p_m_ryn, y_m)
    unc_m = niepewnosc_wieloklasowa(y_m)

    d_g = b_ryn - b_mod
    d_m = bm_ryn - bm_mod
    return {
        "liga": d["league"].iat[0],
        "n": len(d),
        "czestosc_over": float(y_g.mean()),
        "T_gole": sparowana_roznica(b_ryn, b_mod),
        "T_1x2": sparowana_roznica(bm_ryn, bm_mod),
        # Ta sama orientacja co `T_*`: DODATNIE = model lepszy od ceny.
        # Odwrotna kolejnosc odejmowania dawalaby deficyt o znaku przeciwnym
        # do sasiedniej kolumny w tej samej tabeli — i tak bylo do pierwszego
        # przebiegu testow.
        "deficyt_gole": (float(b_ryn.mean()) - float(b_mod.mean())) / unc_g,
        "deficyt_1x2": (float(bm_ryn.mean()) - float(bm_mod.mean())) / unc_m,
        "d_n": int(len(d_g)), "d_sum": float(d_g.sum()),
        "d_sumsq": float((d_g ** 2).sum()),
        "m_n": int(len(d_m)), "m_sum": float(d_m.sum()),
        "m_sumsq": float((d_m ** 2).sum()),
    }


def polacz(czesci: list[dict], pre: str) -> tuple[int, float, float] | None:
    n = sum(c[f"{pre}_n"] for c in czesci)
    if n < 2:
        return None
    s = sum(c[f"{pre}_sum"] for c in czesci)
    sq = sum(c[f"{pre}_sumsq"] for c in czesci)
    war = (sq - s * s / n) / (n - 1)
    return n, s / n, float(np.sqrt(max(war, 0.0) / n))


def ev_najlepsza_cena(df: pd.DataFrame) -> dict | None:
    """Płasko 1 jednostka na każdą stronę o EV > 0, po najlepszym kursie."""
    # Ten sam guard co wyzej. Kurs <= 1.0 dawalby EV rosnace bez ograniczenia
    # i zakład wchodzilby do stawki ZAWSZE — czyli dziura w danych ladowalaby
    # prosto w ROI, jako zysk.
    ok = (df[list(KOL_MAX)].notna().all(axis=1)
          & (df[list(KOL_MAX)] > 1.0).all(axis=1)
          & df["p_over25"].notna() & df["actual_over25"].notna())
    d = df[ok]
    if len(d) < MIN_MECZOW:
        return None

    p_over = d["p_over25"].to_numpy(dtype=float) / 100.0
    y = d["actual_over25"].to_numpy(dtype=float)
    p = np.column_stack([p_over, 1.0 - p_over])
    kursy = d[list(KOL_MAX)].to_numpy(dtype=float)
    trafiony = np.column_stack([y == 1.0, y == 0.0])

    maska = (p * kursy - 1.0) > 0
    n = int(maska.sum())
    if n < 2:
        return None
    zwroty = np.where(trafiony[maska], kursy[maska] - 1.0, -1.0)
    se = float(zwroty.std(ddof=1) / np.sqrt(n))
    po = float(zwroty.mean()) - PODATEK
    return {"n": n, "trafione": int(trafiony[maska].sum()),
            "roi": 100 * float(zwroty.mean()), "roi_po": 100 * po,
            "se": 100 * se, "z": (po / se if se > 0 else None)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zrzut", nargs="+", required=True)
    args = ap.parse_args()

    from footstats.core.testy_przewagi import korekta_sidaka

    df = wczytaj(args.zrzut)
    print(f"Zrzut: {len(df)} meczow, {df['league'].nunique()} lig,"
          f" {df['match_date'].min()} .. {df['match_date'].max()}")

    wyniki = []
    for liga, grp in df.groupby("league"):
        w = zmierz_lige(grp)
        if w is None:
            print(f"  {liga}: pominieta (< {MIN_MECZOW} meczow z cena O/U)")
            continue
        wyniki.append(w)
    if not wyniki:
        raise SystemExit("Zero lig z cena golowa.")

    raport(wyniki, df, korekta_sidaka)


def raport(wyniki: list[dict], df: pd.DataFrame, korekta_sidaka) -> None:
    ile = len(wyniki)
    print("\n" + "=" * 108)
    print("  RYNEK GOLOWY (Over/Under 2.5) kontra zamkniecie Pinnacle."
          "  Dodatnie = MODEL lepszy od ceny.")
    print(f"  Te same mecze niosa kolumne 1X2 dla porownania."
          f"  p po korekcie Sidaka na {ile} lig.")
    print("=" * 108)
    print(f"{'liga':<24}{'n':>7}{'%over':>7}{'T_gole':>11}{'SE':>9}{'z':>7}{'p_kor':>8}"
          f"{'T_1x2':>11}{'z_1x2':>8}{'defG':>8}{'def1X2':>8}")
    print("-" * 108)
    for w in sorted(wyniki, key=lambda x: -(x["T_gole"]["z"] or -99)):
        g, m = w["T_gole"], w["T_1x2"]
        pk = korekta_sidaka(p_jednostronne(g["z"]), ile) if g["z"] else None
        # `z` jest None, gdy SE wyszlo zerowe. To nie awaria, ale nie da sie
        # tego sformatowac liczbowo i przy pierwszym przebiegu wywalilo caly
        # raport PO policzeniu wszystkiego.
        zg = _fmt(g["z"], 7)
        zm = _fmt(m["z"], 8)
        pkt = f"{pk:.4f}" if pk is not None else "-"
        print(f"{w['liga']:<24}{w['n']:>7}{100*w['czestosc_over']:>6.1f}%"
              f"{g['roznica']:>+11.5f}{g['se']:>9.5f}{zg}{pkt:>8}"
              f"{m['roznica']:>+11.5f}{zm}"
              f"{100*w['deficyt_gole']:>+7.1f}%{100*w['deficyt_1x2']:>+7.1f}%")
    print("-" * 108)

    zg = polacz(wyniki, "d")
    zm = polacz(wyniki, "m")
    if not zg or not zm:
        return
    ng, sg, eg = zg
    nm, sm, em = zm
    z_g = sg / eg if eg else 0.0
    print(f"\n  ZBIORCZO rynek golowy   n={ng}  Brier {sg:+.5f}  SE {eg:.5f}"
          f"  z={z_g:+.2f}")
    print(f"  ZBIORCZO 1X2 (te same)  n={nm}  Brier {sm:+.5f}  SE {em:.5f}"
          f"  z={(sm / em if em else 0):+.2f}")

    dg = np.mean([w["deficyt_gole"] for w in wyniki])
    dm = np.mean([w["deficyt_1x2"] for w in wyniki])
    print("\n  DEFICYT ZNORMALIZOWANY (srednia po ligach, ujemne = gorsi od ceny):")
    print(f"    rynek golowy {100*dg:+.1f}% niepewnosci")
    print(f"    1X2          {100*dm:+.1f}% niepewnosci")
    print("    Tylko ta para jest porownywalna miedzy rynkami — surowe Briery")
    print("    dwoch i trzech wyjsc to nie ta sama liczba.")

    ev = ev_najlepsza_cena(df)
    if ev and ev["z"] is not None:
        print("\n  EV PO NAJLEPSZEJ CENIE (`_max`), plasko 1 jednostka, prog EV>0:")
        print(f"    zakladow {ev['n']}  trafione {ev['trafione']}"
              f"  ROI brutto {ev['roi']:+.2f}%  po 12% {ev['roi_po']:+.2f}%"
              f"  SE {ev['se']:.2f}%  z {ev['z']:+.2f}")

    print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
    if z_g <= -2:
        print("    z <= -2 -> rynek golowy TEZ nas bije. Nie jest schronieniem.")
        print("    Pytanie zamkniete, bez szukania lig i progow.")
    elif z_g >= 2:
        print("    z >= +2 -> bijemy ostra cene golowa. Zanim cokolwiek z tego")
        print("    wyniknie: holdout po dacie i sprawdzenie, czy nie stoi")
        print("    na jednej lidze.")
    else:
        print("    |z| < 2 -> PARYTET z cena golowa. Jakosciowo co innego niz")
        print("    1X2 (z=-22..-27). Kierunek wart pracy, ale bez dodatniego EV")
        print("    to nie sa pieniadze.")
    print("\n  Zakres: 22 ligi europejskie. 17 lig pozaeuropejskich nie ma cen")
    print("  golowych ani u football-data, ani wstecz w API-Football (okno 7 dni).")


if __name__ == "__main__":
    main()
