import sqlite3
from pathlib import Path

BACKTEST_DB = Path("data/footstats_backtest.db")


def clean_db() -> None:
    """Usuwa 'osierocone' rekordy o statusie pending starsze niz 3 dni."""
    if not BACKTEST_DB.exists() or BACKTEST_DB.stat().st_size == 0:
        print("Baza danych nie istnieje lub jest pusta. Przerywam czyszczenie.")
        return

    try:
        conn = sqlite3.connect(str(BACKTEST_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='predictions'")
        if not cursor.fetchone():
            print(f"W bazie {BACKTEST_DB} nie znaleziono tabeli 'predictions'.")
            conn.close()
            return

        print(f"Czyszczenie bazy: {BACKTEST_DB}")

        cursor.execute("SELECT count(*) FROM predictions WHERE actual_result IS NULL")
        count_before = cursor.fetchone()[0]
        print(f"   Meczów 'pending' przed czyszczeniem: {count_before}")

        cursor.execute("""
            DELETE FROM predictions
            WHERE actual_result IS NULL
            AND match_date < date('now', '-3 days')
            AND (coupon_id IS NULL OR coupon_id = '')
        """)

        deleted = cursor.rowcount
        conn.commit()

        cursor.execute("SELECT count(*) FROM predictions WHERE actual_result IS NULL")
        count_after = cursor.fetchone()[0]
        print(f"Gotowe! Usunieto {deleted} 'osieroconych' meczów-widm.")
        print(f"   Meczów 'pending' po czyszczeniu: {count_after}")

        print("Optymalizacja bazy (VACUUM)...")
        conn.execute("VACUUM")
        conn.close()
    except Exception as e:
        print(f"Blad podczas czyszczenia: {e}")


if __name__ == "__main__":
    clean_db()
