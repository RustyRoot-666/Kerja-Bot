from __future__ import annotations

import re

from telegram import Update
from telegram.ext import ContextTypes

from database import Database, Technician


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


def _format_assign(inets: list[str], technician: Technician) -> str:
    return "\n".join([
        *inets,
        f"moban assign lensa chat, {technician.name} ({technician.nik})",
    ])


async def handle_assign_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    if not chat or not message or not user or chat.type not in {"group", "supergroup"}:
        return
    if not _is_assign_group(chat.title):
        return

    text = (message.text or message.caption or "").strip()
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0] if text else ""

    db: Database = context.application.bot_data["db"]
    technician = await db.get_technician(user.id)

    if command == "/assign":
        if technician is None:
            await message.reply_text("❌ Akun teknisi belum terdaftar di bot.")
            return

        inets = _extract_inets(text[len(text.split(maxsplit=1)[0]):])
        if not inets and message.reply_to_message:
            replied = message.reply_to_message.text or message.reply_to_message.caption or ""
            inets = _extract_inets(replied)

        if inets:
            context.user_data.pop("assign_waiting_chat_id", None)
            await message.reply_text(_format_assign(inets, technician))
            return

        context.user_data["assign_waiting_chat_id"] = chat.id
        await message.reply_text("Kirim nomor INET yang mau diminta assign. Bisa lebih dari satu, satu baris satu INET.")
        return

    if context.user_data.get("assign_waiting_chat_id") != chat.id:
        return

    if technician is None:
        context.user_data.pop("assign_waiting_chat_id", None)
        return

    inets = _extract_inets(text)
    if not inets:
        await message.reply_text("❌ Nomor INET tidak ditemukan. Kirim nomor INET 10-15 digit.")
        return

    context.user_data.pop("assign_waiting_chat_id", None)
    await message.reply_text(_format_assign(inets, technician))
