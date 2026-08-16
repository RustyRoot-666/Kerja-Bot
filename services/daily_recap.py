from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.auth import require_technician


DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def _format_date(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def _period_bounds(day: date) -> tuple[date, date]:
    # Periode kerja selalu Jumat sampai Kamis.
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    end = start + timedelta(days=6)
    return start, end


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def _local_day_bounds(day: date, tz: ZoneInfo) -> tuple[str, str]:
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return _utc_iso(start_local), _utc_iso(end_local)


def _local_period_bounds(start_day: date, end_day: date, tz: ZoneInfo) -> tuple[str, str]:
    start_local = datetime.combine(start_day, time.min, tzinfo=tz)
    end_local = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)
    return _utc_iso(start_local), _utc_iso(end_local)


async def _history_rows(
    db: Database,
    telegram_id: int,
    start_utc: str,
    end_utc: str,
):
    async with db._lock:
        with db.connection() as conn:
            return conn.execute(
                """
                SELECT kind, ticket_id, service_number, created_at
                FROM histories
                WHERE telegram_id = ?
                  AND created_at >= ?
                  AND created_at < ?
                ORDER BY created_at ASC
                """,
                (telegram_id, start_utc, end_utc),
            ).fetchall()


def _service_key(row) -> str:
    service = (row["service_number"] or "").strip()
    if service and service != "-":
        return service
    ticket = (row["ticket_id"] or "").strip()
    if ticket and ticket != "-":
        return f"TICKET:{ticket}"
    return f"ROW:{row['created_at']}:{row['kind']}"


def _summarize(rows) -> tuple[list[tuple[str, str]], dict[str, int]]:
    jobs: dict[str, tuple[str, str]] = {}
    by_kind: dict[str, set[str]] = {"CONFIG": set(), "REPORT": set(), "STO": set()}

    for row in rows:
        key = _service_key(row)
        service = (row["service_number"] or "-").strip() or "-"
        ticket = (row["ticket_id"] or "-").strip() or "-"
        jobs.setdefault(key, (service, ticket))
        if row["kind"] in by_kind:
            by_kind[row["kind"]].add(key)

    counts = {kind: len(keys) for kind, keys in by_kind.items()}
    counts["TOTAL"] = len(jobs)
    return list(jobs.values()), counts


async def build_recap_text(
    db: Database,
    telegram_id: int,
    technician_name: str,
    day: date,
    timezone_name: str,
) -> str:
    tz = ZoneInfo(timezone_name)
    day_start, day_end = _local_day_bounds(day, tz)
    period_start, period_end = _period_bounds(day)
    period_start_utc, period_end_utc = _local_period_bounds(period_start, min(day, period_end), tz)

    daily_rows = await _history_rows(db, telegram_id, day_start, day_end)
    period_rows = await _history_rows(db, telegram_id, period_start_utc, period_end_utc)

    daily_jobs, daily_counts = _summarize(daily_rows)
    _, period_counts = _summarize(period_rows)

    lines = [
        "📊 REKAP PEKERJAAN HARIAN",
        f"📅 {DAY_NAMES[day.weekday()]}, {_format_date(day)}",
        f"👷 {technician_name}",
        "",
        f"Total pekerjaan hari ini : {daily_counts['TOTAL']}",
    ]

    if daily_jobs:
        lines.append("")
        for index, (service, ticket) in enumerate(daily_jobs, start=1):
            lines.append(f"{index}. {service} | {ticket}")

    lines.extend(
        [
            "",
            f"CONFIG : {daily_counts['CONFIG']}",
            f"REPORT : {daily_counts['REPORT']}",
            f"STO    : {daily_counts['STO']}",
            "",
            f"📆 Periode: {_format_date(period_start)} - {_format_date(period_end)}",
            f"Total periode berjalan : {period_counts['TOTAL']}",
        ]
    )
    return "\n".join(lines)


async def send_daily_recaps(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()

    technicians = await db.list_technicians()
    for technician in technicians:
        telegram_id = int(technician["telegram_id"])
        try:
            text = await build_recap_text(
                db,
                telegram_id,
                technician["name"],
                today,
                settings.timezone,
            )
            await context.bot.send_message(chat_id=telegram_id, text=text)
        except Exception:
            logging.exception("Gagal mengirim rekap harian ke telegram_id=%s", telegram_id)


async def recap_harian_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    text = await build_recap_text(
        db,
        technician.telegram_id,
        technician.name,
        today,
        settings.timezone,
    )
    await update.effective_message.reply_text(text)
