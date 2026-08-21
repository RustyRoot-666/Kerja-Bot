from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.report_hourly_progress import (
    _normalized,
    _save_target,
    _target_title,
    _today_progress_rows,
    build_hourly_progress_text,
)


async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if _normalized(chat.title) != _target_title():
        return

    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)

    await asyncio.to_thread(_save_target, db.db_path, chat.id)
    rows = await asyncio.to_thread(
        _today_progress_rows,
        db.db_path,
        now.date().isoformat(),
    )
    await message.reply_text(build_hourly_progress_text(rows, now))
