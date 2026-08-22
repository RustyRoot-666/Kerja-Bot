from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database import Database
from services.report_leaderboard import (
    NO_SERVICE_RE,
    REPORT_GROUP_SETTING_KEY,
    REPORT_THREAD_SETTING_KEY,
    TECH_RE,
    _period_bounds,
    _save_report_target,
    _store_order,
    _stored_setting,
    _target_group_title,
    _technician_daily_total,
    _technician_period_total,
    _normalized_title,
)

MAX_REPORT_TOPICS = 2
BIND_COMMANDS = {"/setreport", "/setreportmanyar"}


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure_topic_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_topics (
            chat_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, thread_id)
        )
        """
    )


def _seed_legacy_target(database_path: Path) -> None:
    group_id = _stored_setting(database_path, REPORT_GROUP_SETTING_KEY)
    thread_id = _stored_setting(database_path, REPORT_THREAD_SETTING_KEY)
    if group_id is None or thread_id is None:
        return
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO report_topics (chat_id, thread_id, added_at)
            VALUES (?, ?, ?)
            """,
            (group_id, thread_id, _utc_now()),
        )


def _add_topic(database_path: Path, chat_id: int, thread_id: int) -> tuple[str, int]:
    _seed_legacy_target(database_path)
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        exists = conn.execute(
            "SELECT 1 FROM report_topics WHERE chat_id = ? AND thread_id = ?",
            (chat_id, thread_id),
        ).fetchone()
        if exists:
            total = int(conn.execute("SELECT COUNT(*) FROM report_topics").fetchone()[0])
            return "EXISTS", total

        total = int(conn.execute("SELECT COUNT(*) FROM report_topics").fetchone()[0])
        if total >= MAX_REPORT_TOPICS:
            return "FULL", total

        conn.execute(
            "INSERT INTO report_topics (chat_id, thread_id, added_at) VALUES (?, ?, ?)",
            (chat_id, thread_id, _utc_now()),
        )
        total += 1
        return "ADDED", total


def _is_registered_topic(database_path: Path, chat_id: int, thread_id: int) -> bool:
    _seed_legacy_target(database_path)
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        row = conn.execute(
            "SELECT 1 FROM report_topics WHERE chat_id = ? AND thread_id = ?",
            (chat_id, thread_id),
        ).fetchone()
        return row is not None


def _topic_count(database_path: Path) -> int:
    _seed_legacy_target(database_path)
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        return int(conn.execute("SELECT COUNT(*) FROM report_topics").fetchone()[0])


async def handle_multi_report_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a second REPORT topic and accept /sto there without double-counting the primary."""
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if _normalized_title(chat.title) != _target_group_title():
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        return
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0]
    db: Database = context.application.bot_data["db"]

    if command in BIND_COMMANDS:
        thread_id = message.message_thread_id
        if thread_id is None:
            await message.reply_text("❌ /setreport harus dikirim dari dalam topic REPORT.")
            raise ApplicationHandlerStop

        action, total = await asyncio.to_thread(_add_topic, db.db_path, chat.id, thread_id)
        primary_group = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_GROUP_SETTING_KEY)
        primary_thread = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_THREAD_SETTING_KEY)
        if primary_group is None or primary_thread is None:
            await asyncio.to_thread(_save_report_target, db.db_path, chat.id, thread_id)

        if action == "FULL":
            await message.reply_text(
                f"❌ Maksimal {MAX_REPORT_TOPICS} topic REPORT. Saat ini sudah terdaftar {total} topic."
            )
        elif action == "EXISTS":
            await message.reply_text(
                f"ℹ️ Topic ini sudah terdaftar sebagai REPORT.\n📌 TOTAL TOPIC : {total}/{MAX_REPORT_TOPICS}"
            )
        else:
            await message.reply_text(
                "✅ TOPIC REPORT BERHASIL DITAMBAHKAN\n"
                f"📌 TOTAL TOPIC : {total}/{MAX_REPORT_TOPICS}"
            )
        logging.info("REPORT topic bind: chat_id=%s thread_id=%s action=%s total=%s", chat.id, thread_id, action, total)
        raise ApplicationHandlerStop

    if command != "/sto" or message.message_thread_id is None:
        return

    registered = await asyncio.to_thread(
        _is_registered_topic,
        db.db_path,
        chat.id,
        message.message_thread_id,
    )
    if not registered:
        return

    # Primary topic tetap diproses handler lama agar tidak terjadi double-processing.
    primary_group = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_GROUP_SETTING_KEY)
    primary_thread = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_THREAD_SETTING_KEY)
    if chat.id == primary_group and message.message_thread_id == primary_thread:
        return

    service_match = NO_SERVICE_RE.search(text)
    tech_match = TECH_RE.search(text)
    if not service_match or not tech_match:
        await message.reply_text(
            "❌ REPORT belum bisa disimpan. Pastikan /sto berisi NO SERVICE dan NIK NAMA TEKNISI."
        )
        raise ApplicationHandlerStop

    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    message_dt = message.date.astimezone(tz)
    period_start, _ = _period_bounds(message_dt.date())
    service_number = service_match.group(1).strip()
    technician_nik = tech_match.group(1).strip()
    technician_name = tech_match.group(2).strip()

    action = await asyncio.to_thread(
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
    total_today = await asyncio.to_thread(
        _technician_daily_total,
        db.db_path,
        message_dt.date(),
        technician_nik,
    )
    total_period = await asyncio.to_thread(
        _technician_period_total,
        db.db_path,
        period_start,
        technician_nik,
    )

    if action == "INSERTED":
        status = "✅ REPORT SUDAH TERSIMPAN"
    elif action == "UPDATED":
        status = "♻️ REPORT DIPERBARUI"
    else:
        status = "ℹ️ REPORT SUDAH TERSIMPAN"

    await message.reply_text(
        f"{status}\n"
        f"🌐 INET : {service_number}\n"
        f"👷 TEKNISI : {technician_name.upper()}\n"
        f"📊 HARI INI : {total_today} order\n"
        f"📊 TOTAL PERIODE : {total_period} order"
    )
    logging.info(
        "Secondary REPORT /sto: inet=%s teknisi=%s action=%s chat_id=%s thread_id=%s topics=%s",
        service_number,
        technician_nik,
        action,
        chat.id,
        message.message_thread_id,
        await asyncio.to_thread(_topic_count, db.db_path),
    )
    raise ApplicationHandlerStop
