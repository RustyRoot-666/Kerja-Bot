from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from database import Database

REPORT_GROUP_SETTING_KEY = "report_group_id"
REPORT_THREAD_SETTING_KEY = "report_thread_id"
NO_SERVICE_RE = re.compile(r"(?:NO\s*SERVICE|INET)\s*:\s*(\d{6,})", re.IGNORECASE)
TECH_RE = re.compile(
    r"(?:NIK\s*NAMA\s*TEKNISI|TEKNISI)\s*:\s*(\d+)\s*\|\s*([^\n\r]+)",
    re.IGNORECASE,
)


def _stored_setting(database_path: Path, key: str) -> int | None:
    conn = sqlite3.connect(database_path)
    try:
        row = conn.execute(
            "SELECT value FROM report_bot_settings WHERE key = ?",
            (key,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()

    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


async def acknowledge_report_sto(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        return
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0]
    if command != "/sto":
        return

    service_match = NO_SERVICE_RE.search(text)
    tech_match = TECH_RE.search(text)
    if not service_match or not tech_match:
        return

    db: Database = context.application.bot_data["db"]
    group_id = await asyncio.to_thread(
        _stored_setting,
        db.db_path,
        REPORT_GROUP_SETTING_KEY,
    )
    thread_id = await asyncio.to_thread(
        _stored_setting,
        db.db_path,
        REPORT_THREAD_SETTING_KEY,
    )

    if group_id is None or thread_id is None:
        return
    if chat.id != group_id or message.message_thread_id != thread_id:
        return

    service_number = service_match.group(1).strip()
    technician_name = tech_match.group(2).strip().upper()
    await message.reply_text(
        "✅ REPORT SUDAH TERSIMPAN\n"
        f"🌐 INET : {service_number}\n"
        f"👷 TEKNISI : {technician_name}"
    )
