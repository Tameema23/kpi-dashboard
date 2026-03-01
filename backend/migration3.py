"""
Run ONCE in the Render shell after deploying:
  python3 backend/migration3.py
"""
import sqlite3

conn   = sqlite3.connect('/data/kpi.db')
cursor = conn.cursor()

migrations = [
    # Add appt_type to appointments
    ("ALTER TABLE appointments ADD COLUMN appt_type TEXT DEFAULT 'appointment'",
     "appointments.appt_type"),
    # Add can_planner to users
    ("ALTER TABLE users ADD COLUMN can_planner INTEGER DEFAULT 1",
     "users.can_planner"),
    # Add can_quality to users
    ("ALTER TABLE users ADD COLUMN can_quality INTEGER DEFAULT 0",
     "users.can_quality"),
]

for sql, label in migrations:
    try:
        cursor.execute(sql)
        print(f"  Added {label}")
    except Exception as e:
        print(f"  Skipped {label}: {e}")

# Migrate old quality_assistant role → assistant with can_quality=1, can_planner=0
try:
    cursor.execute("""
        UPDATE users SET role='assistant', can_planner=0, can_quality=1
        WHERE role='quality_assistant'
    """)
    n = cursor.rowcount
    print(f"  Migrated {n} quality_assistant account(s) → assistant with can_quality=1")
except Exception as e:
    print(f"  Migration of quality_assistant roles: {e}")

# Ensure old plain assistants have can_planner=1
try:
    cursor.execute("""
        UPDATE users SET can_planner=1 WHERE role='assistant' AND can_planner IS NULL
    """)
    print(f"  Ensured can_planner for existing assistants")
except Exception as e:
    print(f"  {e}")

conn.commit()
conn.close()
print("Migration 3 complete!")