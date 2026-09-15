"""Seed local SQLite whitelist accounts. Safe to run repeatedly."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auth import hash_password  # noqa: E402
from src.config import DEFAULT_ACCOUNT_PASSWORDS  # noqa: E402
from src.data_store import SqliteStore  # noqa: E402

DB_PATH = ROOT / "data" / "app.sqlite"

ACCOUNTS = (
    ("poopoo1993@gmail.com", "teacher"),
    ("eric82923@gmail.com", "student"),
)


def main() -> None:
    store = SqliteStore(str(DB_PATH), "Asia/Taipei")
    for email, role in ACCOUNTS:
        store.upsert_whitelist(email, role, True)
        password = DEFAULT_ACCOUNT_PASSWORDS.get(email)
        if password and not store.has_login_password(email):
            store.set_password_hash(email, hash_password(password))
            print(f"whitelist: {email} ({role}, enabled, password set)")
        else:
            print(f"whitelist: {email} ({role}, enabled)")


if __name__ == "__main__":
    main()
