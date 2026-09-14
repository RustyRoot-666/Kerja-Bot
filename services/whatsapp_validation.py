from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "database/bot.sqlite3"))


def normalize_whatsapp_phone(phone: str) -> str:
    value = re.sub(r"[^0-9]", "", str(phone or ""))
    if value.startswith("0"):
        value = "62" + value[1:]
    return value


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_whatsapp_schema() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_checks (
                phone_number TEXT PRIMARY KEY,
                exists_whatsapp INTEGER NOT NULL CHECK(exists_whatsapp IN (0,1)),
                checked_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'green-api'
            )
        """)
        conn.commit()


def get_whatsapp_check(phone: str) -> dict | None:
    normalized = normalize_whatsapp_phone(phone)
    if not normalized:
        return None
    ensure_whatsapp_schema()
    with _connect() as conn:
        row = conn.execute(
            "SELECT phone_number, exists_whatsapp, checked_at, source "
            "FROM whatsapp_checks WHERE phone_number=?",
            (normalized,),
        ).fetchone()
    return dict(row) if row else None


def check_whatsapp(phone: str) -> dict:
    normalized = normalize_whatsapp_phone(phone)
    if not normalized or normalized in {"0", "62"} or len(normalized) < 8:
        return {"ok": False, "error": "invalid_phone", "phone_number": normalized}

    ensure_whatsapp_schema()
    with _connect() as conn:
        cached = conn.execute(
            "SELECT phone_number, exists_whatsapp, checked_at, source "
            "FROM whatsapp_checks WHERE phone_number=?",
            (normalized,),
        ).fetchone()
    if cached:
        return {
            "ok": True,
            "phone_number": normalized,
            "exists_whatsapp": bool(cached["exists_whatsapp"]),
            "checked_at": cached["checked_at"],
            "cached": True,
        }

    base = (os.getenv("GREEN_API_URL") or "").rstrip("/")
    instance = os.getenv("GREEN_API_INSTANCE") or ""
    token = os.getenv("GREEN_API_TOKEN") or ""
    if not base or not instance or not token:
        return {"ok": False, "error": "green_api_not_configured"}

    url = f"{base}/waInstance{instance}/checkWhatsapp/{token}"
    try:
        response = requests.post(
            url,
            json={"phoneNumber": int(normalized)},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {"ok": False, "error": "green_api_request_failed", "message": str(exc)}

    exists = bool(payload.get("existsWhatsapp"))
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO whatsapp_checks "
            "(phone_number, exists_whatsapp, checked_at, source) VALUES (?, ?, ?, ?)",
            (normalized, int(exists), checked_at, "green-api"),
        )
        conn.commit()

    return {
        "ok": True,
        "phone_number": normalized,
        "exists_whatsapp": exists,
        "checked_at": checked_at,
        "cached": False,
    }
