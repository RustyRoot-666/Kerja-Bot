from __future__ import annotations

import base64
import hashlib
import logging
import secrets

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from database import Database

ROLES = {"technician", "admin", "superadmin"}


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 310000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def temporary_password(length: int = 12) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def webaccount_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message:
        return
    settings = context.application.bot_data["settings"]
    if update.effective_user.id not in settings.admin_ids:
        await update.effective_message.reply_text("⛔ Anda tidak memiliki akses mengatur akun Website.")
        return

    args = context.args or []
    if not args or not args[0].isdigit():
        await update.effective_message.reply_text(
            "Format:\n/webaccount <telegram_id> [technician|admin|superadmin]\n\n"
            "Contoh:\n/webaccount 1189386983 technician"
        )
        return

    telegram_id = int(args[0])
    role = (args[1].strip().lower() if len(args) > 1 else "technician")
    if role not in ROLES:
        await update.effective_message.reply_text("Role tidak valid. Pilih: technician, admin, atau superadmin.")
        return

    db: Database = context.application.bot_data["db"]
    technician = await db.get_technician(telegram_id)
    if not technician:
        await update.effective_message.reply_text("❌ Telegram ID tersebut belum terdaftar sebagai teknisi. Minta akun menjalankan /start terlebih dahulu.")
        return

    password = temporary_password()
    saved = await db.set_web_account(telegram_id, password_hash(password), role)
    if not saved:
        await update.effective_message.reply_text("❌ Gagal membuat akun Website.")
        return

    try:
        await context.bot.send_message(
            chat_id=telegram_id,
            text=(
                "🌐 AKUN WEBSITE KERJA-BOT AKTIF\n\n"
                f"Nama: {saved.name}\n"
                f"NIK: {saved.nik}\n"
                f"Role: {saved.role}\n\n"
                f"Password sementara: {password}\n\n"
                "Gunakan NIK + password tersebut untuk masuk ke Website Kerja-Bot. "
                "Jangan bagikan password kepada orang lain."
            ),
        )
    except Exception:
        logging.exception("Failed to deliver web account credentials to telegram_id=%s", telegram_id)
        await update.effective_message.reply_text(
            f"⚠️ Akun dibuat, tetapi password gagal dikirim ke Telegram {telegram_id}. "
            "Reset ulang setelah koneksi Telegram normal."
        )
        return

    await update.effective_message.reply_text(
        "✅ Akun Website berhasil dibuat.\n\n"
        f"Nama: {saved.name}\nNIK: {saved.nik}\nRole: {saved.role}\n"
        "Kredensial sudah dikirim langsung ke Telegram teknisi."
    )


async def webaccount_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message:
        return
    settings = context.application.bot_data["settings"]
    if update.effective_user.id not in settings.admin_ids:
        await update.effective_message.reply_text("⛔ Anda tidak memiliki akses reset akun Website.")
        return
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.effective_message.reply_text("Format: /webaccount_reset <telegram_id>")
        return
    telegram_id = int(args[0])
    db: Database = context.application.bot_data["db"]
    technician = await db.get_technician(telegram_id)
    if not technician:
        await update.effective_message.reply_text("❌ Teknisi tidak ditemukan.")
        return
    password = temporary_password()
    saved = await db.set_web_account(telegram_id, password_hash(password), technician.role)
    if not saved:
        await update.effective_message.reply_text("❌ Gagal reset password.")
        return
    try:
        await context.bot.send_message(chat_id=telegram_id, text=f"🔐 Password Website Kerja-Bot Anda telah di-reset.\n\nNIK: {saved.nik}\nPassword sementara: {password}\nRole: {saved.role}\n\nJangan bagikan password ini.")
    except Exception:
        logging.exception("Failed to deliver reset password telegram_id=%s", telegram_id)
        await update.effective_message.reply_text("⚠️ Password sudah di-reset, tetapi gagal dikirim ke Telegram teknisi.")
        return
    await update.effective_message.reply_text(f"✅ Password Website {saved.name} berhasil di-reset dan dikirim ke Telegram teknisi.")


async def webconfirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return
    data = str(query.data or "")
    if not data.startswith("webconfirm:"):
        return
    token = data.split(":", 1)[1].strip()
    db: Database = context.application.bot_data["db"]
    # Keep confirmation state in the same SQLite database used by the PHP website.
    from pathlib import Path
    import sqlite3
    from datetime import datetime, timezone

    def confirm() -> bool:
        with sqlite3.connect(db.db_path) as conn:
            row = conn.execute("SELECT id,telegram_id,status,expires_at FROM web_link_requests WHERE token_hash=? LIMIT 1", [hashlib.sha256(token.encode()).hexdigest()]).fetchone()
            if not row or int(row[1]) != query.from_user.id or row[2] != "pending":
                return False
            try:
                expires = datetime.fromisoformat(str(row[3]).replace("Z", "+00:00"))
            except ValueError:
                return False
            if expires <= datetime.now(timezone.utc).replace(tzinfo=timezone.utc):
                return False
            conn.execute("UPDATE web_link_requests SET status='confirmed', confirmed_at=? WHERE id=?", [datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), row[0]])
            conn.commit()
            return True

    ok = await context.application.run_in_executor(None, confirm)
    if ok:
        await query.answer("Akun Telegram berhasil diverifikasi.", show_alert=True)
        await query.edit_message_text("✅ Telegram berhasil dikonfirmasi untuk Website Kerja-Bot. Silakan kembali ke Website dan lanjutkan proses.")
    else:
        await query.answer("Permintaan sudah tidak valid atau sudah kedaluwarsa.", show_alert=True)


def build_web_auth_handlers():
    return [
        CommandHandler("webaccount", webaccount_command),
        CommandHandler("webaccount_reset", webaccount_reset_command),
        CallbackQueryHandler(webconfirm_callback, pattern=r"^webconfirm:"),
    ]
