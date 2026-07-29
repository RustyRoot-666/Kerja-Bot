from __future__ import annotations

import re
from html import escape

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes

from services.auth import require_technician
from services.google_sheet_reference import (
    ReferenceStatus,
    get_reference_statuses,
    is_reference_closed,
    normalize_ticket,
    status_for_order,
)
from services.order_repository import Order, OrderRepository


CLOSED_STATUSES = {"CLOSE", "CLOSED", "SELESAI", "DONE"}
SEPARATOR = "━━━━━━━━━━━━━━━"


def repository(context: ContextTypes.DEFAULT_TYPE) -> OrderRepository:
    return context.application.bot_data["orders"]


def is_database_closed(order: Order) -> bool:
    return order.result.strip().upper() in CLOSED_STATUSES


def is_effectively_closed(order: Order, reference: ReferenceStatus | None) -> bool:
    return is_database_closed(order) or is_reference_closed(reference)


def displayed_ticket(order: Order, reference: ReferenceStatus | None) -> str:
    """Prioritas tiket: TIKET valid, lalu INSERA TODAY dari referensi, lalu MANUAL."""
    database_ticket = normalize_ticket(order.ticket_id)
    reference_ticket = normalize_ticket(reference.ticket_id if reference else "")
    return database_ticket or reference_ticket or "MANUAL"


def displayed_service(order: Order, reference: ReferenceStatus | None) -> str:
    return order.service_number or (reference.service_number if reference else "") or "-"


def displayed_new_sn(order: Order, reference: ReferenceStatus | None) -> str:
    return order.new_sn or (reference.new_sn if reference else "") or "-"


def displayed_value(order_value: str, reference_value: str = "") -> str:
    return order_value.strip() or reference_value.strip() or "-"


def displayed_package(reference: ReferenceStatus | None) -> str:
    value = (reference.package if reference else "").strip()
    if not value:
        return "-"
    if re.fullmatch(r"\d+(?:[.,]\d+)?", value):
        return f"{value} Mbps"
    return value


def code(value: str) -> str:
    """Render nilai sebagai teks monospace yang dapat diketuk untuk disalin di Telegram."""
    return f"<code>{escape(value)}</code>"


def orderanku_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🟢 Orderanku Open", "🔴 Orderanku Close"],
            ["📋 Semua Orderanku"],
            ["↩️ Kembali"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Pilih kategori orderanku",
    )


def format_order(
    order: Order,
    index: int,
    reference: ReferenceStatus | None,
    category: str,
) -> str:
    ticket = displayed_ticket(order, reference)
    service = displayed_service(order, reference)
    name = displayed_value(
        order.customer_name,
        reference.customer_name if reference else "",
    )

    if category == "open":
        phone = displayed_value(
            order.customer_phone,
            reference.customer_phone if reference else "",
        )
        address = displayed_value(
            order.address,
            reference.address if reference else "",
        )
        package = displayed_package(reference)
        return (
            f"{index}. {escape(name)}\n"
            f"{SEPARATOR}\n"
            f"🎫 Tiket : {code(ticket)}\n"
            f"🌐 INET  : {code(service)}\n"
            f"📞 CP    : {code(phone)}\n"
            f"⚡ Paket : {escape(package)}\n"
            f"🏠 Alamat:\n"
            f"{escape(address)}"
        )

    if category == "close":
        return (
            f"{index}. {escape(name)}\n"
            f"{SEPARATOR}\n"
            f"🎫 Tiket : {code(ticket)}\n"
            f"🌐 INET  : {code(service)}\n"
            f"🔢 SN New: {code(displayed_new_sn(order, reference))}"
        )

    status_label = (
        reference.status
        if is_reference_closed(reference)
        else order.result.strip().upper() if is_database_closed(order)
        else "OPEN"
    )
    return (
        f"{index}. {escape(name)}\n"
        f"{SEPARATOR}\n"
        f"Status   : {escape(status_label)}\n"
        f"🎫 Tiket : {code(ticket)}\n"
        f"🌐 INET  : {code(service)}\n"
        f"🔢 SN New: {code(displayed_new_sn(order, reference))}"
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
            f"🔴 CLOSE : {closed_count}\n"
            f"Progress : {progress:.1f}%\n\n"
            "Silakan pilih kategori order di menu bawah.",
            reply_markup=orderanku_menu(),
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
            "/orderanku close, atau /orderanku semua.",
            reply_markup=orderanku_menu(),
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
        "close": "🔴 ORDER CLOSE/DONE",
        "all": "📋 SEMUA ORDER",
    }[status]

    if not orders:
        await update.effective_message.reply_text(
            f"{title} — {technician.name.upper()}\n\nTidak ada order pada kategori ini.",
            reply_markup=orderanku_menu(),
        )
        return

    chunks: list[str] = []
    current = f"{title} — {escape(technician.name.upper())}\n\n"
    for index, order in enumerate(orders, start=1):
        item = format_order(order, index, references.get(order.id), status) + "\n\n"
        if len(current) + len(item) > 3800:
            chunks.append(current.rstrip())
            current = item
        else:
            current += item
    if current.strip():
        chunks.append(current.rstrip())

    for chunk in chunks:
        await update.effective_message.reply_text(
            chunk,
            parse_mode="HTML",
            reply_markup=orderanku_menu(),
        )

    if matching_count > 50:
        await update.effective_message.reply_text(
            f"Ditampilkan 50 dari {matching_count} order.",
            reply_markup=orderanku_menu(),
        )


def build_my_orders_handlers() -> list[CommandHandler]:
    return [CommandHandler("orderanku", orderanku)]