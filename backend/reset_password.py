"""
Operator tool, run from the Render shell. Never exposed over the web.

  python -m backend.reset_password --list
      Lists every account with its role and owner, so you can spot admin
      accounts nobody recognises (public signup used to be open).

  python -m backend.reset_password <username>
      Sets a new password for that account. You are asked for it twice and it
      is never shown. Every device signed in to the account is signed out.
"""
import sys
import getpass

from backend.database import SessionLocal, User
from backend.main import hash_password, validate_new_password, business_now


def list_accounts(db) -> None:
    users = db.query(User).order_by(User.id).all()
    names = {u.id: u.username for u in users}
    print(f"{'ID':>4}  {'USERNAME':<24} {'ROLE':<10} {'OWNER':<20} SUSPENDED")
    for u in users:
        owner = names.get(u.owner_id, "") if u.owner_id else ""
        print(f"{u.id:>4}  {u.username:<24} {u.role or '':<10} {owner:<20} "
              f"{'yes' if getattr(u, 'is_suspended', False) else ''}")


def reset(db, username: str) -> int:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        print(f"No account named {username!r}. Use --list to see accounts.")
        return 1
    pw1 = getpass.getpass("New password (8+ characters): ")
    pw2 = getpass.getpass("Repeat new password: ")
    if pw1 != pw2:
        print("The passwords don't match. Nothing changed.")
        return 1
    try:
        validate_new_password(pw1)
    except Exception as e:
        print(f"Password rejected: {getattr(e, 'detail', e)}")
        return 1
    user.previous_password_hash = user.password
    user.password = hash_password(pw1)
    user.password_changed_at = business_now().strftime("%Y-%m-%dT%H:%M:%S")
    user.needs_password_reset = False
    user.token_version = (user.token_version or 0) + 1   # signs out every device
    db.commit()
    print(f"Password for {username!r} changed. All of its sessions were signed out.")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    db = SessionLocal()
    try:
        if sys.argv[1] == "--list":
            list_accounts(db)
            return 0
        return reset(db, sys.argv[1])
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
