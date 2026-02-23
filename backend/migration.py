"""
Run this ONCE in the Render shell to migrate the existing database.
Command: python3 migration.py
"""
import sqlite3

conn = sqlite3.connect('/data/kpi.db')
cursor = conn.cursor()

# 1. Add owner_id to users table (for assistants)
try:
    cursor.execute('ALTER TABLE users ADD COLUMN owner_id INTEGER REFERENCES users(id)')
    print("✓ Added owner_id to users table")
except Exception as e:
    print(f"  users.owner_id already exists or error: {e}")

# 2. Add owner_id to appointments table
try:
    cursor.execute('ALTER TABLE appointments ADD COLUMN owner_id INTEGER REFERENCES users(id)')
    print("✓ Added owner_id to appointments table")
except Exception as e:
    print(f"  appointments.owner_id already exists or error: {e}")

# 3. For existing appointments with no owner_id, assign them to the first admin found
cursor.execute("SELECT id FROM users WHERE role='admin' OR role IS NULL LIMIT 1")
first_admin = cursor.fetchone()
if first_admin:
    cursor.execute("UPDATE appointments SET owner_id=? WHERE owner_id IS NULL", (first_admin[0],))
    print(f"✓ Assigned existing appointments to admin id={first_admin[0]}")

# 4. Existing assistants (if any) have no owner - set owner_id to first admin
# (You may want to manually reassign these if you have multiple admins)
cursor.execute("SELECT id FROM users WHERE role='admin' OR role IS NULL LIMIT 1")
first_admin = cursor.fetchone()
if first_admin:
    cursor.execute("UPDATE users SET owner_id=? WHERE role='assistant' AND owner_id IS NULL", (first_admin[0],))
    print(f"✓ Assigned existing assistants to admin id={first_admin[0]}")

conn.commit()
conn.close()
print("\nMigration complete!")