from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database


DEFAULT_REPORT_GROUP_TITLE = "REPORT MANYAR"
REPORT_GROUP_SETTING_KEY = "report_group_id"

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

NO_SERVICE_RE = re.compile(r"(?:NO\s*SERVICE|INET)\s*:\s*(\d{6,})", re.IGNORECASE)
TECH_RE = re.compile(
    r"(?:NIK\s*NAMA\s*TEKNISI|TEKNISI)\s*:\s*(\d+)\s*\|\s*([^\n\r]+)",
    re.IGNORECASE,
)


def _normalized_title(value: str | None) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _target_group_title() -> str:
    return _normalized_title(os.getenv("REPORT_GROUP_TITLE", DEFAULT_REPORT_GROUP_TITLE))


def _period_bounds(day: date) -> tuple[date, date]:
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    end = start + timedelta(days=6)
    return start, end


def _format_date(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_group_orders (
            service_number TEXT NOT NULL,
            period_start TEXT NOT NULL,
            technician_nik TEXT NOT NULL,
            technician_name TEXT NOT NULL,
            message_date TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER,
            created_at TEXT NOT NULL,
            PRIMARY KEY (service_number, period_start)
        )
        """
    )


def _save_group_id(database_path: Path, group_id: int) -> None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO report_bot_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (REPORT_GROUP_SETTING_KEY, str(group_id), _utc_now()),
        )
        conn.commit()
    finally:
        conn.close()


def _stored_group_id(database_path: Path) -> int | None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT value FROM report_bot_settings WHERE key = ?",
            (REPORT_GROUP_SETTING_KEY,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()

    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        logging.error("report_group_id tersimpan tidak valid: %r", row[0])
        return None


def _store_order(
    database_path: Path,
    service_number: str,
    period_start: date,
    technician_nik: str,
    technician_name: str,
    message_date: datetime,
    chat_id: int,
    message_id: int | None,
) -> bool:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO report_group_orders (
                service_number, period_start, technician_nik, technician_name,
                message_date, chat_id, message_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_number,
                period_start.isoformat(),
                technician_nik,
                technician_name.strip(),
                message_date.isoformat(),
                chat_id,
                message_id,
                _utc_now(),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _leaderboard_rows(database_path: Path, period_start: date) -> list[tuple[str, int]]:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
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
        conn.commit()
        return [(str(name), int(total)) for name, total in rows]
    finally:
        conn.close()


async def capture_report_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if _normalized_title(chat.title) != _target_group_title():
        return

    db: Database = context.application.bot_data["db"]
    await asyncio.to_thread(_save_group_id, db.db_path, chat.id)

    text = message.text or message.caption or ""
    service_match = NO_SERVICE_RE.search(text)
    tech_match = TECH_RE.search(text)
    if not service_match or not tech_match:
        return

    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    message_dt = message.date.astimezone(tz)
    period_start, _ = _period_bounds(message_dt.date())

    service_number = service_match.group(1).strip()
    technician_nik = tech_match.group(1).strip()
    technician_name = tech_match.group(2).strip()

    inserted = await asyncio.to_thread(
        _store_order,
        db.db_path,
        service_number,
        period_start,
        technician_nik,
        technician_name,
        message_dt,
        chat.id,
        message.message_id,
    )
    if inserted:
        logging.info(
            "Report order captured: inet=%s teknisi=%s (%s) periode=%s",
            service_number,
            technician_name,
            technician_nik,
            period_start,
        )


def build_leaderboard_text(rows: list[tuple[str, int]], today: date) -> str:
    period_start, period_end = _period_bounds(today)
    lines = [
        "🏆 LEADERBOARD PERIODE BERJALAN",
        f"📆 {_format_date(period_start)} - {_format_date(period_end)}",
        f"📅 Update: {DAY_NAMES[today.weekday()]}, {_format_date(today)}",
        "",
    ]

    if rows:
        width = max(len(name.upper()) for name, _ in rows)
        for index, (name, total) in enumerate(rows, start=1):
            lines.append(f"{index}. {name.upper().ljust(width)} : {total} order")
    else:
        lines.append("Belum ada order yang tercatat pada periode ini.")

    lines.append("")
    remaining = (period_end - today).days
    if remaining <= 0:
        lines.append("🏁 Periode selesai. Terima kasih atas kerja keras semuanya!")
    else:
        lines.append(f"🔥 Masih ada {remaining} hari lagi. Posisi masih bisa berubah!")
    return "\n".join(lines)


async def send_report_leaderboard(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    period_start, _ = _period_bounds(today)

    group_id = await asyncio.to_thread(_stored_group_id, db.db_path)
    if group_id is None:
        logging.warning("Leaderboard belum dikirim: grup %s belum terdeteksi", _target_group_title())
        return

    rows = await asyncio.to_thread(_leaderboard_rows, db.db_path, period_start)
    text = build_leaderboard_text(rows, today)
    await context.bot.send_message(chat_id=group_id, text=text)
