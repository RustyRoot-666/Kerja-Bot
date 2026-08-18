from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database


ASSIGN_GROUP_CANONICAL = "REPLACEMENT NTE MANYAR"
INET_RE = re.compile(r"\b\d{10,15}\b")


def _canonical_title(value: str | None) -> str:
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).split())


def _is_assign_group(title: str | None) -> bool:
    return _canonical_title(title) == ASSIGN_GROUP_CANONICAL


def _extract_inets(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for inet in INET_RE.findall(text or ""):
        if inet not in seen:
            seen.add(inet)
            result.append(inet)
    return result


def _format_assign(inets: list[str], technician_name: str, technician_nik: str) -> str:
    footer = f"moban assign lensa chat, {technician_name.upper()} ({technician_nik})"
    return "\n".join([*inets, footer])


def _format_tiket(inets: list[str]) -> str:
    return "\n".join([
        "#REQOPENTIKET",
        "STO: MYR",
        "",
        "NOMER INET:",
        *inets,
        "moban create tiket",
    ])


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def _ensure_seen_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assign_group_seen (
            chat_id INTEGER NOT NULL,
            service_number TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            source_message_id INTEGER,
            PRIMARY KEY (chat_id, service_number)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_group_seen (
            chat_id INTEGER NOT NULL,
            service_number TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            source_message_id INTEGER,
            PRIMARY KEY (chat_id, service_number)
        )
        """
    )


async def _remember_inets(
    db: Database,
    table: str,
    chat_id: int,
    inets: list[str],
    message_id: int | None,
) -> None:
    if not inets:
        return
    if table not in {"assign_group_seen", "ticket_group_seen"}:
        raise ValueError("invalid seen table")
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    async with db._lock:
        with db.connection() as conn:
            _ensure_seen_tables(conn)
            conn.executemany(
                f"""
                INSERT OR IGNORE INTO {table} (
                    chat_id, service_number, first_seen_at, source_message_id
                ) VALUES (?, ?, ?, ?)
                """,
                [(chat_id, inet, now, message_id) for inet in inets],
            )


async def _already_seen(db: Database, table: str, chat_id: int, inets: list[str]) -> set[str]:
    if not inets:
        return set()
    if table not in {"assign_group_seen", "ticket_group_seen"}:
        raise ValueError("invalid seen table")
    placeholders = ",".join("?" for _ in inets)
    async with db._lock:
        with db.connection() as conn:
            _ensure_seen_tables(conn)
            rows = conn.execute(
                f"""
                SELECT service_number
                FROM {table}
                WHERE chat_id = ?
                  AND service_number IN ({placeholders})
                """,
                [chat_id, *inets],
            ).fetchall()
    return {str(row["service_number"]) for row in rows}


async def _today_technician_inets(
    db: Database,
    telegram_id: int,
    timezone_name: str,
) -> list[str]:
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = _utc_iso(start_local)
    end_utc = _utc_iso(end_local)

    async with db._lock:
        with db.connection() as conn:
            rows = conn.execute(
                """
                SELECT service_number, MIN(created_at) AS first_created
                FROM histories
                WHERE telegram_id = ?
                  AND created_at >= ?
                  AND created_at < ?
                  AND service_number IS NOT NULL
                  AND TRIM(service_number) NOT IN ('', '-')
                GROUP BY service_number
                ORDER BY first_created ASC
                """,
                (telegram_id, start_utc, end_utc),
            ).fetchall()

    result: list[str] = []
    for row in rows:
        service_number = str(row["service_number"] or "").strip()
        if INET_RE.fullmatch(service_number):
            result.append(service_number)
    return result


async def handle_assign_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    if not chat or not message or not user or chat.type not in {"group", "supergroup"}:
        return
    if not _is_assign_group(chat.title):
        return

    db: Database = context.application.bot_data["db"]
    text = (message.text or message.caption or "").strip()
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0] if text else ""
    visible_inets = _extract_inets(text)

    # Semua INET yang terlihat di grup dianggap sudah pernah muncul untuk /assign.
    if command not in {"/assign", "/tiket"} and visible_inets:
        await _remember_inets(db, "assign_group_seen", chat.id, visible_inets, message.message_id)

        # Untuk /tiket, hanya pesan yang memang berbentuk req open tiket yang dianggap sudah direquest.
        normalized = text.upper()
        if "#REQOPENTIKET" in normalized or "MOBAN CREATE TIKET" in normalized:
            await _remember_inets(db, "ticket_group_seen", chat.id, visible_inets, message.message_id)
        return

    if command not in {"/assign", "/tiket"}:
        return

    technician = await db.get_technician(user.id)
    if technician is None:
        await message.reply_text("❌ Akun teknisi belum terdaftar di bot.")
        return

    settings = context.application.bot_data["settings"]
    today_inets = await _today_technician_inets(db, technician.telegram_id, settings.timezone)
    if not today_inets:
        await message.reply_text("Belum ada INET pekerjaan hari ini yang tercatat di bot.")
        return

    if command == "/assign":
        seen = await _already_seen(db, "assign_group_seen", chat.id, today_inets)
        missing = [inet for inet in today_inets if inet not in seen]
        if not missing:
            await message.reply_text("✅ Semua INET pekerjaan hari ini sudah ada di grup.")
            return

        sent = await message.reply_text(_format_assign(missing, technician.name, technician.nik))
        await _remember_inets(db, "assign_group_seen", chat.id, missing, sent.message_id)
        return

    seen = await _already_seen(db, "ticket_group_seen", chat.id, today_inets)
    missing = [inet for inet in today_inets if inet not in seen]
    if not missing:
        await message.reply_text("✅ Semua INET pekerjaan hari ini sudah pernah direquest open tiket.")
        return

    sent = await message.reply_text(_format_tiket(missing))
    await _remember_inets(db, "ticket_group_seen", chat.id, missing, sent.message_id)
