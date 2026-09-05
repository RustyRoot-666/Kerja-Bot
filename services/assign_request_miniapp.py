from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import services.assign_request as base
from database import Database


_original_today_technician_inets = base._today_technician_inets


async def _today_miniapp_draft_inets(
    db: Database,
    telegram_id: int,
    timezone_name: str,
) -> list[str]:
    """Return INET started from Mini App today for this technician."""
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    start_day = start_local.date().isoformat()
    end_day = end_local.date().isoformat()

    async with db._lock:
        with db.connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='miniapp_workflow_drafts'"
            ).fetchone()
            if not exists:
                return []
            rows = conn.execute(
                """
                SELECT service_number, MAX(updated_at) AS last_updated
                FROM miniapp_workflow_drafts
                WHERE telegram_id = ?
                  AND service_number IS NOT NULL
                  AND TRIM(service_number) NOT IN ('', '-')
                  AND substr(updated_at, 1, 10) >= ?
                  AND substr(updated_at, 1, 10) < ?
                GROUP BY service_number
                ORDER BY last_updated ASC
                """,
                (telegram_id, start_day, end_day),
            ).fetchall()

    result: list[str] = []
    for row in rows:
        service = str(row["service_number"] or "").strip()
        if base.INET_RE.fullmatch(service):
            result.append(service)
    return result


async def _today_miniapp_completed_inets(
    db: Database,
    telegram_id: int,
    timezone_name: str,
) -> list[str]:
    """Return INETs completed from Mini App today for this technician."""
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    start_day = start_local.date().isoformat()
    end_day = end_local.date().isoformat()

    async with db._lock:
        with db.connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='miniapp_completed_workflows'"
            ).fetchone()
            if not exists:
                return []
            rows = conn.execute(
                """
                SELECT service_number, MAX(completed_at) AS completed_at
                FROM miniapp_completed_workflows
                WHERE telegram_id = ?
                  AND service_number IS NOT NULL
                  AND TRIM(service_number) NOT IN ('', '-')
                  AND substr(completed_at, 1, 10) >= ?
                  AND substr(completed_at, 1, 10) < ?
                GROUP BY service_number
                ORDER BY completed_at ASC
                """,
                (telegram_id, start_day, end_day),
            ).fetchall()

    result: list[str] = []
    for row in rows:
        service = str(row["service_number"] or "").strip()
        if base.INET_RE.fullmatch(service):
            result.append(service)
    return result


async def _today_technician_inets_with_miniapp(
    db: Database,
    telegram_id: int,
    timezone_name: str,
) -> list[str]:
    """Merge history, Mini App drafts and Mini App completed workflows."""
    history_inets = await _original_today_technician_inets(
        db,
        telegram_id,
        timezone_name,
    )
    draft_inets = await _today_miniapp_draft_inets(
        db,
        telegram_id,
        timezone_name,
    )
    completed_inets = await _today_miniapp_completed_inets(
        db,
        telegram_id,
        timezone_name,
    )

    seen: set[str] = set()
    merged: list[str] = []
    for inet in [*history_inets, *draft_inets, *completed_inets]:
        if inet not in seen:
            seen.add(inet)
            merged.append(inet)
    return merged


# The existing /assign handler calls this module-level helper at runtime.
# Replacing it preserves the existing formatting, group checks and validation
# while making Mini App completed workflows visible in today's orders.
base._today_technician_inets = _today_technician_inets_with_miniapp
handle_assign_message = base.handle_assign_message
