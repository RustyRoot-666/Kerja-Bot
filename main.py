from __future__ import annotations

import logging

import handlers.order_flow as order_flow_module
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from config import settings
from database import Database
from handlers.admin import build_admin_handlers
from handlers.common import (
    cancel,
    delete_history,
    export_history,
    history,
    profile,
    search,
    settings_menu,
)
from handlers.excel_status import build_excel_status_handlers
from handlers.google_sheet import build_google_sheet_handlers
from handlers.login import build_login_conversation, start
from handlers.my_orders import build_my_orders_handlers, orderanku
from handlers.order_flow import build_order_conversation
from services.auto_close import install_auto_close
from services.google_sheet_reference import (
    get_reference_statuses,
    initialize_sheet_config,
    sync_missing_orders_from_sheet,
)
from services.order_repository import OrderRepository
from utils.keyboards import MAIN_MENU
from utils.logging import setup_logging


AUTO_SHEET_SYNC_SECONDS = 180


async def auto_sync_google_sheet(context) -> None:
    """Refresh Google Sheet and mirror its latest order data into the local DB."""
    try:
        app = context.application
        database_path = app.bot_data["settings"].database_path
        statuses = await get_reference_statuses(force=True, raise_errors=True)
        total, inserted, updated, unchanged = await sync_missing_orders_from_sheet(
            database_path,
            statuses,
        )
        logging.info(
            "Google Sheet auto-sync complete: total=%s inserted=%s updated=%s unchanged=%s",
            total,
            inserted,
            updated,
            unchanged,
        )
    except Exception:
        # A temporary Google/network failure must never stop the Telegram bot.
        logging.exception("Google Sheet auto-sync failed; keeping previous data")


async def post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    orders: OrderRepository = application.bot_data["orders"]
    await db.initialize()
    await orders.initialize()
    await initialize_sheet_config(application.bot_data["settings"].database_path)

    if application.job_queue is None:
        logging.warning(
            "JobQueue unavailable; Google Sheet auto-sync is disabled. "
            "Install python-telegram-bot[job-queue]."
        )
    else:
        application.job_queue.run_repeating(
            auto_sync_google_sheet,
            interval=AUTO_SHEET_SYNC_SECONDS,
            first=5,
            name="google-sheet-auto-sync",
        )

    logging.info(
        "Bot started; technician, order, Google Sheets config, and auto-sync initialized"
    )


def build_application() -> Application:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.photo_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(settings.log_dir)

    db = Database(settings.database_path)
    orders = OrderRepository(settings.database_path)

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=30.0,
    )

    app = (
        Application.builder()
        .token(settings.bot_token)
        .request(request)
        .get_updates_request(request)
        .post_init(post_init)
        .build()
    )

    app.bot_data["db"] = db
    app.bot_data["orders"] = orders
    app.bot_data["settings"] = settings

    install_auto_close(order_flow_module)

    login_conv = build_login_conversation()
    order_conv = build_order_conversation()

    app.add_handler(login_conv)
    app.add_handler(order_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daftar_teknisi", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("delete", delete_history))
    app.add_handler(CommandHandler("export", export_history))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("settings", settings_menu))

    for handler in build_excel_status_handlers():
        app.add_handler(handler)

    for handler in build_my_orders_handlers():
        app.add_handler(handler)

    for handler in build_google_sheet_handlers():
        app.add_handler(handler)

    for handler in build_admin_handlers():
        app.add_handler(handler)

    app.add_handler(
        MessageHandler(
            filters.Regex(f"^({MAIN_MENU['orders']})$"),
            orderanku,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(f"^({MAIN_MENU['profile']})$"),
            profile,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Regex(f"^({MAIN_MENU['settings']})$"),
            settings_menu,
        )
    )

    app.add_error_handler(error_handler)
    return app


async def error_handler(update, context) -> None:
    logging.exception("Unhandled bot error", exc_info=context.error)
    if update and update.effective_chat:
        await update.effective_chat.send_message(
            "Terjadi error. Silakan coba lagi atau hubungi admin."
        )


def main() -> None:
    app = build_application()
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
