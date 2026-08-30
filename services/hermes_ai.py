from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from handlers.my_orders import (
    address_sort_key,
    classify_area,
    displayed_package,
    displayed_sheet_value,
    sheet_status_bucket,
    technician_sheet_orders,
)
from services.google_sheet_reference import get_reference_statuses
from services.manja_reminder import _latest_manja

BRIDGE_URL = "http://127.0.0.1:8765/ask"
MAX_ORDERS_IN_CONTEXT = 60


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _rx_number(value: object) -> float | None:
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _query_jagir_rows(database_path, telegram_id: int, nik: str, name: str) -> list[dict]:
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "jagir_work_orders" not in tables:
            return []
        username = ""
        if "technician_usernames" in tables:
            row = conn.execute(
                "SELECT username FROM technician_usernames WHERE telegram_id=?",
                (telegram_id,),
            ).fetchone()
            if row:
                username = str(row["username"] or "").strip().lower()
        rows = conn.execute(
            """
            SELECT * FROM jagir_work_orders
            WHERE UPPER(TRIM(status))='OPEN'
              AND (
                    assigned_telegram_id=?
                 OR (? != '' AND TRIM(assigned_nik)=?)
                 OR (? != '' AND UPPER(TRIM(assigned_name))=?)
                 OR (? != '' AND LOWER(TRIM(assigned_username))=?)
              )
            ORDER BY address, service_number
            """,
            (telegram_id, nik, nik, _norm(name), _norm(name), username, username),
        ).fetchall()
    return [dict(row) for row in rows]


def _query_report_rows(database_path, nik: str, name: str, tz_name: str) -> dict:
    now = datetime.now(ZoneInfo(tz_name))
    today = now.date().isoformat()
    since = (now.date() - timedelta(days=6)).isoformat()
    result = {"today": 0, "last_7_days": 0, "recent": []}
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "report_group_orders" not in tables:
            return result
        where = "TRIM(technician_nik)=?" if nik else "UPPER(TRIM(technician_name))=?"
        key = nik if nik else _norm(name)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(report_group_orders)")}
        date_col = "message_date" if "message_date" in cols else ("created_at" if "created_at" in cols else "")
        if date_col:
            result["today"] = conn.execute(
                f"SELECT COUNT(*) FROM report_group_orders WHERE {where} AND substr({date_col},1,10)=?",
                (key, today),
            ).fetchone()[0]
            result["last_7_days"] = conn.execute(
                f"SELECT COUNT(*) FROM report_group_orders WHERE {where} AND substr({date_col},1,10)>=?",
                (key, since),
            ).fetchone()[0]
            selected = ["service_number"]
            if "ticket_id" in cols:
                selected.append("ticket_id")
            selected.append(date_col)
            rows = conn.execute(
                f"SELECT {', '.join(selected)} FROM report_group_orders WHERE {where} ORDER BY {date_col} DESC LIMIT 20",
                (key,),
            ).fetchall()
            result["recent"] = [dict(row) for row in rows]
        else:
            result["last_7_days"] = conn.execute(
                f"SELECT COUNT(*) FROM report_group_orders WHERE {where}",
                (key,),
            ).fetchone()[0]
    return result


def _bridge_call_sync(prompt: str) -> str:
    body = json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        BRIDGE_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=130) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Hermes bridge HTTP {exc.code}: {detail[-500:]}") from exc
    except OSError as exc:
        raise RuntimeError("Hermes bridge belum aktif di VPS.") from exc
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("message") or payload.get("error") or "Hermes gagal menjawab"))
    return str(payload.get("answer") or "").strip()


async def _build_context(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> tuple[str, str]:
    user = update.effective_user
    if user is None:
        raise RuntimeError("Akun Telegram tidak ditemukan.")
    db = context.application.bot_data["db"]
    technician = await db.get_technician(user.id)
    if technician is None:
        raise RuntimeError("Akun belum terdaftar sebagai teknisi.")

    settings = context.application.bot_data["settings"]
    sheet_rows = []
    try:
        statuses = await get_reference_statuses(force=False, raise_errors=True)
        refs = technician_sheet_orders(statuses, technician.name)
        for ref in refs:
            if sheet_status_bucket(ref) != "open":
                continue
            sheet_rows.append({
                "source": "ORDER SHEET",
                "sto": "MYR",
                "area": classify_area(ref.address),
                "service_number": ref.service_number,
                "ticket_id": ref.ticket_id or "MANUAL",
                "customer_name": ref.customer_name or "-",
                "customer_phone": ref.customer_phone or "-",
                "address": ref.address or "-",
                "package": displayed_package(ref),
                "onu_rx": displayed_sheet_value(ref.onu_rx),
                "rca": displayed_sheet_value(ref.rca),
            })
        sheet_rows.sort(key=lambda row: address_sort_key(row["address"]))
    except Exception:
        sheet_rows = []

    jagir_raw = await asyncio.to_thread(
        _query_jagir_rows,
        db.db_path,
        user.id,
        technician.nik,
        technician.name,
    )
    jagir_rows = []
    for row in jagir_raw:
        jagir_rows.append({
            "source": "WORK ORDER JAGIR",
            "sto": "JGR",
            "area": "JAGIR",
            "service_number": str(row.get("service_number") or ""),
            "ticket_id": str(row.get("ticket_id") or "MANUAL"),
            "customer_name": str(row.get("customer_name") or "-"),
            "customer_phone": str(row.get("customer_phone") or "-"),
            "address": str(row.get("address") or "-"),
            "package": str(row.get("package") or "-"),
            "onu_rx": str(row.get("onu_rx") or "-"),
            "rca": str(row.get("description") or "-"),
            "odp": str(row.get("odp_name") or "-"),
        })

    manja_raw = await asyncio.to_thread(_latest_manja, db.db_path)
    manja_rows = []
    for row in manja_raw:
        if int(row.get("telegram_id") or 0) != user.id:
            continue
        manja_rows.append({
            "source": str(row.get("source") or "MANJA"),
            "service_number": str(row.get("service_number") or ""),
            "appointment_date": str(row.get("appointment_date") or ""),
            "appointment_time": str(row.get("appointment_time") or ""),
            "note": str(row.get("note") or "-") or "-",
            "updated_at": str(row.get("updated_at") or ""),
        })
    manja_rows.sort(
        key=lambda row: (
            row["appointment_date"] or "9999-12-31",
            row["appointment_time"] or "23:59",
            row["service_number"],
        )
    )

    reports = await asyncio.to_thread(
        _query_report_rows,
        db.db_path,
        technician.nik,
        technician.name,
        settings.timezone,
    )

    all_open = sheet_rows + jagir_rows
    exact_services = re.findall(r"\b\d{8,}\b", question)
    if exact_services:
        wanted = set(exact_services)
        relevant = [row for row in all_open if row["service_number"] in wanted]
        others = [row for row in all_open if row["service_number"] not in wanted]
        all_open = relevant + others
        manja_rows.sort(key=lambda row: (row["service_number"] not in wanted, row["appointment_date"] or "9999-12-31"))
    worst = sorted(
        [row for row in all_open if _rx_number(row.get("onu_rx")) is not None],
        key=lambda row: _rx_number(row.get("onu_rx")) or 0,
    )[:10]

    snapshot = {
        "technician": {
            "telegram_id": user.id,
            "name": technician.name,
            "nik": technician.nik,
            "default_sto": getattr(technician, "sto", "") or "",
        },
        "rules": {
            "ORDER SHEET": "MANYAR / MYR only",
            "WORK ORDER JAGIR": "JAGIR / JGR only",
            "MANJA": "active appointment/follow-up state for this technician",
            "mode": "READ ONLY",
        },
        "open_summary": {
            "total": len(all_open),
            "myr": len(sheet_rows),
            "jgr": len(jagir_rows),
        },
        "manja_summary": {
            "active": len(manja_rows),
            "with_appointment": sum(1 for row in manja_rows if row["appointment_date"]),
            "without_appointment": sum(1 for row in manja_rows if not row["appointment_date"]),
        },
        "active_manja": manja_rows[:30],
        "open_orders": all_open[:MAX_ORDERS_IN_CONTEXT],
        "worst_rx_preview": worst,
        "report_summary": reports,
    }
    # Compact JSON keeps the user question safely inside the bridge prompt limit.
    return technician.name, json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None or chat.type != "private":
        return
    question = " ".join(context.args).strip()
    if not question:
        await message.reply_text(
            "Gunakan /ai diikuti pertanyaan.\n\n"
            "Contoh:\n"
            "/ai wo saya\n"
            "/ai cari inet 152310205282\n"
            "/ai mana WO JAGIR saya yang RX paling jelek?\n"
            "/ai berapa order saya yang masih OPEN?\n"
            "/ai MANJA saya apa saja?\n"
            "/ai kapan janji MANJA saya berikutnya?\n"
            "/ai ringkas pekerjaan saya hari ini\n\n"
            "Boleh juga bertanya bebas tentang data pekerjaanmu yang tersedia di Kerja BOT."
        )
        return

    status = await message.reply_text("🤖 Hermes sedang membaca data pekerjaanmu...")
    try:
        technician_name, context_text = await _build_context(update, context, question)
        # Put the actual user request before the potentially long dataset. The bridge
        # has a prompt-size guard, so the request must never be the part that gets cut.
        prompt = f"""Kamu adalah Hermes, AI internal Kerja BOT untuk teknisi lapangan.

PERTANYAAN USER YANG WAJIB KAMU JAWAB LANGSUNG:
{question}

Nama teknisi: {technician_name}

ATURAN KERAS:
- Jawab pertanyaan user di atas, jangan hanya memperkenalkan diri atau bertanya balik.
- Gunakan hanya DATA KERJA di bawah untuk fakta pekerjaan, INET, tiket, alamat, RX, status, jumlah, teknisi, STO, MANJA, dan jadwal janji.
- Jangan mengarang data yang tidak ada.
- ORDER SHEET = MANYAR/MYR. WORK ORDER JAGIR = JAGIR/JGR.
- active_manja berisi status MANJA aktif milik teknisi, termasuk jadwal janji jika tersedia.
- Mode READ-ONLY: jangan mengaku mengubah database, menutup WO, membuat tiket, membuat reminder, mengirim pesan, atau menjalankan aksi.
- Jika user meminta daftar WO/order/MANJA, tampilkan data yang relevan langsung. Jika terlalu banyak, ringkas total lalu tampilkan yang paling relevan.
- Jika user meminta jumlah, hitung dari summary/data yang tersedia.
- Jika user meminta janji berikutnya, utamakan MANJA dengan appointment_date/time terdekat yang masih tersedia.
- Jika user meminta RX terburuk, angka lebih negatif berarti lebih buruk (-24 lebih buruk daripada -17).
- Jika data tidak tersedia, katakan data tidak tersedia. Jangan menanyakan kembali apa yang mau dicek jika pertanyaan sudah jelas.

DATA KERJA:
{context_text}
"""
        answer = await asyncio.to_thread(_bridge_call_sync, prompt)
        if not answer:
            answer = "Hermes tidak mengembalikan jawaban."
        chunks = [answer[i:i + 3900] for i in range(0, len(answer), 3900)]
        await status.edit_text(chunks[0])
        for chunk in chunks[1:]:
            await message.reply_text(chunk)
    except Exception as exc:
        await status.edit_text(f"❌ Hermes belum bisa digunakan: {exc}")
