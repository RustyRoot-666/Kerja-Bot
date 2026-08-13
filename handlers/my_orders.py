from __future__ import annotations

import re
from collections import defaultdict
from html import escape

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from services.auth import require_technician
from services.google_sheet_reference import (
    ReferenceStatus,
    get_reference_statuses,
    is_reference_closed,
    normalize,
    normalize_ticket,
    status_for_order,
    unique_reference_orders,
)
from services.order_repository import Order, OrderRepository
from utils.keyboards import main_menu_keyboard


CLOSED_STATUSES = {"CLOSE", "CLOSED", "SELESAI", "DONE", "COMPLETED"}
UPDATE_STATUSES = {"UPDATE", "UPDATED", "PROGRESS", "ON PROGRESS", "PENDING"}
REJECT_STATUSES = {"MENOLAK", "TOLAK", "REJECT", "REJECTED", "DITOLAK"}
SEPARATOR = "━━━━━━━━━━━━━━━"
BACK_TO_MAIN = "⬅️ Kembali ke Menu Utama"
COPY_CALLBACK_PATTERN = r"^copy_(inet|cp):"
AREA_CALLBACK_PATTERN = r"^myarea:"

# Alias khusus diletakkan sebelum fallback otomatis. Tambahkan pola baru di sini
# jika ditemukan variasi alamat yang perlu digabung ke satu cluster.
AREA_ALIASES: dict[str, tuple[str, ...]] = {
    "KERTAJAYA": (
        "KERTAJAYA INDAH TIMUR",
        "KERTAJAYA INDAH",
        "KERTAJAYA",
    ),
    "MULYOREJO": ("MULYOREJO",),
    "KEPUTIH": ("KEPUTIH",),
}

ADDRESS_PREFIXES = {
    "JL", "JLN", "JALAN", "GG", "GANG", "PERUM", "PERUMAHAN",
    "KOMP", "KOMPLEK", "KOMPLEKS", "KP", "KAMPUNG",
}


def repository(context: ContextTypes.DEFAULT_TYPE) -> OrderRepository:
    return context.application.bot_data["orders"]


def is_database_closed(order: Order) -> bool:
    return order.result.strip().upper() in CLOSED_STATUSES


def is_effectively_closed(order: Order, reference: ReferenceStatus | None) -> bool:
    return is_database_closed(order) or is_reference_closed(reference)


def displayed_ticket(order: Order, reference: ReferenceStatus | None) -> str:
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


def orderanku_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["/orderanku", "/orderanku open"],
            ["/orderanku close", "/orderanku semua"],
            [BACK_TO_MAIN],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Pilih kategori order",
    )


def copy_buttons(service: str, phone: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("📋 Salin INET", callback_data=f"copy_inet:{service}"),
            InlineKeyboardButton("📋 Salin CP", callback_data=f"copy_cp:{phone}"),
        ]]
    )


def normalize_address(address: str) -> str:
    text = normalize(address)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_area(address: str) -> str:
    """Kelompokkan alamat ke nama area yang stabil dan mudah dibaca."""
    text = normalize_address(address)
    if not text:
        return "LAINNYA"

    for area, aliases in AREA_ALIASES.items():
        if any(alias in text for alias in aliases):
            return area

    # Fallback: ambil kata lokasi pertama yang bermakna. Dengan cara ini
    # 'KERTAJAYA INDAH ...' tetap menjadi KERTAJAYA meski belum ada alias.
    tokens = text.split()
    while tokens and (tokens[0] in ADDRESS_PREFIXES or tokens[0].isdigit()):
        tokens.pop(0)
    for token in tokens:
        if token in ADDRESS_PREFIXES or token.isdigit() or len(token) < 4:
            continue
        if re.fullmatch(r"\d+[A-Z]?", token):
            continue
        return token
    return "LAINNYA"


def sheet_status_bucket(reference: ReferenceStatus) -> str:
    status = normalize(reference.status)
    if status in CLOSED_STATUSES:
        return "close"
    if status in REJECT_STATUSES or "TOLAK" in status or "REJECT" in status:
        return "reject"
    if status in UPDATE_STATUSES or "UPDATE" in status or "PROGRESS" in status:
        return "update"
    return "open"


def technician_sheet_orders(
    statuses: dict[str, ReferenceStatus], technician_name: str
) -> list[ReferenceStatus]:
    wanted = normalize(technician_name)
    return [
        reference
        for reference in unique_reference_orders(statuses)
        if normalize(reference.assigned_technician) == wanted
    ]


def area_summary(references: list[ReferenceStatus]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {"open": 0, "close": 0, "update": 0, "reject": 0}
    )
    for reference in references:
        area = classify_area(reference.address)
        summary[area][sheet_status_bucket(reference)] += 1
    return dict(summary)


def area_keyboard(areas: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, area in enumerate(areas):
        rows.append([
            InlineKeyboardButton(
                f"📍 {area}",
                callback_data=f"myarea:{index}",
            )
        ])
    return InlineKeyboardMarkup(rows)


def format_reference_open(reference: ReferenceStatus, index: int) -> str:
    ticket = normalize_ticket(reference.ticket_id) or "MANUAL"
    service = reference.service_number.strip() or "-"
    name = reference.customer_name.strip() or "-"
    phone = reference.customer_phone.strip() or "-"
    address = reference.address.strip() or "-"
    package = displayed_package(reference)
    return (
        f"{index}. {escape(name)}\n"
        f"{SEPARATOR}\n"
        f"🎫 Tiket : {escape(ticket)}\n"
        f"🌐 INET  : {escape(service)}\n"
        f"📞 CP    : {escape(phone)}\n"
        f"⚡ Paket : {escape(package)}\n"
        f"🏠 Alamat:\n{escape(address)}"
    )


def format_order(order: Order, index: int, reference: ReferenceStatus | None, category: str) -> str:
    ticket = displayed_ticket(order, reference)
    service = displayed_service(order, reference)
    name = displayed_value(order.customer_name, reference.customer_name if reference else "")

    if category == "open":
        phone = displayed_value(order.customer_phone, reference.customer_phone if reference else "")
        address = displayed_value(order.address, reference.address if reference else "")
        package = displayed_package(reference)
        return (
            f"{index}. {escape(name)}\n{SEPARATOR}\n"
            f"🎫 Tiket : {escape(ticket)}\n"
            f"🌐 INET  : {escape(service)}\n"
            f"📞 CP    : {escape(phone)}\n"
            f"⚡ Paket : {escape(package)}\n"
            f"🏠 Alamat:\n{escape(address)}"
        )

    if category == "close":
        return (
            f"{index}. {escape(name)}\n{SEPARATOR}\n"
            f"🎫 Tiket : {escape(ticket)}\n"
            f"🌐 INET  : {escape(service)}\n"
            f"🔢 SN New: {escape(displayed_new_sn(order, reference))}"
        )

    status_label = (
        reference.status if is_reference_closed(reference)
        else order.result.strip().upper() if is_database_closed(order)
        else "OPEN"
    )
    return (
        f"{index}. {escape(name)}\n{SEPARATOR}\n"
        f"Status   : {escape(status_label)}\n"
        f"🎫 Tiket : {escape(ticket)}\n"
        f"🌐 INET  : {escape(service)}\n"
        f"🔢 SN New: {escape(displayed_new_sn(order, reference))}"
    )


async def copy_order_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return
    data = query.data or ""
    prefix, separator, value = data.partition(":")
    if not separator or prefix not in {"copy_inet", "copy_cp"}:
        await query.answer("Data tidak valid.", show_alert=True)
        return
    await query.answer("Nomor dikirim. Tekan lama pada pesan untuk menyalin.")
    await query.message.reply_text(value, reply_to_message_id=query.message.message_id)


async def show_area_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    technician = await require_technician(update, context)
    if query is None or query.message is None or technician is None:
        return

    try:
        area_index = int((query.data or "").split(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Area tidak valid.", show_alert=True)
        return

    await query.answer()
    try:
        statuses = await get_reference_statuses(force=True, raise_errors=True)
    except Exception:
        await query.message.reply_text("❌ Gagal membaca Google Sheets terbaru.")
        return

    references = technician_sheet_orders(statuses, technician.name)
    areas = sorted(area_summary(references))
    if area_index < 0 or area_index >= len(areas):
        await query.message.reply_text("Daftar area berubah. Buka /orderanku lagi.")
        return

    area = areas[area_index]
    open_orders = [
        reference for reference in references
        if classify_area(reference.address) == area
        and sheet_status_bucket(reference) == "open"
    ]

    await query.message.reply_text(
        f"🟢 ORDER OPEN — {escape(area)}\n{escape(technician.name.upper())}\n\n"
        f"Total: {len(open_orders)}",
        parse_mode="HTML",
    )
    if not open_orders:
        await query.message.reply_text(
            "✅ Tidak ada order OPEN di daerah ini.",
            reply_markup=orderanku_menu(),
        )
        return

    for index, reference in enumerate(open_orders[:50], start=1):
        service = reference.service_number.strip() or "-"
        phone = reference.customer_phone.strip() or "-"
        await query.message.reply_text(
            format_reference_open(reference, index),
            parse_mode="HTML",
            reply_markup=copy_buttons(service, phone),
        )
    if len(open_orders) > 50:
        await query.message.reply_text(
            f"Ditampilkan 50 dari {len(open_orders)} order OPEN di {area}."
        )


async def refresh_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return
    await update.effective_message.reply_text("🔄 Membaca ulang Google Sheets...")
    try:
        statuses = await get_reference_statuses(force=True, raise_errors=True)
    except Exception:
        await update.effective_message.reply_text(
            "❌ Gagal membaca Google Sheets.\n"
            "Periksa URL, akses sharing, tab Sheet, dan koneksi internet."
        )
        return
    unique_orders = {
        reference.service_number or reference.ticket_id
        for reference in statuses.values()
        if reference.service_number or reference.ticket_id
    }
    await update.effective_message.reply_text(
        "✅ Data terbaru Google Sheets berhasil dimuat.\n"
        f"Referensi terbaca: {len(unique_orders)} order."
    )


async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return
    await update.effective_message.reply_text("Menu utama.", reply_markup=main_menu_keyboard())


async def orderanku(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    mode = context.args[0].lower().strip() if context.args else "ringkas"

    # Menu utama Orderanku sekarang mengambil dashboard area langsung dari
    # Google Sheets terbaru, bukan jumlah dari database lokal.
    if mode in {"ringkas", "menu", "statistik", "stats"}:
        try:
            statuses = await get_reference_statuses(force=True, raise_errors=True)
        except Exception:
            await update.effective_message.reply_text(
                "❌ Gagal membaca Google Sheets terbaru.",
                reply_markup=orderanku_menu(),
            )
            return

        references = technician_sheet_orders(statuses, technician.name)
        if not references:
            await update.effective_message.reply_text(
                "Belum ada order di Google Sheets yang cocok dengan nama teknisi kamu.\n\n"
                f"Nama akun bot: {technician.name}",
                reply_markup=orderanku_menu(),
            )
            return

        summary = area_summary(references)
        areas = sorted(summary, key=lambda area: (-summary[area]["open"], area))
        lines = [
            f"📋 ORDERANKU — {technician.name.upper()}",
            "",
            f"Total dari Google Sheet: {len(references)}",
            "",
            "📍 AREA PEKERJAAN",
        ]
        for area in areas:
            counts = summary[area]
            lines.extend([
                "",
                f"📍 {area}",
                f"🟢 Open: {counts['open']} | 🔴 Close: {counts['close']}",
                f"🟡 Update: {counts['update']} | ⚫ Menolak: {counts['reject']}",
            ])

        # Callback memakai index dari urutan alfabet agar stabil saat tombol ditekan.
        callback_areas = sorted(summary)
        await update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=area_keyboard(callback_areas),
        )
        return

    # Command lama tetap dipertahankan untuk kompatibilitas.
    all_orders = await repository(context).list_for_technician(
        technician.name, status="all", limit=5000
    )
    if not all_orders:
        await update.effective_message.reply_text(
            "Belum ada order yang cocok dengan nama teknisi kamu.",
            reply_markup=orderanku_menu(),
        )
        return

    reference_statuses = await get_reference_statuses()
    references = {
        order.id: status_for_order(reference_statuses, order.ticket_id, order.service_number)
        for order in all_orders
    }
    aliases = {
        "open": "open", "buka": "open",
        "close": "close", "closed": "close", "selesai": "close", "done": "close",
        "semua": "all", "all": "all",
    }
    status = aliases.get(mode)
    if status is None:
        await update.effective_message.reply_text(
            "Pilihan tidak dikenali. Gunakan /orderanku atau pilih OPEN, CLOSE, SEMUA.",
            reply_markup=orderanku_menu(),
        )
        return

    if status == "open":
        orders = [o for o in all_orders if not is_effectively_closed(o, references.get(o.id))]
    elif status == "close":
        orders = [o for o in all_orders if is_effectively_closed(o, references.get(o.id))]
    else:
        orders = all_orders

    matching_count = len(orders)
    orders = orders[:50]
    title = {"open": "🟢 ORDER OPEN", "close": "🔴 ORDER CLOSE/DONE", "all": "📋 SEMUA ORDER"}[status]
    if not orders:
        await update.effective_message.reply_text(
            f"{title} — {technician.name.upper()}\n\nTidak ada order pada kategori ini.",
            reply_markup=orderanku_menu(),
        )
        return

    await update.effective_message.reply_text(
        f"{title} — {technician.name.upper()}", reply_markup=orderanku_menu()
    )
    if status == "open":
        for index, order in enumerate(orders, start=1):
            reference = references.get(order.id)
            service = displayed_service(order, reference)
            phone = displayed_value(order.customer_phone, reference.customer_phone if reference else "")
            await update.effective_message.reply_text(
                format_order(order, index, reference, status),
                parse_mode="HTML",
                reply_markup=copy_buttons(service, phone),
            )
    else:
        chunks: list[str] = []
        current = ""
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
            await update.effective_message.reply_text(chunk, parse_mode="HTML")

    if matching_count > 50:
        await update.effective_message.reply_text(
            f"Ditampilkan 50 dari {matching_count} order.", reply_markup=orderanku_menu()
        )


def build_my_orders_handlers() -> list:
    return [
        CommandHandler("orderanku", orderanku),
        CommandHandler("refreshsheet", refresh_sheet),
        CallbackQueryHandler(show_area_open, pattern=AREA_CALLBACK_PATTERN),
        CallbackQueryHandler(copy_order_value, pattern=COPY_CALLBACK_PATTERN),
        MessageHandler(filters.Regex(f"^{re.escape(BACK_TO_MAIN)}$"), back_to_main_menu),
    ]
