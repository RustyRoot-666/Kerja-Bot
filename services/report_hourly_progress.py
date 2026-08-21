from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database


DEFAULT_GROUP_TITLE = "REPORT MANYAR"
TARGET_SETTING_KEY = "report_manyar_progress_group_id"

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _normalized(value: str | None) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _target_title() -> str:
    return _normalized(os.getenv("STO_RECAP_GROUP_TITLE", DEFAULT_GROUP_TITLE))


def _period_bounds(day: date) -> tuple[date, date]:
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    return start, start + timedelta(days=6)


def _format_date(day: date) -> str:
    return f"{day.day} {MONTH_NAMES[day.month - 1]} {day.year}"


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


def _get_target(database_path: Path) -> int | None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_settings_table(conn)
        row = conn.execute(
            "SELECT value FROM report_bot_settings WHERE key = ?",
            (TARGET_SETTING_KEY,),
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


def _leaderboard_rows(database_path: Path, period_start: date) -> list[tuple[str, int]]:
    conn = sqlite3.connect(database_path)
    try:
        rows = conn.execute(
            """
            SELECT MAX(technician_name) AS technician_name, COUNT(*) AS total
            FROM report_group_orders
            WHERE period_start = ?
            GROUP BY technician_nik
            ORDER BY total DESC, UPPER(MAX(technician_name)) ASC
            """,
            (period_start.isoformat(),),
        ).fetchall()
        return [(str(name), int(total)) for name, total in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


async def remember_report_manyar_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat
    if not chat or chat.type not in {"group", "supergroup"}:
        return
    if _normalized(chat.title) != _target_title():
        return

    db: Database = context.application.bot_data["db"]
    await asyncio.to_thread(_save_target, db.db_path, chat.id)


def build_hourly_progress_text(rows: list[tuple[str, int]], now: datetime) -> str:
    period_start, period_end = _period_bounds(now.date())
    total = sum(count for _, count in rows)
    lines = [
        "📈 AUTO PROGRESS REPORT MANYAR",
        f"🕐 Update: {DAY_NAMES[now.weekday()]}, {_format_date(now.date())} {now.strftime('%H:%M')}",
        f"📅 Periode: {_format_date(period_start)} - {_format_date(period_end)}",
        "",
    ]

    if rows:
        width = max(len(name.upper()) for name, _ in rows)
        for index, (name, count) in enumerate(rows, start=1):
            lines.append(f"{index}. {name.upper().ljust(width)} : {count} order")
        lines.extend(["", f"📊 TOTAL PROGRESS : {total} order"])
    else:
        lines.append("Belum ada order yang terekap pada periode ini.")

    return "\n".join(lines)


async def send_hourly_report_progress(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    period_start, _ = _period_bounds(now.date())

    chat_id = await asyncio.to_thread(_get_target, db.db_path)
    if chat_id is None:
        logging.warning(
            "Auto progress REPORT MANYAR belum dikirim: bot belum melihat pesan di grup REPORT MANYAR."
        )
        return

    rows = await asyncio.to_thread(_leaderboard_rows, db.db_path, period_start)
    await context.bot.send_message(
        chat_id=chat_id,
        text=build_hourly_progress_text(rows, now),
    )
