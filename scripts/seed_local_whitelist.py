"""Seed local SQLite whitelist accounts. Safe to run repeatedly."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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
        print(f"whitelist: {email} ({role}, enabled)")


if __name__ == "__main__":
    main()
