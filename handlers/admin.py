from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from database import Database


def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.application.bot_data["settings"]
    return bool(update.effective_user and update.effective_user.id in settings.admin_ids)


async def admin_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if is_admin(update, context):
        return True
    if update.effective_chat:
        await update.effective_chat.send_message("Perintah admin saja.")
    return False


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    db: Database = context.application.bot_data["db"]
    rows = await db.list_technicians()
    if not rows:
        await update.effective_chat.send_message("Belum ada user.")
        return
    lines = ["Daftar user:"]
    for row in rows[:50]:
        lines.append(f"{row['telegram_id']} | {row['nik']} | {row['name']} | {row['created_at']}")
    await update.effective_chat.send_message("\n".join(lines))


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.effective_chat.send_message("Format: /admin_broadcast pesan")
        return
    db: Database = context.application.bot_data["db"]
    rows = await db.list_technicians()
    success = 0
    for row in rows:
        try:
            await context.bot.send_message(chat_id=row["telegram_id"], text=text)
            success += 1
        except Exception:
            continue
    await update.effective_chat.send_message(f"Broadcast terkirim ke {success} user.")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    db: Database = context.application.bot_data["db"]
    stats = await db.statistics()
    await update.effective_chat.send_message(
        f"Statistik\n\nUsers: {stats['users']}\nGenerated: {stats['histories']}\nOCR failures: {stats['ocr_failures']}"
    )


async def admin_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_chat.send_message("Format: /admin_delete_user telegram_id")
        return
    db: Database = context.application.bot_data["db"]
    deleted = await db.delete_technician(int(context.args[0]))
    await update.effective_chat.send_message("User dihapus." if deleted else "User tidak ditemukan.")


async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    db_path: Path = context.application.bot_data["settings"].database_path
    backup_path = db_path.parent / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
    shutil.copy2(db_path, backup_path)
    await update.effective_chat.send_document(
        document=backup_path.open("rb"),
        filename=backup_path.name,
        caption="Backup database.",
    )


def build_admin_handlers() -> list[CommandHandler]:
    return [
        CommandHandler("admin_users", admin_users),
        CommandHandler("admin_broadcast", admin_broadcast),
        CommandHandler("admin_stats", admin_stats),
        CommandHandler("admin_delete_user", admin_delete_user),
        CommandHandler("admin_backup", admin_backup),
    ]
