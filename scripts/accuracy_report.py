"""scripts/accuracy_report.py — hit-rate report per liga, typ, confidence band, source."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

DB_PATH = Path(__file__).parents[1] / "data" / "footstats_backtest.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _pct(hits: int, total: int) -> str:
    if total == 0:
        return "  —  "
    return f"{hits / total * 100:5.1f}%"


def _section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("=" * 60)


def _table(rows: list[tuple[Any, ...]], headers: list[str]) -> None:
    widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*row))


def report_overall(conn: sqlite3.Connection) -> None:
    _section("OVERALL")
    row = conn.execute(
        "SELECT COUNT(*) total, SUM(tip_correct) hits FROM predictions WHERE tip_correct IS NOT NULL"
    ).fetchone()
    total, hits = row["total"], int(row["hits"] or 0)
    print(f"  Settled predictions : {total}")
    print(f"  Hit rate            : {_pct(hits, total)}  ({hits}/{total})")


def report_per_liga(conn: sqlite3.Connection) -> None:
    _section("HIT RATE PER LIGA (min 5 settled)")
    rows = conn.execute(
        """
        SELECT league,
               COUNT(*) AS total,
               SUM(tip_correct) AS hits
        FROM predictions
        WHERE tip_correct IS NOT NULL AND league != ''
        GROUP BY league
        HAVING total >= 5
        ORDER BY hits * 1.0 / total DESC
        """
    ).fetchall()
    data = [(r["league"], r["total"], f"{int(r['hits'] or 0)}/{r['total']}", _pct(int(r["hits"] or 0), r["total"])) for r in rows]
    _table(data, ["Liga", "Settled", "Hits", "Hit%"])


def report_per_typ(conn: sqlite3.Connection) -> None:
    _section("HIT RATE PER TYP ZAKŁADU (min 5 settled)")
    rows = conn.execute(
        """
        SELECT ai_tip,
               COUNT(*) AS total,
               SUM(tip_correct) AS hits
        FROM predictions
        WHERE tip_correct IS NOT NULL AND ai_tip NOT IN ('', 'Brak danych', 'Brak', 'ML')
        GROUP BY ai_tip
        HAVING total >= 5
        ORDER BY hits * 1.0 / total DESC
        """
    ).fetchall()
    data = [(r["ai_tip"], r["total"], f"{int(r['hits'] or 0)}/{r['total']}", _pct(int(r["hits"] or 0), r["total"])) for r in rows]
    _table(data, ["Typ", "Settled", "Hits", "Hit%"])


def report_per_confidence(conn: sqlite3.Connection) -> None:
    _section("HIT RATE PER CONFIDENCE BAND")
    bands = [(50, 60), (60, 70), (70, 80), (80, 91)]
    data = []
    for lo, hi in bands:
        row = conn.execute(
            "SELECT COUNT(*) total, SUM(tip_correct) hits FROM predictions "
            "WHERE tip_correct IS NOT NULL AND ai_confidence >= ? AND ai_confidence < ?",
            (lo, hi),
        ).fetchone()
        total, hits = row["total"], int(row["hits"] or 0)
        data.append((f"{lo}-{hi}%", total, f"{hits}/{total}", _pct(hits, total)))
    # 80+
    row = conn.execute(
        "SELECT COUNT(*) total, SUM(tip_correct) hits FROM predictions "
        "WHERE tip_correct IS NOT NULL AND ai_confidence >= 80"
    ).fetchone()
    total, hits = row["total"], int(row["hits"] or 0)
    data.append(("80%+", total, f"{hits}/{total}", _pct(hits, total)))
    _table(data, ["Band", "Settled", "Hits", "Hit%"])


def report_per_kupon_type(conn: sqlite3.Connection) -> None:
    _section("HIT RATE PER KUPON TYPE")
    rows = conn.execute(
        """
        SELECT kupon_type,
               COUNT(*) AS total,
               SUM(tip_correct) AS hits
        FROM predictions
        WHERE tip_correct IS NOT NULL AND kupon_type != ''
        GROUP BY kupon_type
        HAVING total >= 3
        ORDER BY hits * 1.0 / total DESC
        """
    ).fetchall()
    data = [(r["kupon_type"], r["total"], f"{int(r['hits'] or 0)}/{r['total']}", _pct(int(r["hits"] or 0), r["total"])) for r in rows]
    _table(data, ["Kupon Type", "Settled", "Hits", "Hit%"])


def report_coupon_summary(conn: sqlite3.Connection) -> None:
    _section("COUPON P&L SUMMARY")
    rows = conn.execute(
        """
        SELECT status, COUNT(*) cnt,
               SUM(stake_pln) stake,
               SUM(CASE WHEN payout_pln IS NOT NULL THEN payout_pln ELSE 0 END) payout
        FROM coupons
        WHERE status IN ('WON', 'LOST', 'WIN', 'LOSE', 'ACTIVE', 'VOID')
        GROUP BY status
        """
    ).fetchall()
    total_stake = 0.0
    total_payout = 0.0
    data = []
    for r in rows:
        st, cnt = r["status"], r["cnt"]
        stake = r["stake"] or 0.0
        payout = r["payout"] or 0.0
        total_stake += stake
        total_payout += payout
        data.append((st, cnt, f"{stake:.1f} PLN", f"{payout:.1f} PLN"))
    _table(data, ["Status", "Count", "Stake", "Payout"])
    roi = (total_payout - total_stake) / total_stake * 100 if total_stake > 0 else 0
    print(f"\n  Total stake  : {total_stake:.1f} PLN")
    print(f"  Total payout : {total_payout:.1f} PLN")
    print(f"  ROI          : {roi:+.1f}%")


def main() -> None:
    with _connect() as conn:
        report_overall(conn)
        report_per_liga(conn)
        report_per_typ(conn)
        report_per_confidence(conn)
        report_per_kupon_type(conn)
        report_coupon_summary(conn)
    print()


if __name__ == "__main__":
    main()
