from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from services.auth import require_technician
from services.order_repository import Order, OrderRepository


def repository(context: ContextTypes.DEFAULT_TYPE) -> OrderRepository:
    return context.application.bot_data["orders"]


def is_closed(order: Order) -> bool:
    return order.result.strip().upper() in {"CLOSE", "CLOSED", "SELESAI", "DONE"}


def format_order(order: Order, index: int) -> str:
    marker = "✅" if is_closed(order) else "🟢"
    return (
        f"{index}. {marker} {order.ticket_id or '-'}\n"
        f"   INET : {order.service_number or '-'}\n"
        f"   Nama : {order.customer_name or '-'}\n"
        f"   SN New: {order.new_sn or '-'}"
    )


async def orderanku(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    mode = context.args[0].lower().strip() if context.args else "ringkas"
    stats = await repository(context).technician_stats(technician.name)

    if stats["total"] == 0:
        await update.effective_message.reply_text(
            "Belum ada order yang cocok dengan nama teknisi kamu.\n\n"
            f"Nama akun bot : {technician.name}\n"
            "Pastikan penulisannya sama dengan kolom NAMA PETUGAS di Excel, "
            "kemudian import ulang melalui /importorder."
        )
        return

    if mode in {"ringkas", "menu", "statistik", "stats"}:
        progress = (stats["close"] / stats["total"] * 100) if stats["total"] else 0
        await update.effective_message.reply_text(
            f"📋 ORDER {technician.name.upper()}\n\n"
            f"Total    : {stats['total']}\n"
            f"🟢 OPEN  : {stats['open']}\n"
            f"✅ CLOSE : {stats['close']}\n"
            f"Progress : {progress:.1f}%\n\n"
            "Perintah:\n"
            "/orderanku open\n"
            "/orderanku close\n"
            "/orderanku semua"
        )
        return

    aliases = {
        "open": "open",
        "buka": "open",
        "close": "close",
        "closed": "close",
        "selesai": "close",
        "semua": "all",
        "all": "all",
    }
    status = aliases.get(mode)
    if status is None:
        await update.effective_message.reply_text(
            "Pilihan tidak dikenali. Gunakan /orderanku, /orderanku open, "
            "/orderanku close, atau /orderanku semua."
        )
        return

    orders = await repository(context).list_for_technician(
        technician.name,
        status=status,
        limit=50,
    )
    title = {"open": "🟢 ORDER OPEN", "close": "✅ ORDER CLOSE", "all": "📋 SEMUA ORDER"}[status]

    if not orders:
        await update.effective_message.reply_text(
            f"{title}\n\nTidak ada order pada kategori ini."
        )
        return

    chunks: list[str] = []
    current = f"{title} — {technician.name.upper()}\n\n"
    for index, order in enumerate(orders, start=1):
        item = format_order(order, index) + "\n\n"
        if len(current) + len(item) > 3800:
            chunks.append(current.rstrip())
            current = item
        else:
            current += item
    if current.strip():
        chunks.append(current.rstrip())

    for chunk in chunks:
        await update.effective_message.reply_text(chunk)

    if len(orders) == 50:
        await update.effective_message.reply_text(
            "Ditampilkan maksimal 50 order terbaru."
        )


def build_my_orders_handlers() -> list[CommandHandler]:
    return [CommandHandler("orderanku", orderanku)]
