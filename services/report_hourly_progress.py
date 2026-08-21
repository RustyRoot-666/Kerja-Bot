from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database


DEFAULT_GROUP_TITLE = "REPORT MANYAR"
TARGET_SETTING_KEY = "report_manyar_progress_group_id"
REPORT_GROUP_SETTING_KEY = "report_group_id"
REPORT_THREAD_SETTING_KEY = "report_thread_id"


def _normalized(value: str | None) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _target_title() -> str:
    return _normalized(os.getenv("STO_RECAP_GROUP_TITLE", DEFAULT_GROUP_TITLE))


def _ensure_settings_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _save_target(database_path: Path, chat_id: int) -> None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_settings_table(conn)
        now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        conn.execute(
            """
            INSERT INTO report_bot_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (TARGET_SETTING_KEY, str(chat_id), now),
        )
        conn.commit()
    finally:
        conn.close()


def _get_setting(database_path: Path, key: str) -> int | None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_settings_table(conn)
        row = conn.execute(
            "SELECT value FROM report_bot_settings WHERE key = ?",
            (key,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _get_target(database_path: Path) -> int | None:
    return _get_setting(database_path, TARGET_SETTING_KEY)


def _today_progress_rows(
    database_path: Path,
    day_iso: str,
) -> list[tuple[str, int, int]]:
    """Return technician name, CLOSE count and UPDATE count for one local day."""
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        try:
            close_rows = conn.execute(
                """
                SELECT technician_nik,
                       MAX(technician_name) AS technician_name,
                       COUNT(DISTINCT service_number) AS total
                FROM report_group_orders
                WHERE substr(message_date, 1, 10) = ?
                GROUP BY technician_nik
                """,
                (day_iso,),
            ).fetchall()
        except sqlite3.OperationalError:
            close_rows = []

        try:
            update_rows = conn.execute(
                """
                SELECT telegram_id,
                       MAX(technician_name) AS technician_name,
                       COUNT(DISTINCT service_number) AS total
                FROM kendala_updates
                WHERE substr(created_at, 1, 10) = ?
                  AND UPPER(TRIM(status)) = 'UPDATE'
                GROUP BY telegram_id
                """,
                (day_iso,),
            ).fetchall()
        except sqlite3.OperationalError:
            update_rows = []

        combined: dict[str, dict[str, object]] = {}

        for row in close_rows:
            name = str(row["technician_name"] or "-").strip().upper()
            key = _normalized(name)
            combined[key] = {"name": name, "close": int(row["total"] or 0), "update": 0}

        for row in update_rows:
            name = str(row["technician_name"] or "-").strip().upper()
            key = _normalized(name)
            item = combined.setdefault(key, {"name": name, "close": 0, "update": 0})
            item["update"] = int(row["total"] or 0)

        rows = [
            (str(item["name"]), int(item["close"]), int(item["update"]))
            for item in combined.values()
        ]
        rows.sort(key=lambda item: (-(item[1] + item[2]), -item[1], item[0]))
        return rows
    finally:
        conn.close()


def build_hourly_progress_text(
    rows: list[tuple[str, int, int]],
    now: datetime,
) -> str:
    total_close = sum(close for _, close, _ in rows)
    total_update = sum(update for _, _, update in rows)
    total_reports = total_close + total_update

    lines = ["📊 PROGRESS MANYAR", ""]

    if rows:
        for index, (name, close, update) in enumerate(rows):
            if index:
                lines.append("")
            lines.extend(
                [
                    f"👨 {name.upper()}",
                    f"✅ Close : {close}",
                    f"🔄 Update : {update}",
                ]
            )
    else:
        lines.append("Belum ada laporan hari ini.")

    lines.extend(
        [
            "",
            "============================",
            f"📌 TOTAL CLOSE : {total_close}",
            f"📌 TOTAL UPDATE : {total_update}",
            f"📌 TOTAL LAPORAN : {total_reports}",
            "",
            f"⏰ Auto update {now.strftime('%H:%M')} WIB",
        ]
    )
    return "\n".join(lines)


async def remember_report_manyar_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return

    db: Database = context.application.bot_data["db"]
    text = (message.text or message.caption or "").strip()
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0] if text else ""

    standalone_report_group = _normalized(chat.title) == _target_title()
    bound_group_id = await asyncio.to_thread(_get_setting, db.db_path, REPORT_GROUP_SETTING_KEY)
    bound_thread_id = await asyncio.to_thread(_get_setting, db.db_path, REPORT_THREAD_SETTING_KEY)
    bound_report_topic = (
        bound_group_id is not None
        and bound_thread_id is not None
        and chat.id == bound_group_id
        and message.message_thread_id == bound_thread_id
    )

    if not standalone_report_group and not bound_report_topic:
        return

    await asyncio.to_thread(_save_target, db.db_path, chat.id)

    if command != "/progres":
        return

    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    rows = await asyncio.to_thread(
        _today_progress_rows,
        db.db_path,
        now.date().isoformat(),
    )
    await message.reply_text(build_hourly_progress_text(rows, now))


async def send_hourly_report_progress(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)

    bound_group_id = await asyncio.to_thread(_get_setting, db.db_path, REPORT_GROUP_SETTING_KEY)
    bound_thread_id = await asyncio.to_thread(_get_setting, db.db_path, REPORT_THREAD_SETTING_KEY)

    chat_id = bound_group_id
    thread_id = bound_thread_id
    if chat_id is None:
        chat_id = await asyncio.to_thread(_get_target, db.db_path)
        thread_id = None

    if chat_id is None:
        logging.warning(
            "Auto progress REPORT MANYAR belum dikirim: target REPORT MANYAR belum tersimpan."
        )
        return

    rows = await asyncio.to_thread(_today_progress_rows, db.db_path, now.date().isoformat())
    send_kwargs = {
        "chat_id": chat_id,
        "text": build_hourly_progress_text(rows, now),
    }
    if thread_id is not None:
        send_kwargs["message_thread_id"] = thread_id

    await context.bot.send_message(**send_kwargs)
