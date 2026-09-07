#!/usr/bin/env python
"""clv_raport.py — czy bijemy linię zamknięcia. READ-ONLY.

PO CO. Trafność i ROI mówią, co się stało; CLV mówi, czy **cena**, którą
wzięliśmy, była lepsza od ceny rynkowej tuż przed meczem. To jedyny pomiar
przewagi, który nie musi czekać na wyniki i nie tonie w wariancji — przy 429
rozliczonych kuponach ROI ma przedział ufności szerszy niż mierzony efekt,
a CLV nie.

Do 2026-09-07 nie powstał ani jeden wiersz CLV: cały blok w `evening_agent`
stał pod `if pred_id:`, a `prediction_id` nigdy nie trafiał do nogi kuponu
(0 na 82 nogi w 60 rozliczonych kuponach). Teraz CLV liczy się per noga
i ląduje w `legs_json` jako `clv_closing`.

    python scripts/clv_raport.py
    python scripts/clv_raport.py --dni 30 --min-probek 3

UWAGA na interpretację: CLV liczy się WYŁĄCZNIE dla typów, które mają
odpowiednik w kursach zamknięcia football-data (1, X, 2, Over 2.5, Under 2.5).
BTTS, podwójne szanse, inne linie i kombinacje BetBuildera zostają bez CLV —
to około 24% nóg i ich brak w raporcie NIE znaczy, że były złe.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from footstats.core.clv_tracker import raport_clv_z_kuponow  # noqa: E402
from footstats.utils.db import connect  # noqa: E402


def _pobierz(dni: int) -> list:
    prog = (datetime.now() - timedelta(days=dni)).strftime("%Y-%m-%d")
    with connect() as con:
        wiersze = con.execute(
            """SELECT id, status, match_date_first, legs_json FROM coupons
               WHERE status IN ('WON','LOST','PARTIAL')
                 AND match_date_first >= ?
               ORDER BY match_date_first""",
            (prog,),
        ).fetchall()
    return list(wiersze)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dni", type=int, default=90)
    ap.add_argument("--min-probek", type=int, default=5)
    args = ap.parse_args()

    kupony = _pobierz(args.dni)
    print(f"Kuponow rozliczonych w oknie {args.dni} dni: {len(kupony)}")

    raport = raport_clv_z_kuponow(kupony, min_probek=args.min_probek)
    o = raport["overall"]
    if not o:
        print("\nZERO nog z kursem zamkniecia.")
        print("To NIE jest wynik 'brak przewagi' — to brak pomiaru. Sprawdz:")
        print("  * czy `evening_agent` przeszedl po tych kuponach po naprawie 07.09,")
        print("  * czy football-data.co.uk oddaje CSV (`scrapers/closing_odds.py`),")
        print("  * czy typy nog sa mapowalne (`closing_odds._TYP_NA_KURS`).")
        return 1

    print(f"\nCALOSC: n={o['n']}  sredni CLV {o['clv_avg']:+.2f}%"
          f"  dodatnich {o['positive_pct']:.0f}%")
    print("\nCLV > 0 = wzielismy lepsza cene niz rynek zamknal.")
    print("CLV < 0 = rynek byl madrzejszy; przy tej samej trafnosci tracimy na cenie.\n")

    if raport["per_typ"]:
        print(f"{'typ':<14}{'n':>5}{'sredni CLV':>13}{'dodatnich':>12}")
        for t in raport["per_typ"]:
            print(f"{t['typ']:<14}{t['n']:>5}{t['clv_avg']:>12.2f}%{t['positive_pct']:>11.0f}%")
    else:
        print(f"(zaden typ nie ma {args.min_probek} probek — podnies --dni"
              f" albo obniz --min-probek)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
