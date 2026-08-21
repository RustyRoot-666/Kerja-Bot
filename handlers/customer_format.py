from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.order_repository import OrderRepository


def _greeting(hour: int) -> str:
    if 4 <= hour < 11:
        return "Selamat pagi"
    if 11 <= hour < 15:
        return "Selamat siang"
    if 15 <= hour < 18:
        return "Selamat sore"
    return "Selamat malam"


def _dash(value: str) -> str:
    value = str(value or "").strip()
    return value if value else "-"


async def format_customer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    if not chat or chat.type != "private" or not user or not message:
        return

    if not context.args:
        await message.reply_text("Format: /format <INET>\nContoh: /format 152303339740")
        return

    inet = context.args[0].strip()
    if not inet.isdigit():
        await message.reply_text("Nomor INET tidak valid.\nContoh: /format 152303339740")
        return

    db: Database = context.application.bot_data["db"]
    orders: OrderRepository = context.application.bot_data["orders"]

    technician = await db.get_technician(user.id)
    if technician is None:
        await message.reply_text("Silakan daftar/login sebagai teknisi terlebih dahulu.")
        return

    matches = await orders.search(inet, limit=10)
    order = next((item for item in matches if item.service_number.strip() == inet), None)
    if order is None:
        await message.reply_text(f"Order dengan INET {inet} tidak ditemukan.")
        return

    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    greeting = _greeting(datetime.now(tz).hour)

    customer_name = _dash(order.customer_name)
    address = _dash(order.address)
    phone = _dash(order.customer_phone)

    text = (
        f"{greeting} Bapak/Ibu {customer_name}.\n\n"
        f"Perkenalkan, saya {technician.name}, teknisi IndiHome.\n\n"
        "Mohon maaf mengganggu waktunya. Saya mendapat penugasan dari pihak Telkom "
        "untuk melakukan penggantian ONT/Modem pada layanan Bapak/Ibu.\n\n"
        f"No. Internet: {inet}\n"
        f"Alamat: {address}\n"
        f"No. HP: {phone}\n\n"
        "Penggantian ini dilakukan sebagai pembaruan perangkat agar tetap kompatibel "
        "dengan jaringan terbaru dan menjaga kualitas layanan tetap optimal.\n\n"
        "Penggantian ONT/Modem ini tidak dikenakan biaya sama sekali, tidak ada biaya "
        "tambahan di kemudian hari, serta tidak mengubah biaya langganan Bapak/Ibu.\n\n"
        "Apabila Bapak/Ibu berkenan, mohon konfirmasi waktu yang sesuai agar saya dapat "
        "melakukan kunjungan.\n\n"
        "Terima kasih atas perhatian dan kerja sama Bapak/Ibu. 🙏🏼"
    )

    await message.reply_text(text)
