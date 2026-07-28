from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from database import Database
from handlers.common import cancel
from services.auth import require_technician
from services.excel_orders import import_workbook
from services.formatters import generate_config, generate_report, generate_sto
from services.google_sheet_reference import (
    CLOSED_STATUSES,
    get_reference_statuses,
    is_reference_closed,
    normalize,
    status_for_order,
)
from services.order_repository import Order, OrderRepository
from utils.keyboards import MAIN_MENU, cancel_keyboard, main_menu_keyboard
from utils.telegram_format import pre_block


SEARCH_ORDER, CHOOSE_ORDER, FILL_MISSING, WAIT_EXCEL = range(500, 504)


FIELD_LABELS = {
    "ticket_id": "TIKET ID",
    "service_number": "NO SERVICE",
    "voip_number": "NO VOIP",
    "customer_name": "NAMA PELANGGAN",
    "address": "ALAMAT",
    "customer_phone": "CP / NO HP",
    "old_sn": "SN ONT LAMA",
    "new_sn": "SN ONT BARU",
    "ont_type": "TYPE ONT",
    "sto": "STO",
    "valins_id": "VALINS ID",
    "result": "RESULT",
    "config_description": "KETERANGAN CONFIG",
    "report_description": "KETERANGAN REPORT/STO",
}


REQUIRED_FIELDS = {
    "config": [
        "ticket_id",
        "service_number",
        "voip_number",
        "old_sn",
        "new_sn",
        "ont_type",
        "sto",
        "config_description",
    ],
    "sto": [
        "ticket_id",
        "service_number",
        "old_sn",
        "new_sn",
        "ont_type",
        "sto",
        "valins_id",
        "report_description",
        "customer_name",
        "address",
        "customer_phone",
    ],
    "report": [
        "ticket_id",
        "service_number",
        "old_sn",
        "new_sn",
        "valins_id",
        "result",
        "report_description",
    ],
}

REQUIRED_FIELDS["lengkap"] = list(
    dict.fromkeys(
        REQUIRED_FIELDS["config"]
        + REQUIRED_FIELDS["sto"]
        + REQUIRED_FIELDS["report"]
    )
)


def repository(context: ContextTypes.DEFAULT_TYPE) -> OrderRepository:
    return context.application.bot_data["orders"]


def order_data(order: Order) -> dict[str, str]:
    return order.to_dict()


def missing_fields(order: Order, action: str) -> list[str]:
    data = order_data(order)
    missing: list[str] = []
    for field in REQUIRED_FIELDS[action]:
        field_value = data.get(field, "").strip()
        if not field_value:
            missing.append(field)
    return missing


def command_action(update: Update) -> str:
    text = (update.effective_message.text or "").strip()
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0]
    return command.removeprefix("/")


async def start_output(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return ConversationHandler.END

    action = command_action(update)
    if action not in REQUIRED_FIELDS:
        menu_text = update.effective_message.text or ""
        if menu_text == MAIN_MENU["config"]:
            action = "config"
        elif menu_text == MAIN_MENU["sto"]:
            action = "sto"
        elif menu_text == MAIN_MENU["report"]:
            action = "report"
        else:
            action = "lengkap"

    context.user_data["order_action"] = action
    context.user_data.pop("active_order_id", None)
    context.user_data.pop("missing_fields", None)

    args = list(context.args or [])
    if args:
        return await search_and_continue(update, context, " ".join(args))

    await update.effective_message.reply_text(
        f"Masukkan NO SERVICE, TIKET ID, nama, alamat, atau CP untuk /{action}:",
        reply_markup=cancel_keyboard(),
    )
    return SEARCH_ORDER


async def receive_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None or not update.effective_message.text:
        return SEARCH_ORDER
    return await search_and_continue(update, context, update.effective_message.text)


async def search_and_continue(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
) -> int:
    results = await repository(context).search(query)

    if not results:
        await update.effective_message.reply_text(
            "Order tidak ditemukan. Periksa kata kunci atau import Excel melalui /importorder."
        )
        return SEARCH_ORDER

    if len(results) == 1:
        context.user_data["active_order_id"] = results[0].id
        return await continue_order(update, context, results[0])

    context.user_data["order_choices"] = {
        str(index): order.id for index, order in enumerate(results, start=1)
    }

    lines = ["Ditemukan beberapa order. Pilih nomor:"]
    for index, order in enumerate(results, start=1):
        lines.append(
            f"{index}. {order.ticket_id or '-'} | "
            f"{order.service_number or '-'} | "
            f"{order.customer_name or '-'}"
        )

    await update.effective_message.reply_text("\n".join(lines))
    return CHOOSE_ORDER


async def choose_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None or not update.effective_message.text:
        return CHOOSE_ORDER

    choice = update.effective_message.text.strip()
    order_id = context.user_data.get("order_choices", {}).get(choice)

    if not order_id:
        await update.effective_message.reply_text(
            "Pilihan tidak valid. Kirim nomor yang tersedia."
        )
        return CHOOSE_ORDER

    order = await repository(context).get(order_id)
    if order is None:
        await update.effective_message.reply_text("Order tidak ditemukan.")
        return ConversationHandler.END

    context.user_data["active_order_id"] = order.id
    return await continue_order(update, context, order)


async def continue_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order: Order,
) -> int:
    action = context.user_data["order_action"]

    # Google Sheets hanya dibaca sebagai referensi. Untuk order yang sudah
    # CLOSE/DONE, lengkapi field referensi yang tersedia lalu langsung cetak
    # output yang diminta tanpa meminta teknisi mengisi ulang.
    statuses = await get_reference_statuses()
    reference = status_for_order(statuses, order.ticket_id, order.service_number)

    updates: dict[str, str] = {}
    if reference is not None:
        current_ticket = normalize(order.ticket_id)
        if reference.ticket_id and current_ticket in {"", "-", "MANUAL"}:
            updates["ticket_id"] = reference.ticket_id
        if reference.new_sn and not order.new_sn.strip():
            updates["new_sn"] = reference.new_sn
        if is_reference_closed(reference):
            updates["result"] = reference.status or "CLOSE"

    if updates:
        order = await repository(context).update_fields(order.id, updates)

    database_closed = normalize(order.result) in CLOSED_STATUSES
    reference_closed = is_reference_closed(reference)
    if database_closed or reference_closed:
        await send_outputs(update, context, order, action)
        context.user_data.pop("active_order_id", None)
        context.user_data.pop("missing_fields", None)
        context.user_data.pop("order_choices", None)
        context.user_data.pop("order_action", None)
        return ConversationHandler.END

    missing = missing_fields(order, action)

    if not missing:
        await send_outputs(update, context, order, action)
        return ConversationHandler.END

    context.user_data["missing_fields"] = missing

    lines = [
        "Data order ditemukan.",
        "",
        "Isi HANYA data yang masih kosong, satu jawaban per baris:",
        "",
    ]
    for index, field in enumerate(missing, start=1):
        lines.append(f"{index}. {FIELD_LABELS[field]}")

    lines.extend(
        [
            "",
            "Gunakan tanda - jika memang tidak ada.",
            f"Jumlah jawaban harus {len(missing)} baris.",
        ]
    )

    await update.effective_message.reply_text("\n".join(lines))
    return FILL_MISSING


async def fill_missing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None or not update.effective_message.text:
        return FILL_MISSING

    missing: list[str] = context.user_data.get("missing_fields", [])
    values = [line.strip() for line in update.effective_message.text.splitlines()]

    if len(values) != len(missing):
        await update.effective_message.reply_text(
            f"Jumlah baris belum sesuai. Dibutuhkan {len(missing)} baris, "
            f"tetapi diterima {len(values)} baris.\n\n"
            "Kirim ulang sesuai urutan yang tadi."
        )
        return FILL_MISSING

    updates = {
        field: value if value != "-" else "-"
        for field, value in zip(missing, values)
    }

    order_id = context.user_data.get("active_order_id")
    order = await repository(context).update_fields(order_id, updates)
    action = context.user_data["order_action"]

    await send_outputs(update, context, order, action)
    context.user_data.pop("active_order_id", None)
    context.user_data.pop("missing_fields", None)
    context.user_data.pop("order_choices", None)
    context.user_data.pop("order_action", None)
    return ConversationHandler.END


async def send_outputs(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order: Order,
    action: str,
) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    data = order_data(order)
    settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]

    outputs: list[tuple[str, str]] = []

    if action in {"config", "lengkap"}:
        outputs.append(("CONFIG", generate_config(technician, data)))

    if action in {"report", "lengkap"}:
        outputs.append(("REPORT", generate_report(technician, data, settings.timezone)))

    if action in {"sto", "lengkap"}:
        outputs.append(("STO", generate_sto(technician, data)))

    for index, (kind, content) in enumerate(outputs):
        await db.save_history(technician, kind, data, content)
        markup = main_menu_keyboard() if index == len(outputs) - 1 else None
        await update.effective_message.reply_text(
            pre_block(content),
            parse_mode="HTML",
            reply_markup=markup,
        )

    context.user_data["last_replacement"] = data.copy()


async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None or update.effective_message is None:
        return ConversationHandler.END

    settings = context.application.bot_data["settings"]
    if update.effective_user.id not in settings.admin_ids:
        await update.effective_message.reply_text(
            "Perintah /importorder hanya untuk admin."
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "Kirim file Excel order berformat .xlsx:",
        reply_markup=cancel_keyboard(),
    )
    return WAIT_EXCEL


async def receive_excel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None or update.effective_message.document is None:
        if update.effective_message:
            await update.effective_message.reply_text("Kirim file .xlsx.")
        return WAIT_EXCEL

    document = update.effective_message.document
    filename = document.file_name or "orders.xlsx"

    if not filename.lower().endswith(".xlsx"):
        await update.effective_message.reply_text(
            "Format harus .xlsx, bukan .xls atau file lain."
        )
        return WAIT_EXCEL

    settings = context.application.bot_data["settings"]
    import_dir = settings.database_path.parent / "imports"
    import_dir.mkdir(parents=True, exist_ok=True)
    target = import_dir / filename

    telegram_file = await context.bot.get_file(document.file_id)
    await telegram_file.download_to_drive(custom_path=target)

    await update.effective_message.reply_text("Membaca dan menyimpan order...")

    try:
        stats = await import_workbook(target, repository(context))
    except Exception as exc:
        await update.effective_message.reply_text(
            f"Import gagal: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "✅ Import order selesai\n\n"
        f"Sheet terbaca : {stats['sheets']}\n"
        f"Baris dibaca  : {stats['rows']}\n"
        f"Data baru     : {stats['inserted']}\n"
        f"Diperbarui    : {stats['updated']}\n"
        f"Dilewati      : {stats['skipped']}\n"
        f"Gagal         : {stats['failed']}",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


def build_order_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("config", start_output),
            CommandHandler("sto", start_output),
            CommandHandler("report", start_output),
            CommandHandler("lengkap", start_output),
            CommandHandler("importorder", start_import),
            MessageHandler(filters.Regex(f"^{MAIN_MENU['config']}$"), start_output),
            MessageHandler(filters.Regex(f"^{MAIN_MENU['sto']}$"), start_output),
            MessageHandler(filters.Regex(f"^{MAIN_MENU['report']}$"), start_output),
            MessageHandler(filters.Regex(f"^{MAIN_MENU['full']}$"), start_output),
        ],
        states={
            SEARCH_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_search)],
            CHOOSE_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_order)],
            FILL_MISSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, fill_missing)],
            WAIT_EXCEL: [MessageHandler(filters.Document.ALL, receive_excel)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="order_conversation",
        persistent=False,
        allow_reentry=True,
    )
