"""Buduje tablicę wzorców czynnik→typ z historii → data/rag_wzorce_historyczne.json.

PO CO: warstwa RAG liczy skuteczność czynników z własnych predykcji, a tych
z niepustymi `factors` jest na produkcji ZERO (pomiar 09.08.2026). Ten skrypt
robi to samo na 139 102 historycznych meczach, dzięki czemu RAG ma liczby od
pierwszego dnia zamiast po tygodniach zbierania.

ANTY-LOOKAHEAD: dla każdego meczu czynniki i predykcja liczą się WYŁĄCZNIE
z meczów wcześniejszych w tej samej lidze. Zapisana data `zbudowano_do` mówi,
do kiedy sięga tablica — backtest na starszym oknie czytałby własną przyszłość.

Użycie:
    python -m scripts.buduj_wzorce_historyczne              # podglad
    python -m scripts.buduj_wzorce_historyczne --zapisz     # zapis do data/
    python -m scripts.buduj_wzorce_historyczne --na-lige 400 --zapisz
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Ligi, w których realnie typujemy albo mamy gęstą historię. Nie wszystkie 40:
# czynniki liczą się z H2H i serii domowych, więc liga z rzadką historią daje
# wzorce zbudowane na szumie.
LIGI = [
    "GER-Bundesliga", "GER-2. Bundesliga", "ENG-Premier League",
    "ENG-Championship", "ESP-La Liga", "ESP-Segunda Division",
    "ITA-Serie A", "ITA-Serie B", "FRA-Ligue 1", "FRA-Ligue 2",
    "NED-Eredivisie", "POL-Ekstraklasa", "POR-Primeira Liga",
    "BEL-First Division A", "TUR-Super Lig", "SCO-Premiership",
]


def zbierz_mecze(na_lige: int) -> tuple[list[dict], str]:
    """Walk-forward po historii → rekordy {"typ", "czynniki", "wynik"}."""
    import pandas as pd

    from footstats.ai.rag import wyciagnij_faktory
    from footstats.core.fatigue import HeurystaZmeczeniaRotacji
    from footstats.core.fortress import HomeFortress
    from footstats.core.h2h import AnalizaH2H
    from footstats.core.poisson import predict_match
    from footstats.core.wf_harness import adapt_to_prod_schema
    from footstats.data.historical_loader import load_cached

    df = adapt_to_prod_schema(load_cached())
    df["_dt"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.sort_values("_dt").reset_index(drop=True)
    do_kiedy = str(df["_dt"].max())[:10]

    rekordy: list[dict] = []
    for liga in LIGI:
        l_df = df[df["league"] == liga].reset_index(drop=True)
        if l_df.empty:
            continue
        probka = l_df.tail(na_lige)
        print(f"  {liga}: {len(probka)} meczow", flush=True)
        for idx, r in probka.iterrows():
            wynik = str(r.get("result", ""))
            if wynik not in ("H", "D", "A"):
                continue
            hist = l_df.iloc[:idx]
            if len(hist) < 200:
                continue

            g, a = str(r["gospodarz"]), str(r["goscie"])
            d = str(r["data"])[:10]
            czynniki = wyciagnij_faktory({
                "h2h_g": AnalizaH2H(hist).analiza(g, a),
                "fortress_g": HomeFortress(hist).analiza(g),
                "heur_g": HeurystaZmeczeniaRotacji(hist).analiza(g, d),
                "heur_a": HeurystaZmeczeniaRotacji(hist).analiza(a, d),
            })
            if not czynniki:
                continue  # bez czynnika mecz nie wnosi nic do tablicy

            p = predict_match(g, a, hist)
            if not p:
                continue
            model = {"1": p["p_wygrana"], "X": p["p_remis"], "2": p["p_przegrana"]}
            typ = max(model, key=lambda k: model[k])
            rekordy.append({
                "typ": typ,
                "czynniki": czynniki,
                # Tip modelu jest w notacji 1/X/2, a wynik meczu w H/D/A —
                # bez tego mapowania KAŻDE porównanie wychodziłoby fałszywie ujemne.
                "wynik": {"H": "1", "D": "X", "A": "2"}[wynik],
            })
    return rekordy, do_kiedy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--na-lige", type=int, default=300,
                        help="ile ostatnich meczow na lige (domyslnie 300)")
    parser.add_argument("--min-probek", type=int, default=None,
                        help="minimum meczow na wzorzec")
    parser.add_argument("--zapisz", action="store_true")
    args = parser.parse_args()

    from footstats.core.wzorce_historyczne import MIN_PROBEK, SCIEZKA, buduj_tablice

    rekordy, do_kiedy = zbierz_mecze(args.na_lige)
    tablica = buduj_tablice(
        rekordy,
        min_probek=args.min_probek or MIN_PROBEK,
        zbudowano_do=do_kiedy,
    )

    print(f"\nmeczow z czynnikiem: {len(rekordy)} | wzorcow ponad progiem:"
          f" {len(tablica['wzorce'])} | dane do {do_kiedy}")
    for klucz, w in sorted(tablica["wzorce"].items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {klucz:26} {w['trafien']:5}/{w['n']:<5}"
              f" = {w['trafien'] / w['n'] * 100:5.1f}%")

    if not args.zapisz:
        print("\nPODGLAD — nic nie zapisano. Powtorz z --zapisz.")
        return

    SCIEZKA.parent.mkdir(parents=True, exist_ok=True)
    SCIEZKA.write_text(json.dumps(tablica, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(f"\nZAPISANO → {SCIEZKA}")


if __name__ == "__main__":
    main()
