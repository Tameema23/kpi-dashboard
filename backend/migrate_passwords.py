"""
migrate_passwords.py
────────────────────
Place this file in your backend/ folder alongside main.py and database.py.

Run from your PROJECT ROOT like this:
    python backend/migrate_passwords.py

What it does:
  1. Adds token_version column to users table (for JWT invalidation)
  2. Adds needs_password_reset column (for short-password accounts)
  3. Adds audit_logs table
  4. Hashes all plain-text passwords with bcrypt
  5. If a password was under 8 characters: still hashed, account flagged
     for a reset prompt on next login — user is NOT locked out

Safe to run multiple times.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from passlib.context import CryptContext
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////data/kpi.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def is_bcrypt(s):
    return s.startswith("$2b$") or s.startswith("$2a$")

engine = create_engine(DATABASE_URL, connect_args=connect_args)

with engine.connect() as conn:

    # Add token_version
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0"))
        conn.commit()
        print("+ Added token_version column")
    except:
        print("  token_version already exists")

    # Add needs_password_reset
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN needs_password_reset INTEGER DEFAULT 0"))
        conn.commit()
        print("+ Added needs_password_reset column")
    except:
        print("  needs_password_reset already exists")

    # Add audit_logs table
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                action    VARCHAR(100) NOT NULL,
                detail    VARCHAR(500) DEFAULT '',
                timestamp VARCHAR(20) NOT NULL
            )
        """))
        conn.commit()
        print("+ audit_logs table ready")
    except Exception as e:
        print(f"  audit_logs: {e}")

    # Hash passwords
    rows = conn.execute(text("SELECT id, username, password FROM users")).fetchall()
    migrated = skipped = flagged = 0

    print(f"\nProcessing {len(rows)} user(s)...")

    for row in rows:
        uid, uname, pw = row.id, row.username, row.password

        if is_bcrypt(pw):
            print(f"  SKIP  {uname!r} — already hashed")
            skipped += 1
            continue

        needs_reset = 1 if len(pw) < 8 else 0
        if needs_reset:
            print(f"  WARN  {uname!r} — password under 8 chars, flagged for reset prompt")
            flagged += 1
        else:
            print(f"  HASH  {uname!r}")

        conn.execute(text(
            "UPDATE users SET password=:pw, token_version=0, needs_password_reset=:nr WHERE id=:id"
        ), {"pw": pwd_context.hash(pw), "nr": needs_reset, "id": uid})
        migrated += 1

    conn.commit()

print(f"""
Done.
  Hashed:   {migrated}
  Skipped:  {skipped}
  Flagged for reset prompt: {flagged}

{"WARNING: " + str(flagged) + " user(s) will see a prompt to update their password on next login." if flagged else "All passwords meet requirements."}
Deploy the new main.py now.
""")