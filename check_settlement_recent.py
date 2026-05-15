import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

db_path = Path("data/footstats_backtest.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

now = datetime.now()
four_hours_ago = (now - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")

print(f"Checking matches older than: {four_hours_ago}")

try:
    # Check only matches from the last 7 days that are not settled
    seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT id, match_date, team_home, team_away FROM predictions WHERE actual_result IS NULL AND match_date < ? AND match_date > ?", (four_hours_ago, seven_days_ago))
    rows = cursor.fetchall()

    if not rows:
        print("SUCCESS: All matches from the last 7 days are settled.")
    else:
        print(f"WARNING: Found {len(rows)} unsettled matches from the last 7 days:")
        for row in rows:
            print(f"ID: {row['id']} | Date: {row['match_date']} | {row['team_home']} vs {row['team_away']}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
