from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import Database


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "bot.sqlite3"
        db = Database(db_path)
        await db.initialize()
        await db.initialize()  # migration/init must be idempotent

        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            required = {
                "technicians",
                "histories",
                "ocr_logs",
                "web_link_requests",
                "web_sessions",
            }
            missing = required - tables
            if missing:
                raise AssertionError(f"missing tables: {sorted(missing)}")

            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(technicians)")
            }
            required_columns = {
                "telegram_id",
                "nik",
                "name",
                "sto",
                "password_hash",
                "role",
                "is_active",
            }
            missing_columns = required_columns - columns
            if missing_columns:
                raise AssertionError(
                    f"missing technicians columns: {sorted(missing_columns)}"
                )

    print("database schema smoke test: OK")


if __name__ == "__main__":
    asyncio.run(main())
