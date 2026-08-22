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
from services.report_multi_topic import list_registered_topics


DEFAULT_GROUP_TITLE = "REPORT MANYAR"
TARGET_SETTING_KEY = "report_manyar_progress_group_id"
REPORT_GROUP_SETTING_KEY = "report_group_id"
REPORT_THREAD_SETTING_KEY = "report_thread_id"
AUTO_PROGRESS_START_HOUR = 6
AUTO_PROGRESS_END_HOUR = 23


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
    registered_topics = await asyncio.to_thread(list_registered_topics, db.db_path)
    current_topic = (chat.id, message.message_thread_id) if message.message_thread_id is not None else None
    bound_report_topic = current_topic in registered_topics if current_topic is not None else False

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

    if now.hour < AUTO_PROGRESS_START_HOUR or now.hour > AUTO_PROGRESS_END_HOUR:
        logging.debug(
            "Auto progress REPORT MANYAR dilewati di luar jam aktif: %s",
            now.strftime("%H:%M"),
        )
        return

    rows = await asyncio.to_thread(_today_progress_rows, db.db_path, now.date().isoformat())
    text = build_hourly_progress_text(rows, now)

    topics = await asyncio.to_thread(list_registered_topics, db.db_path)
    if topics:
        sent = 0
        for chat_id, thread_id in topics:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=thread_id,
                    text=text,
                )
                sent += 1
            except Exception:
                logging.exception(
                    "Gagal mengirim auto progress ke REPORT topic chat_id=%s thread_id=%s",
                    chat_id,
                    thread_id,
                )
        logging.info("Auto progress REPORT MANYAR terkirim ke %s/%s topic", sent, len(topics))
        return

    chat_id = await asyncio.to_thread(_get_target, db.db_path)
    if chat_id is None:
        logging.warning(
            "Auto progress REPORT MANYAR belum dikirim: target REPORT MANYAR belum tersimpan."
        )
        return

    await context.bot.send_message(chat_id=chat_id, text=text)
