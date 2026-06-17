"""
calibration_monitor.py — FAZA 17.7: monitoring kalibracji modelu na Neon (prod).

Serwuje priorytet M1: czy po fixach Fazy 17 kalibracja jest MONOTONICZNA
(wyższa pewność → wyższa trafność), oraz jak radzi sobie System paper-trading
(single-leg, flat 2 PLN) pod kątem win rate i ROI.

Read-only. Uruchom: python scripts/calibration_monitor.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass

from footstats.utils.db import connect  # noqa: E402


def _sep(title: str) -> None:
    print(f"\n{'=' * 56}\n  {title}\n{'=' * 56}")


def _pct(hits, total) -> str:
    return f"{(hits / total * 100):.1f}%" if total else "—"


def raport_kalibracji() -> None:
    """Trafność per pasmo pewności + werdykt monotoniczności."""
    _sep("KALIBRACJA — trafność per pasmo pewności")
    with connect() as c:
        rows = c.execute(
            "SELECT (ai_confidence/10)*10 AS band, COUNT(*) AS n, "
            "SUM(CASE WHEN tip_correct=1 THEN 1 ELSE 0 END) AS won "
            "FROM predictions WHERE tip_correct IS NOT NULL AND ai_confidence > 0 "
            "GROUP BY band ORDER BY band"
        ).fetchall()

    pasma = []
    for r in rows:
        band, n, won = r["band"], r["n"], r["won"] or 0
        acc = won / n * 100 if n else 0
        pasma.append((band, n, won, acc))
        print(f"  {band:>3}-{band + 9}%:  n={n:<3} trafność={_pct(won, n):<6} ({won}/{n})")

    # Monotoniczność: trafność rośnie z pewnością? (tylko pasma z n>=5)
    istotne = [(b, acc) for (b, n, w, acc) in pasma if n >= 5]
    if len(istotne) >= 2:
        rosnaca = all(istotne[i][1] <= istotne[i + 1][1] + 5 for i in range(len(istotne) - 1))
        pierwsza, ostatnia = istotne[0][1], istotne[-1][1]
        print()
        if ostatnia >= pierwsza:
            print(f"  ✅ Kierunek OK: niskie pasmo {pierwsza:.0f}% → wysokie {ostatnia:.0f}% (rośnie)")
        else:
            print(f"  🔴 ODWRÓCONA: niskie {pierwsza:.0f}% > wysokie {ostatnia:.0f}% — model przekalibrowany")
        print(f"  Monotoniczność (tol. 5pp): {'TAK' if rosnaca else 'NIE — są spadki'}")
    else:
        print("\n  Za mało danych (pasma n>=5) na werdykt — czekaj na więcej settled.")


def raport_per_typ() -> None:
    _sep("TRAFNOŚĆ per typ")
    with connect() as c:
        rows = c.execute(
            "SELECT ai_tip, COUNT(*) AS n, SUM(CASE WHEN tip_correct=1 THEN 1 ELSE 0 END) AS won "
            "FROM predictions WHERE tip_correct IS NOT NULL "
            "GROUP BY ai_tip ORDER BY n DESC"
        ).fetchall()
    for r in rows:
        print(f"  {(r['ai_tip'] or '?'):<14} n={r['n']:<3} trafność={_pct(r['won'] or 0, r['n'])}")


def raport_system_paper() -> None:
    """Win rate + ROI single-leg kuponów System (paper-trading, FAZA 19)."""
    _sep("SYSTEM PAPER-TRADING — win rate + ROI")
    with connect() as c:
        uid = c.execute("SELECT id FROM users WHERE username='System' LIMIT 1").fetchone()
        if not uid:
            print("  Brak użytkownika System.")
            return
        rows = c.execute(
            "SELECT status, total_odds, stake_pln FROM coupons "
            "WHERE user_id = ? AND status IN ('WON','LOST')",
            (uid["id"],),
        ).fetchall()

    if not rows:
        print("  Brak rozliczonych kuponów System jeszcze (czekaj na settlement).")
        return

    won = sum(1 for r in rows if r["status"] == "WON")
    n = len(rows)
    staked = sum((r["stake_pln"] or 0) for r in rows)
    profit = sum(
        ((r["stake_pln"] or 0) * ((r["total_odds"] or 1) - 1)) if r["status"] == "WON"
        else -(r["stake_pln"] or 0)
        for r in rows
    )
    print(f"  Rozliczone : {n}")
    print(f"  Win rate   : {_pct(won, n)} ({won}/{n})")
    print(f"  Postawione : {staked:.2f} PLN")
    print(f"  Zysk netto : {profit:+.2f} PLN")
    print(f"  ROI        : {(profit / staked * 100):+.1f}%" if staked else "  ROI: —")


def raport_system_vs_groq() -> None:
    """
    KLUCZOWY EKSPERYMENT: czy Groq (LLM) pomaga, czy bottleneckiem jest model?
    - System (bez Groq): single-leg kupony, wybór max p_modelu — naiwna selekcja.
    - Pipeline (Groq): typy wybrane przez Groq (tabela predictions).
    Oba używają tych samych prawdopodobieństw Poissona → różni je SELEKCJA.

    Werdykt:
      System ≈ Groq  → bottleneck to model/dane, nie LLM (większy LLM nie pomoże)
      System > Groq  → Groq szkodzi w selekcji (wtedy lepszy LLM/prompt pomoże)
      System < Groq  → Groq dodaje wartość w selekcji
    """
    _sep("SYSTEM (bez Groq) vs PIPELINE (Groq) — izolacja wpływu LLM")
    with connect() as c:
        uid = c.execute("SELECT id FROM users WHERE username='System' LIMIT 1").fetchone()
        sys_n = sys_won = 0
        if uid:
            r = c.execute(
                "SELECT COUNT(*) n, SUM(CASE WHEN status='WON' THEN 1 ELSE 0 END) won "
                "FROM coupons WHERE user_id = ? AND status IN ('WON','LOST')",
                (uid["id"],),
            ).fetchone()
            sys_n, sys_won = r["n"] or 0, r["won"] or 0
        rg = c.execute(
            "SELECT COUNT(*) n, SUM(CASE WHEN tip_correct=1 THEN 1 ELSE 0 END) won "
            "FROM predictions WHERE tip_correct IS NOT NULL"
        ).fetchone()
        groq_n, groq_won = rg["n"] or 0, rg["won"] or 0

    sys_acc = (sys_won / sys_n * 100) if sys_n else None
    groq_acc = (groq_won / groq_n * 100) if groq_n else None
    print(f"  System (bez Groq) : {_pct(sys_won, sys_n)} ({sys_won}/{sys_n})")
    print(f"  Pipeline (Groq)   : {_pct(groq_won, groq_n)} ({groq_won}/{groq_n})")
    print()

    MIN_N = 15
    if sys_n < MIN_N:
        print(f"  ⏳ System ma {sys_n} settled (potrzeba >= {MIN_N}) — paper-trading zbiera dane.")
        print("     Werdykt dostępny gdy System uzbiera próbkę (Task Scheduler 08:00 codziennie).")
        return
    if groq_acc is None:
        print("  Brak danych Groq.")
        return

    delta = sys_acc - groq_acc
    if abs(delta) <= 5:
        print(f"  ⚖️  System ≈ Groq (Δ{delta:+.1f}pp) → BOTTLENECK TO MODEL/DANE, nie LLM.")
        print("     Większy Groq nie podniesie sufitu — popraw lambdy/dane wejściowe.")
    elif delta > 5:
        print(f"  🔴 System > Groq (Δ{delta:+.1f}pp) → Groq SZKODZI w selekcji.")
        print("     Lepszy prompt/LLM lub mocniejsze ograniczenie Groq pomoże.")
    else:
        print(f"  ✅ Groq > System (Δ{delta:+.1f}pp) → Groq dodaje wartość w selekcji.")


def main() -> None:
    print("FootStats — monitor kalibracji (Neon prod, read-only)")
    raport_kalibracji()
    raport_per_typ()
    raport_system_paper()
    raport_system_vs_groq()
    print()


if __name__ == "__main__":
    main()
