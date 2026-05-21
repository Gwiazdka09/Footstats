import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

db_path = Path("data/footstats_backtest.db")
if not db_path.exists():
    print("Database not found.")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get matches older than 4 hours from now
now = datetime.now()
four_hours_ago = (now - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")

print(f"Checking matches older than: {four_hours_ago}")

try:
    cursor.execute("SELECT id, match_date, team_home, team_away FROM predictions WHERE actual_result IS NULL AND match_date < ?", (four_hours_ago,))
    rows = cursor.fetchall()

    if not rows:
        print("SUCCESS: All past matches are settled.")
    else:
        print(f"WARNING: Found {len(rows)} unsettled past matches:")
        for row in rows:
            print(f"ID: {row['id']} | Date: {row['match_date']} | {row['team_home']} vs {row['team_away']}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
