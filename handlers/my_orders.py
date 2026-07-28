from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from services.auth import require_technician
from services.google_sheet_reference import (
    ReferenceStatus,
    get_reference_statuses,
    is_reference_closed,
    status_for_order,
)
from services.order_repository import Order, OrderRepository


CLOSED_STATUSES = {"CLOSE", "CLOSED", "SELESAI", "DONE"}


def repository(context: ContextTypes.DEFAULT_TYPE) -> OrderRepository:
    return context.application.bot_data["orders"]


def is_database_closed(order: Order) -> bool:
    return order.result.strip().upper() in CLOSED_STATUSES


def is_effectively_closed(order: Order, reference: ReferenceStatus | None) -> bool:
    return is_database_closed(order) or is_reference_closed(reference)


def format_order(
    order: Order,
    index: int,
    reference: ReferenceStatus | None,
) -> str:
    if is_reference_closed(reference):
        status_label = f"✅ {reference.status} (Google Sheets)"
    elif is_database_closed(order):
        status_label = f"✅ {order.result.strip().upper() or 'CLOSE'}"
    else:
        status_label = "🟢 OPEN"

    displayed_ticket = order.ticket_id or (reference.ticket_id if reference else "") or "-"
    ticket_source = (
        " (Google Sheets)"
        if not order.ticket_id and reference and reference.ticket_id
        else ""
    )

    displayed_service = (
        order.service_number or (reference.service_number if reference else "") or "-"
    )
    service_source = (
        " (Google Sheets)"
        if not order.service_number and reference and reference.service_number
        else ""
    )

    displayed_new_sn = order.new_sn or (reference.new_sn if reference else "") or "-"
    sn_source = (
        " (Google Sheets)"
        if not order.new_sn and reference and reference.new_sn
        else ""
    )

    return (
        f"{index}. {status_label}\n"
        f"   Tiket : {displayed_ticket}{ticket_source}\n"
        f"   INET  : {displayed_service}{service_source}\n"
        f"   Nama  : {order.customer_name or '-'}\n"
        f"   SN New: {displayed_new_sn}{sn_source}"
    )


async def orderanku(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    mode = context.args[0].lower().strip() if context.args else "ringkas"
    all_orders = await repository(context).list_for_technician(
        technician.name,
        status="all",
        limit=5000,
    )

    if not all_orders:
        await update.effective_message.reply_text(
            "Belum ada order yang cocok dengan nama teknisi kamu.\n\n"
            f"Nama akun bot : {technician.name}\n"
            "Pastikan penulisannya sama dengan kolom NAMA PETUGAS di Excel, "
            "kemudian import ulang melalui /importorder."
        )
        return

    reference_statuses = await get_reference_statuses()
    references = {
        order.id: status_for_order(
            reference_statuses,
            order.ticket_id,
            order.service_number,
        )
        for order in all_orders
    }

    closed_count = sum(
        1
        for order in all_orders
        if is_effectively_closed(order, references.get(order.id))
    )
    total_count = len(all_orders)
    open_count = total_count - closed_count

    if mode in {"ringkas", "menu", "statistik", "stats"}:
        progress = (closed_count / total_count * 100) if total_count else 0
        await update.effective_message.reply_text(
            f"📋 ORDER {technician.name.upper()}\n\n"
            f"Total    : {total_count}\n"
            f"🟢 OPEN  : {open_count}\n"
            f"✅ CLOSE : {closed_count}\n"
            f"Progress : {progress:.1f}%\n\n"
            "Status, tiket, dan SN ONT NEW juga dibaca dari referensi Google Sheets. "
            "Bot tidak mengubah Google Sheets maupun database dari data tersebut.\n\n"
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
        "done": "close",
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

    if status == "open":
        orders = [
            order
            for order in all_orders
            if not is_effectively_closed(order, references.get(order.id))
        ]
    elif status == "close":
        orders = [
            order
            for order in all_orders
            if is_effectively_closed(order, references.get(order.id))
        ]
    else:
        orders = all_orders

    matching_count = len(orders)
    orders = orders[:50]
    title = {
        "open": "🟢 ORDER OPEN",
        "close": "✅ ORDER CLOSE/DONE",
        "all": "📋 SEMUA ORDER",
    }[status]

    if not orders:
        await update.effective_message.reply_text(
            f"{title}\n\nTidak ada order pada kategori ini."
        )
        return

    chunks: list[str] = []
    current = f"{title} — {technician.name.upper()}\n\n"
    for index, order in enumerate(orders, start=1):
        item = format_order(order, index, references.get(order.id)) + "\n\n"
        if len(current) + len(item) > 3800:
            chunks.append(current.rstrip())
            current = item
        else:
            current += item
    if current.strip():
        chunks.append(current.rstrip())

    for chunk in chunks:
        await update.effective_message.reply_text(chunk)

    if matching_count > 50:
        await update.effective_message.reply_text(
            f"Ditampilkan 50 dari {matching_count} order."
        )


def build_my_orders_handlers() -> list[CommandHandler]:
    return [CommandHandler("orderanku", orderanku)]
