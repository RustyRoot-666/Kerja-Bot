from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

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
from handlers.customer_format import format_customer_command
from handlers.excel_status import build_excel_status_handlers
from handlers.google_sheet import build_google_sheet_handlers
from handlers.login import build_login_conversation, start
from handlers.my_orders import build_my_orders_handlers, orderanku
from handlers.order_flow import build_order_conversation
from services.assign_request import handle_assign_message
from services.auto_close import install_auto_close
from services.daily_recap import (
    initialize_recap_delivery_log,
    recap_harian_command,
    recap_mingguan_command,
    send_daily_recaps,
    send_previous_week_recaps_once,
    send_weekly_recaps,
)
from services.google_sheet_reference import (
    get_reference_statuses,
    initialize_sheet_config,
    sync_missing_orders_from_sheet,
)
from services.logic_dispatch import detect_logic_group, ignore_group_message
from services.order_repository import OrderRepository
from services.report_area_leaderboard import send_daily_close, send_report_leaderboard
from services.report_hourly_progress import (
    remember_report_manyar_group,
    send_hourly_report_progress,
)
from services.report_leaderboard import (
    capture_report_group_message,
    capture_sto_recap_group_message,
)
from services.report_multi_topic import handle_multi_report_topic
from services.update_kendala import handle_update_message, migrate_existing_evidence_urls
from utils.keyboards import MAIN_MENU
from utils.logging import setup_logging


AUTO_SHEET_SYNC_SECONDS = 180
REPORT_PROGRESS_SECONDS = 3600


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
        logging.exception("Google Sheet auto-sync failed; keeping previous data")


async def leaderboard_command(update, context) -> None:
    chat = update.effective_chat
    user = update.effective_user
    app_settings = context.application.bot_data["settings"]
    if not chat or chat.type != "private" or not user or user.id not in app_settings.admin_ids:
        return
    await send_report_leaderboard(context)


async def closeharian_command(update, context) -> None:
    chat = update.effective_chat
    user = update.effective_user
    app_settings = context.application.bot_data["settings"]
    if not chat or chat.type != "private" or not user or user.id not in app_settings.admin_ids:
        return
    await send_daily_close(context)


async def post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    orders: OrderRepository = application.bot_data["orders"]
    await db.initialize()
    await orders.initialize()
    await initialize_sheet_config(application.bot_data["settings"].database_path)
    await initialize_recap_delivery_log(db)

    try:
        migrated = await migrate_existing_evidence_urls()
        logging.info("Kendala evidence URL migration complete: updated=%s", migrated)
    except Exception:
        logging.exception("Kendala evidence URL migration failed; bot startup continues")

    await send_previous_week_recaps_once(application)

    if application.job_queue is None:
        logging.warning(
            "JobQueue unavailable; Google Sheet auto-sync, technician recaps, leaderboard, daily close, and hourly REPORT MANYAR progress are disabled. "
            "Install python-telegram-bot[job-queue]."
        )
    else:
        application.job_queue.run_repeating(
            auto_sync_google_sheet,
            interval=AUTO_SHEET_SYNC_SECONDS,
            first=5,
            name="google-sheet-auto-sync",
        )
        recap_tz = ZoneInfo(application.bot_data["settings"].timezone)
        now = datetime.now(recap_tz)
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        first_progress = max(1, int((next_hour - now).total_seconds()))
        application.job_queue.run_repeating(
            send_hourly_report_progress,
            interval=REPORT_PROGRESS_SECONDS,
            first=first_progress,
            name="hourly-report-manyar-progress",
        )
        application.job_queue.run_daily(
            send_report_leaderboard,
            time=time(hour=22, minute=0, tzinfo=recap_tz),
            name="daily-report-leaderboard",
        )
        application.job_queue.run_daily(
            send_daily_close,
            time=time(hour=23, minute=59, tzinfo=recap_tz),
            name="daily-report-close",
        )
        application.job_queue.run_daily(
            send_daily_recaps,
            time=time(hour=23, minute=59, tzinfo=recap_tz),
            name="daily-technician-recap",
        )
        application.job_queue.run_daily(
            send_weekly_recaps,
            time=time(hour=20, minute=0, tzinfo=recap_tz),
            days=(4,),
            name="weekly-technician-recap",
        )

    logging.info(
        "Bot started; technician, order, Google Sheets config, auto-sync, daily recap, weekly recap, area leaderboard, area daily close, hourly REPORT progress, multi-topic /sto report, /update kendala, public evidence links, /assign NTE Manyar, private /tiket, /format WhatsApp customer, STO recap replies in REPORT MANYAR, and previous-week catch-up initialized"
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

    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS, handle_multi_report_topic),
        group=-7,
    )
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS, remember_report_manyar_group),
        group=-6,
    )
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS, capture_sto_recap_group_message),
        group=-5,
    )
    app.add_handler(MessageHandler(filters.ALL, handle_assign_message), group=-4)
    app.add_handler(MessageHandler(filters.ALL, handle_update_message), group=-3)
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS, capture_report_group_message),
        group=-2,
    )
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS, detect_logic_group),
        group=-1,
    )
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS, ignore_group_message),
        group=0,
    )

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
    app.add_handler(CommandHandler("format", format_customer_command))
    app.add_handler(CommandHandler("rekapharian", recap_harian_command))
    app.add_handler(CommandHandler("rekapmingguan", recap_mingguan_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("closeharian", closeharian_command))

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
    if not update or not update.effective_chat:
        return

    if update.effective_chat.type != "private":
        return

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
