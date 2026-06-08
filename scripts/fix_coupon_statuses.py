"""
Migracja: LOSE->LOST, WIN->WON + backfill leg_won dla kuponow z result ale bez leg_won
"""
import sys, json
sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from footstats.core.backtest import _connect
from footstats.utils.betting import oblicz_tip_correct

with _connect() as conn:
    # 1. LOSE -> LOST, WIN -> WON
    r1 = conn.execute("UPDATE coupons SET status='LOST' WHERE status='LOSE'")
    r2 = conn.execute("UPDATE coupons SET status='WON'  WHERE status='WIN'")
    print(f"Status fix: LOSE->LOST={r1.rowcount}, WIN->WON={r2.rowcount}")

    # 2. Backfill leg_won dla kuponow ktore maja result ale nie maja leg_won
    rows = conn.execute("""
        SELECT id, status, legs_json FROM coupons
        WHERE status IN ('WON','LOST','PARTIAL')
        AND legs_json IS NOT NULL
    """).fetchall()

updated = 0
for r in rows:
    legs = json.loads(r['legs_json'] or '[]')
    changed = False
    for leg in legs:
        if leg.get('leg_won') is not None:
            continue
        result = leg.get('result')
        tip    = leg.get('tip', '')
        if not result or not tip:
            continue
        correct = oblicz_tip_correct(tip, result)
        leg['leg_won'] = True if correct == 1 else (False if correct == 0 else None)
        changed = True

    if changed:
        with _connect() as conn2:
            conn2.execute(
                "UPDATE coupons SET legs_json=? WHERE id=?",
                (json.dumps(legs, ensure_ascii=False), r['id'])
            )
        updated += 1
        print(f"  Backfill leg_won kupon #{r['id']}")

print(f"Backfill leg_won: {updated} kuponow zaktualizowanych")

# 3. Raport koncowy
with _connect() as conn:
    rows = conn.execute("""
        SELECT id, status, legs_json FROM coupons
        WHERE status NOT IN ('VOID','DRAFT','ACTIVE')
        ORDER BY id DESC LIMIT 10
    """).fetchall()

print("\n--- STAN PO MIGRACJI ---")
for r in rows:
    legs = json.loads(r['legs_json'] or '[]')
    won  = sum(1 for l in legs if l.get('leg_won') is True)
    lost = sum(1 for l in legs if l.get('leg_won') is False)
    pend = sum(1 for l in legs if l.get('leg_won') is None)
    print(f"  #{r['id']:3d} {r['status']:6s}  ✓{won} ✗{lost} ?{pend}")
