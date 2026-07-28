from __future__ import annotations

import logging
from functools import wraps

from telegram.ext import ConversationHandler

from services.excel_update import update_order_excel
from services.google_sheet_reference import (
    CLOSED_STATUSES,
    get_reference_statuses,
    normalize,
    status_for_order,
)


def install_auto_close(order_flow_module) -> None:
    """Pasang guard order selesai dan pembaruan status setelah output dibuat."""
    original_continue_order = order_flow_module.continue_order
    original_send_outputs = order_flow_module.send_outputs

    @wraps(original_continue_order)
    async def continue_order_with_close_guard(update, context, order) -> int:
        """Jangan meminta data ulang jika order sudah selesai."""
        message = update.effective_message
        if message is None:
            return ConversationHandler.END

        db_status = normalize(order.result)
        reference = None
        try:
            statuses = await get_reference_statuses()
            reference = status_for_order(
                statuses,
                ticket_id=order.ticket_id,
                service_number=order.service_number,
            )
        except Exception:
            # Google Sheets hanya referensi. Kegagalan membacanya tidak boleh
            # mematikan alur utama bot.
            logging.exception("Gagal memeriksa status Google Sheets pada order flow")

        sheet_status = normalize(reference.status) if reference else ""
        closed_status = sheet_status if sheet_status in CLOSED_STATUSES else db_status

        if closed_status in CLOSED_STATUSES:
            ticket_id = (
                (reference.ticket_id if reference else "")
                or order.ticket_id
                or "-"
            )
            new_sn = (
                (reference.new_sn if reference else "")
                or order.new_sn
                or "-"
            )
            source = "Google Sheets" if sheet_status in CLOSED_STATUSES else "database bot"

            await message.reply_text(
                "✅ Order ini sudah selesai. Data tidak perlu diisi ulang.\n\n"
                f"NO SERVICE : {order.service_number or '-'}\n"
                f"TIKET      : {ticket_id}\n"
                f"SN ONT NEW : {new_sn}\n"
                f"STATUS     : {closed_status}\n"
                f"SUMBER     : {source}",
                reply_markup=order_flow_module.main_menu_keyboard(),
            )

            for key in (
                "active_order_id",
                "missing_fields",
                "order_choices",
                "order_action",
            ):
                context.user_data.pop(key, None)
            return ConversationHandler.END

        return await original_continue_order(update, context, order)

    @wraps(original_send_outputs)
    async def send_outputs_with_auto_close(update, context, order, action) -> None:
        await original_send_outputs(update, context, order, action)

        message = update.effective_message
        if message is None:
            return

        new_sn = (order.new_sn or "").strip().upper()
        if not new_sn or new_sn == "-":
            await message.reply_text(
                "⚠️ Status belum diubah menjadi CLOSE karena SN ONT BARU belum tersedia."
            )
            return

        try:
            updated_order = await context.application.bot_data["orders"].update_fields(
                order.id,
                {"new_sn": new_sn, "result": "CLOSE"},
            )

            settings = context.application.bot_data["settings"]
            excel_path = (
                settings.database_path.parent
                / "imports"
                / updated_order.source_file
            )

            changed_rows = update_order_excel(
                excel_path,
                ticket_id=updated_order.ticket_id,
                service_number=updated_order.service_number,
                new_sn=new_sn,
                status="CLOSE",
            )

            await message.reply_text(
                "✅ Order otomatis ditandai selesai\n\n"
                f"SN ONT NEW : {new_sn}\n"
                "STATUS     : CLOSE\n"
                f"Baris Excel: {changed_rows}\n\n"
                "Gunakan /exportorder untuk mengambil Excel terbaru."
            )
        except Exception as exc:
            logging.exception("Gagal memperbarui Excel order secara otomatis")
            await message.reply_text(
                "⚠️ Format laporan berhasil dibuat, tetapi pembaruan Excel gagal:\n"
                f"{exc}"
            )

    order_flow_module.continue_order = continue_order_with_close_guard
    order_flow_module.send_outputs = send_outputs_with_auto_close
