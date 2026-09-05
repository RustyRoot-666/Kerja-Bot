from __future__ import annotations

import asyncio
import csv
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass(frozen=True)
class Technician:
    id: int
    telegram_id: int
    nik: str
    name: str
    sto: str
    created_at: str
    password_hash: str | None = None
    role: str = "technician"
    is_active: int = 1


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    @contextmanager
    def connection(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    async def initialize(self) -> None:
        async with self._lock:
            with self.connection() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS technicians (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER NOT NULL UNIQUE,
                        nik TEXT NOT NULL,
                        name TEXT NOT NULL,
                        sto TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        password_hash TEXT,
                        role TEXT NOT NULL DEFAULT 'technician',
                        is_active INTEGER NOT NULL DEFAULT 1
                    );

                    CREATE TABLE IF NOT EXISTS histories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        technician_id INTEGER NOT NULL,
                        telegram_id INTEGER NOT NULL,
                        kind TEXT NOT NULL CHECK(kind IN ('CONFIG', 'REPORT', 'STO')),
                        ticket_id TEXT,
                        service_number TEXT,
                        old_sn TEXT,
                        new_sn TEXT,
                        ont_type TEXT,
                        sto TEXT,
                        valins_id TEXT,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (technician_id) REFERENCES technicians(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS ocr_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        technician_id INTEGER,
                        telegram_id INTEGER NOT NULL,
                        image_path TEXT NOT NULL,
                        raw_text TEXT NOT NULL,
                        serial_number TEXT,
                        model TEXT,
                        manufacturer TEXT,
                        confidence REAL NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (technician_id) REFERENCES technicians(id) ON DELETE SET NULL
                    );

                    CREATE TABLE IF NOT EXISTS web_link_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token_hash TEXT NOT NULL UNIQUE,
                        telegram_id INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','expired','cancelled')),
                        expires_at TEXT NOT NULL,
                        confirmed_at TEXT,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS web_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token_hash TEXT NOT NULL UNIQUE,
                        technician_id INTEGER NOT NULL,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        FOREIGN KEY (technician_id) REFERENCES technicians(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_histories_telegram ON histories(telegram_id);
                    CREATE INDEX IF NOT EXISTS idx_histories_ticket ON histories(ticket_id);
                    CREATE INDEX IF NOT EXISTS idx_histories_service ON histories(service_number);
                    CREATE INDEX IF NOT EXISTS idx_histories_sn ON histories(old_sn, new_sn);
                    CREATE INDEX IF NOT EXISTS idx_web_link_requests_telegram ON web_link_requests(telegram_id, status);
                    CREATE INDEX IF NOT EXISTS idx_web_sessions_technician ON web_sessions(technician_id);
                    """
                )

                columns = {row["name"] for row in conn.execute("PRAGMA table_info(technicians)").fetchall()}
                migrations = {
                    "sto": "ALTER TABLE technicians ADD COLUMN sto TEXT NOT NULL DEFAULT ''",
                    "password_hash": "ALTER TABLE technicians ADD COLUMN password_hash TEXT",
                    "role": "ALTER TABLE technicians ADD COLUMN role TEXT NOT NULL DEFAULT 'technician'",
                    "is_active": "ALTER TABLE technicians ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
                }
                for column, statement in migrations.items():
                    if column not in columns:
                        conn.execute(statement)

    async def get_technician(self, telegram_id: int) -> Technician | None:
        async with self._lock:
            with self.connection() as conn:
                row = conn.execute(
                    "SELECT id, telegram_id, nik, name, sto, created_at, password_hash, role, is_active FROM technicians WHERE telegram_id = ?",
                    (telegram_id,),
                ).fetchone()
        return Technician(**dict(row)) if row else None

    async def create_technician(self, telegram_id: int, nik: str, name: str, sto: str) -> Technician:
        async with self._lock:
            with self.connection() as conn:
                conn.execute(
                    "INSERT INTO technicians (telegram_id, nik, name, sto, created_at) VALUES (?, ?, ?, ?, ?)",
                    (telegram_id, nik.strip(), name.strip(), sto.strip().upper(), utc_now()),
                )
                row = conn.execute(
                    "SELECT id, telegram_id, nik, name, sto, created_at, password_hash, role, is_active FROM technicians WHERE telegram_id = ?",
                    (telegram_id,),
                ).fetchone()
        return Technician(**dict(row))

    async def update_technician_sto(self, telegram_id: int, sto: str) -> Technician | None:
        normalized_sto = sto.strip().upper()
        async with self._lock:
            with self.connection() as conn:
                conn.execute("UPDATE technicians SET sto = ? WHERE telegram_id = ?", (normalized_sto, telegram_id))
                row = conn.execute(
                    "SELECT id, telegram_id, nik, name, sto, created_at, password_hash, role, is_active FROM technicians WHERE telegram_id = ?",
                    (telegram_id,),
                ).fetchone()
        return Technician(**dict(row)) if row else None

    async def list_technicians(self) -> list[sqlite3.Row]:
        async with self._lock:
            with self.connection() as conn:
                return conn.execute("SELECT * FROM technicians ORDER BY created_at DESC").fetchall()

    async def delete_technician(self, telegram_id: int) -> bool:
        async with self._lock:
            with self.connection() as conn:
                cursor = conn.execute("DELETE FROM technicians WHERE telegram_id = ?", (telegram_id,))
                return cursor.rowcount > 0

    async def set_web_account(self, telegram_id: int, password_hash: str, role: str) -> Technician | None:
        role = role.strip().lower()
        if role not in {"technician", "admin", "superadmin"}:
            raise ValueError("invalid_role")
        async with self._lock:
            with self.connection() as conn:
                conn.execute("UPDATE technicians SET password_hash=?, role=?, is_active=1 WHERE telegram_id=?", (password_hash, role, telegram_id))
                row = conn.execute("SELECT id, telegram_id, nik, name, sto, created_at, password_hash, role, is_active FROM technicians WHERE telegram_id=?", (telegram_id,)).fetchone()
        return Technician(**dict(row)) if row else None

    async def disable_web_account(self, telegram_id: int) -> bool:
        async with self._lock:
            with self.connection() as conn:
                cursor = conn.execute("UPDATE technicians SET is_active=0 WHERE telegram_id=?", (telegram_id,))
                return cursor.rowcount > 0

    async def save_history(self, technician: Technician, kind: str, data: dict[str, Any], content: str) -> int:
        async with self._lock:
            with self.connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO histories (technician_id, telegram_id, kind, ticket_id, service_number, old_sn, new_sn, ont_type, sto, valins_id, content, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (technician.id, technician.telegram_id, kind, data.get("ticket_id"), data.get("service_number") or data.get("internet_number"), data.get("old_sn"), data.get("new_sn"), data.get("ont_type"), data.get("sto"), data.get("valins_id"), content, utc_now()),
                )
                return int(cursor.lastrowid)

    async def list_history(self, telegram_id: int, limit: int = 10) -> list[sqlite3.Row]:
        async with self._lock:
            with self.connection() as conn:
                return conn.execute("SELECT * FROM histories WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?", (telegram_id, limit)).fetchall()

    async def search_history(self, telegram_id: int, query: str) -> list[sqlite3.Row]:
        like = f"%{query}%"
        async with self._lock:
            with self.connection() as conn:
                return conn.execute("SELECT * FROM histories WHERE telegram_id = ? AND (ticket_id LIKE ? OR service_number LIKE ? OR old_sn LIKE ? OR new_sn LIKE ? OR sto LIKE ? OR content LIKE ?) ORDER BY created_at DESC LIMIT 25", (telegram_id, like, like, like, like, like, like)).fetchall()

    async def delete_history(self, telegram_id: int, history_id: int) -> bool:
        async with self._lock:
            with self.connection() as conn:
                cursor = conn.execute("DELETE FROM histories WHERE id = ? AND telegram_id = ?", (history_id, telegram_id))
                return cursor.rowcount > 0

    async def export_history_csv(self, telegram_id: int, output_path: Path) -> Path:
        async with self._lock:
            with self.connection() as conn:
                rows = conn.execute("SELECT id, kind, ticket_id, service_number, old_sn, new_sn, ont_type, sto, valins_id, content, created_at FROM histories WHERE telegram_id = ? ORDER BY created_at DESC", (telegram_id,)).fetchall()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(rows[0].keys() if rows else ["id", "kind", "ticket_id", "service_number", "old_sn", "new_sn", "ont_type", "sto", "valins_id", "content", "created_at"])
            for row in rows:
                writer.writerow([row[key] for key in row.keys()])
        return output_path

    async def save_ocr_log(self, telegram_id: int, technician_id: int | None, image_path: str, raw_text: str, serial_number: str | None, model: str | None, manufacturer: str | None, confidence: float, status: str) -> None:
        async with self._lock:
            with self.connection() as conn:
                conn.execute("INSERT INTO ocr_logs (technician_id, telegram_id, image_path, raw_text, serial_number, model, manufacturer, confidence, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (technician_id, telegram_id, image_path, raw_text, serial_number, model, manufacturer, float(confidence), status, utc_now()))

    async def statistics(self) -> dict[str, int]:
        async with self._lock:
            with self.connection() as conn:
                users = conn.execute("SELECT COUNT(*) AS total FROM technicians").fetchone()["total"]
                histories = conn.execute("SELECT COUNT(*) AS total FROM histories").fetchone()["total"]
                ocr_failures = conn.execute("SELECT COUNT(*) AS total FROM ocr_logs WHERE status != 'success'").fetchone()["total"]
        return {"users": users, "histories": histories, "ocr_failures": ocr_failures}
