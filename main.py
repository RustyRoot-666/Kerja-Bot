from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
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
from handlers.config_flow import build_config_conversation
from handlers.full_flow import build_full_conversation
from handlers.login import build_login_conversation, start
from handlers.report_flow import build_report_conversation
from handlers.sto_flow import build_sto_conversation
from utils.logging import setup_logging
from utils.keyboards import MAIN_MENU


async def post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    await db.initialize()
    logging.info("Bot started and database initialized")


def build_application() -> Application:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.photo_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(settings.log_dir)

    db = Database(settings.database_path)
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
    app.bot_data["settings"] = settings

    login_conv = build_login_conversation()
    full_conv = build_full_conversation()
    config_conv = build_config_conversation()
    report_conv = build_report_conversation()
    sto_conv = build_sto_conversation()

    app.add_handler(login_conv)
    app.add_handler(full_conv)
    app.add_handler(config_conv)
    app.add_handler(report_conv)
    app.add_handler(sto_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daftar_teknisi", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("delete", delete_history))
    app.add_handler(CommandHandler("export", export_history))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("settings", settings_menu))

    for handler in build_admin_handlers():
        app.add_handler(handler)

    app.add_handler(MessageHandler(filters.Regex(f"^({MAIN_MENU['profile']})$"), profile))
    app.add_handler(MessageHandler(filters.Regex(f"^({MAIN_MENU['settings']})$"), settings_menu))
    app.add_error_handler(error_handler)
    return app


async def error_handler(update, context) -> None:
    logging.exception("Unhandled bot error", exc_info=context.error)
    if update and update.effective_chat:
        await update.effective_chat.send_message("Terjadi error. Silakan coba lagi atau hubungi admin.")


def main() -> None:
    app = build_application()
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
