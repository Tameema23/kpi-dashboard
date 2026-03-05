"""
migration4.py — Add booking_tz column to appointments table
Run once on the server: python migration4.py
"""
import sqlite3

DB_PATH = "/data/kpi.db"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Add booking_tz column (safe — ignores if already exists)
try:
    cur.execute("ALTER TABLE appointments ADD COLUMN booking_tz TEXT DEFAULT 'America/Edmonton'")
    print("Added booking_tz column to appointments")
except Exception as e:
    print(f"Skipped (likely already exists): {e}")

conn.commit()
conn.close()
print("Migration 4 complete.")