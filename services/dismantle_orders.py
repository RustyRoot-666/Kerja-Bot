from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SIGNATURE = "OPEN WO DISMANTLING NTE CRASH"

SEED_ORDERS = [
    ("M****", "MULYOREJO TENGAH 1 NO 26 SURABAYA Jalan Ngagel Surabaya 60246 Surabaya Indonesia", "152303278616", "JAWA TIMUR"),
    ("S****", "Mulyorejo Tengah 1/30 Jalan Dokter Ir. Haji Soekarno Surabaya 60115 Surabaya Indonesia", "152303277738", "JAWA TIMUR"),
    ("B*******", "Mulyorejo Tengah Gang V No. 14 Mulyorejo Tengah Gang V Surabaya 00000 Surabaya Indonesia", "152303272481", "JAWA TIMUR"),
    ("D****", "Mulyorejo Tengah Gang V Surabaya", "152303271125", "JAWA TIMUR"),
    ("N****", "mulyorejo tengah gg 1 no 16", "152303272779", "JAWA TIMUR"),
    ("M********", "MULYOREJO TENGAH NO 51 SURABAYA", "152303279918", "JAWA TIMUR"),
    ("*****", "MULYOREJO TENGAH NO.37", "152303277003", "JAWA TIMUR"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema_sync(db_path: Path | str) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dismantle_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                customer_phone TEXT NOT NULL DEFAULT '',
                assigned_nik TEXT NOT NULL DEFAULT '',
                assigned_name TEXT NOT NULL DEFAULT '',
                assigned_username TEXT NOT NULL DEFAULT '',
                assigned_telegram_id INTEGER,
                source_chat_id INTEGER,
                source_message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'OPEN',
                raw_source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_dismantle_assignee ON dismantle_orders(assigned_telegram_id, assigned_nik, status);
            CREATE INDEX IF NOT EXISTS idx_dismantle_completed ON dismantle_orders(completed_at);
            """
        )
        now = _utc_now()
        for name, address, inet, cp in SEED_ORDERS:
            conn.execute(
                """
                INSERT OR IGNORE INTO dismantle_orders (
                    service_number, customer_name, address, customer_phone,
                    assigned_nik, assigned_name, assigned_username,
                    status, raw_source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, '26050138', 'THOMAS GUSTIAN BAGYO', 'ThomasGustian', 'OPEN', 'SEED OSA MYR', ?, ?)
                """,
                (inet, name, address, cp, now, now),
            )


async def initialize_dismantle_orders(db_path: Path | str) -> None:
    await asyncio.to_thread(_ensure_schema_sync, db_path)


def _field(block: str, label: str) -> str:
    m = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", block)
    return (m.group(1).strip() if m else "")


def parse_dismantle_message(text: str) -> list[dict[str, str]]:
    if SIGNATURE not in (text or "").upper():
        return []
    blocks = re.split(rf"(?i)(?={re.escape(SIGNATURE)})", text)
    result: list[dict[str, str]] = []
    for block in blocks:
        if SIGNATURE not in block.upper():
            continue
        service = re.sub(r"\D", "", _field(block, "NO. INET") or _field(block, "NO INET"))
        if not service:
            continue
        petugas = _field(block, "PETUGAS 1")
        nik = ""
        name = ""
        if "|" in petugas:
            nik, name = [part.strip() for part in petugas.split("|", 1)]
        else:
            name = petugas.strip()
        username = _field(block, "USERNAME").lstrip("@").strip()
        result.append(
            {
                "service_number": service,
                "customer_name": _field(block, "NAMA"),
                "address": _field(block, "ALAMAT"),
                "customer_phone": _field(block, "CP PELANGGAN"),
                "assigned_nik": re.sub(r"\D", "", nik),
                "assigned_name": name,
                "assigned_username": username,
                "raw_source": block.strip(),
            }
        )
    return result


def _resolve_telegram_id(conn: sqlite3.Connection, nik: str, username: str) -> int | None:
    if nik:
        row = conn.execute("SELECT telegram_id FROM technicians WHERE TRIM(nik)=? LIMIT 1", (nik,)).fetchone()
        if row:
            return int(row[0])
    if username:
        try:
            row = conn.execute(
                "SELECT telegram_id FROM technician_usernames WHERE LOWER(TRIM(username))=? LIMIT 1",
                (username.lower(),),
            ).fetchone()
            if row:
                return int(row[0])
        except sqlite3.OperationalError:
            pass
    return None


def _save_orders_sync(db_path: Path | str, orders: list[dict[str, str]], chat_id: int | None, message_id: int | None) -> int:
    _ensure_schema_sync(db_path)
    now = _utc_now()
    saved = 0
    with _connect(db_path) as conn:
        for order in orders:
            telegram_id = _resolve_telegram_id(conn, order["assigned_nik"], order["assigned_username"])
            conn.execute(
                """
                INSERT INTO dismantle_orders (
                    service_number, customer_name, address, customer_phone,
                    assigned_nik, assigned_name, assigned_username, assigned_telegram_id,
                    source_chat_id, source_message_id, status, raw_source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
                ON CONFLICT(service_number) DO UPDATE SET
                    customer_name=excluded.customer_name,
                    address=excluded.address,
                    customer_phone=excluded.customer_phone,
                    assigned_nik=excluded.assigned_nik,
                    assigned_name=excluded.assigned_name,
                    assigned_username=excluded.assigned_username,
                    assigned_telegram_id=COALESCE(excluded.assigned_telegram_id, dismantle_orders.assigned_telegram_id),
                    source_chat_id=excluded.source_chat_id,
                    source_message_id=excluded.source_message_id,
                    raw_source=excluded.raw_source,
                    updated_at=excluded.updated_at
                """,
                (
                    order["service_number"], order["customer_name"], order["address"], order["customer_phone"],
                    order["assigned_nik"], order["assigned_name"], order["assigned_username"], telegram_id,
                    chat_id, message_id, order["raw_source"], now, now,
                ),
            )
            saved += 1
    return saved


async def capture_dismantle_order(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    text = message.text or message.caption or ""
    orders = parse_dismantle_message(text)
    if not orders:
        return
    db_path = context.application.bot_data["settings"].database_path
    try:
        saved = await asyncio.to_thread(
            _save_orders_sync,
            db_path,
            orders,
            update.effective_chat.id if update.effective_chat else None,
            message.message_id,
        )
        logging.info("Captured dismantle work orders: %s", saved)
    except Exception:
        logging.exception("Failed to capture dismantle work order")
