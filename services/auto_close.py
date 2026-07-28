from __future__ import annotations

import logging
from functools import wraps

from services.excel_update import update_order_excel


def install_auto_close(order_flow_module) -> None:
    """Pasang pembaruan STATUS dan SN Excel setelah output berhasil dibuat."""
    original_send_outputs = order_flow_module.send_outputs

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

    order_flow_module.send_outputs = send_outputs_with_auto_close
