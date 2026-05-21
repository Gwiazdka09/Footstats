import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

db_path = Path("data/footstats_backtest.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

now = datetime.now()
four_hours_ago = (now - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
two_days_ago = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

print(f"Checking real matches from: {two_days_ago} to {four_hours_ago}")

try:
    cursor.execute("""
        SELECT id, match_date, team_home, team_away 
        FROM predictions 
        WHERE actual_result IS NULL 
        AND match_date < ? 
        AND match_date > ?
        AND team_home NOT LIKE 'Druzyna%'
        AND team_home NOT LIKE 'Gospodarz%'
        AND team_home NOT LIKE '?%'
    """, (four_hours_ago, two_days_ago))
    rows = cursor.fetchall()

    if not rows:
        print("SUCCESS: All real matches from the last 2 days are settled.")
    else:
        print(f"WARNING: Found {len(rows)} unsettled REAL matches from the last 2 days:")
        for row in rows:
            print(f"ID: {row['id']} | Date: {row['match_date']} | {row['team_home']} vs {row['team_away']}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
