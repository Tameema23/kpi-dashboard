"""
Run ONCE in the Render shell after deploying:
  python3 backend/migration2.py
"""
import sqlite3

conn   = sqlite3.connect('/data/kpi.db')
cursor = conn.cursor()

# Create quality_entries table
try:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quality_entries (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id      INTEGER NOT NULL REFERENCES users(id),
            created_by    INTEGER NOT NULL REFERENCES users(id),
            insured_name  TEXT NOT NULL,
            policy_number TEXT DEFAULT '',
            remarks       TEXT DEFAULT '',
            date          TEXT DEFAULT '',
            phone_number  TEXT DEFAULT '',
            follow_up     TEXT DEFAULT '',
            action        TEXT DEFAULT '',
            alp           TEXT DEFAULT '',
            created_at    TEXT DEFAULT ''
        )
    ''')
    print("✓ Created quality_entries table")
except Exception as e:
    print(f"  Error: {e}")

conn.commit()
conn.close()
print("Migration 2 complete!")