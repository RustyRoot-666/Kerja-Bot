from __future__ import annotations

import logging

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import Database
from utils.keyboards import main_menu_keyboard


NIK, NAME = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END

    db: Database = context.application.bot_data["db"]
    technician = await db.get_technician(update.effective_user.id)
    if technician:
        logging.info("Login recognized telegram_id=%s nik=%s", technician.telegram_id, technician.nik)
        await update.message.reply_text(
            f"Selamat datang kembali, {technician.name}.\nSilakan pilih menu.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Selamat datang di Bot Replacement ONT IndiHome.\n\nInput NIK:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NIK


async def input_nik(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NIK
    nik = update.message.text.strip()
    if len(nik) < 4:
        await update.message.reply_text("NIK terlalu pendek. Input NIK yang benar:")
        return NIK
    context.user_data["login_nik"] = nik
    await update.message.reply_text("Input Full Name:")
    return NAME


async def input_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message or not update.message.text:
        return NAME
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("Nama terlalu pendek. Input Full Name:")
        return NAME
    db: Database = context.application.bot_data["db"]
    technician = await db.create_technician(
        telegram_id=update.effective_user.id,
        nik=context.user_data["login_nik"],
        name=name,
    )
    logging.info("New login saved telegram_id=%s nik=%s name=%s", technician.telegram_id, technician.nik, technician.name)
    await update.message.reply_text(
        f"Login berhasil.\nNIK: {technician.nik}\nNama: {technician.name}\n\nSilakan pilih menu.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


def build_login_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NIK: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_nik)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_name)],
        },
        fallbacks=[CommandHandler("start", start)],
        name="login_conversation",
        persistent=False,
    )
