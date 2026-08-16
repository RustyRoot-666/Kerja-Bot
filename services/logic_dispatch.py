from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram.ext import ContextTypes

from database import Database


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _logic_group_id() -> int | None:
    raw = os.getenv("LOGIC_GROUP_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logging.error("LOGIC_GROUP_ID tidak valid: %r", raw)
        return None


def _claim_service(database_path: Path, service_number: str) -> bool:
    conn = sqlite3.connect(database_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logic_config_dispatches (
                service_number TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL
            )
            """
        )
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO logic_config_dispatches (service_number, sent_at)
            VALUES (?, ?)
            """,
            (service_number, _utc_now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _release_service(database_path: Path, service_number: str) -> None:
    conn = sqlite3.connect(database_path)
    try:
        conn.execute(
            "DELETE FROM logic_config_dispatches WHERE service_number = ?",
            (service_number,),
        )
        conn.commit()
    finally:
        conn.close()


async def send_config_to_logic_once(
    context: ContextTypes.DEFAULT_TYPE,
    db: Database,
    service_number: str,
    config_text: str,
) -> bool:
    """Kirim CONFIG murni ke grup Logic sekali untuk setiap NO SERVICE / INET."""
    group_id = _logic_group_id()
    if group_id is None:
        return False

    service = str(service_number or "").strip()
    if not service:
        logging.warning("CONFIG tidak dikirim ke Logic karena NO SERVICE / INET kosong")
        return False

    claimed = await asyncio.to_thread(_claim_service, db.db_path, service)
    if not claimed:
        logging.info("CONFIG INET %s sudah pernah dikirim ke Logic; dilewati", service)
        return False

    try:
        # Grup Logic hanya menerima isi CONFIG, tanpa header/status/pesan tambahan.
        await context.bot.send_message(chat_id=group_id, text=config_text)
        return True
    except Exception:
        # Jika Telegram gagal menerima pesan, izinkan percobaan berikutnya untuk INET yang sama.
        await asyncio.to_thread(_release_service, db.db_path, service)
        logging.exception("Gagal mengirim CONFIG INET %s ke grup Logic", service)
        return False
