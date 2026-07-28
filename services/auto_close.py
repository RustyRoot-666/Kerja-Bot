from __future__ import annotations

import logging
from functools import wraps

from services.excel_update import update_order_excel
from services.google_sheet_reference import (
    CLOSED_STATUSES,
    get_reference_statuses,
    is_reference_closed,
    normalize,
    status_for_order,
)


GENERIC_ONT_TYPES = {
    "ONT PREMIUM",
    "ONT DUALBAND",
    "ONT DUAL BAND",
    "ONT REPLACEMENT",
    "REPLACEMENT",
    "PREMIUM",
    "DUALBAND",
    "DUAL BAND",
}

EMPTY_VALUES = {"", "-", "N/A", "NA", "NONE", "NULL"}


def install_auto_close(order_flow_module) -> None:
    """Pasang validasi data dan pembaruan status setelah output dibuat."""
    original_continue_order = order_flow_module.continue_order
    original_send_outputs = order_flow_module.send_outputs

    # TYPE ONT harus berupa model perangkat sebenarnya, bukan kategori order
    # seperti ONT PREMIUM atau ONT DUALBAND.
    order_flow_module.FIELD_LABELS["ont_type"] = (
        "MODEL / TYPE ONT BARU (contoh: HG8145V5, HG8245H5, F609)"
    )

    def missing_fields_with_real_ont(order, action: str) -> list[str]:
        data = order_flow_module.order_data(order)
        missing: list[str] = []

        for field in order_flow_module.REQUIRED_FIELDS[action]:
            value = normalize(data.get(field, ""))
            if value in EMPTY_VALUES:
                missing.append(field)
                continue

            if field == "ont_type" and value in GENERIC_ONT_TYPES:
                missing.append(field)

        return missing

    order_flow_module.missing_fields = missing_fields_with_real_ont

    @wraps(original_continue_order)
    async def continue_order_with_validation(update, context, order) -> int:
        """Order OPEN maupun CLOSE tetap meminta field yang benar-benar kosong."""
        message = update.effective_message
        if message is None:
            return order_flow_module.ConversationHandler.END

        # Ambil hanya data referensi yang memang tersedia di Google Sheets.
        # Sheets tidak pernah ditulis atau dijadikan pengganti data teknisi.
        try:
            statuses = await get_reference_statuses()
            reference = status_for_order(
                statuses,
                ticket_id=order.ticket_id,
                service_number=order.service_number,
            )

            updates: dict[str, str] = {}
            if reference is not None:
                current_ticket = normalize(order.ticket_id)
                if reference.ticket_id and current_ticket in EMPTY_VALUES | {"MANUAL"}:
                    updates["ticket_id"] = reference.ticket_id
                if reference.new_sn and normalize(order.new_sn) in EMPTY_VALUES:
                    updates["new_sn"] = reference.new_sn
                if is_reference_closed(reference):
                    updates["result"] = reference.status or "CLOSE"

            if updates:
                order = await context.application.bot_data["orders"].update_fields(
                    order.id,
                    updates,
                )
        except Exception:
            logging.exception("Gagal membaca referensi Google Sheets saat validasi order")

        action = context.user_data.get("order_action", "lengkap")
        missing = order_flow_module.missing_fields(order, action)

        if missing:
            context.user_data["active_order_id"] = order.id
            context.user_data["missing_fields"] = missing

            lines = [
                "Data order ditemukan.",
                "",
                "Isi HANYA data yang masih kosong atau belum benar, satu jawaban per baris:",
                "",
            ]
            for index, field in enumerate(missing, start=1):
                lines.append(f"{index}. {order_flow_module.FIELD_LABELS[field]}")

            lines.extend(
                [
                    "",
                    "Data akan disimpan. Saat order diminta lagi, bot langsung mengirim output jika sudah lengkap.",
                    f"Jumlah jawaban harus {len(missing)} baris.",
                ]
            )

            await message.reply_text(
                "\n".join(lines),
                reply_markup=order_flow_module.cancel_keyboard(),
            )
            return order_flow_module.FILL_MISSING

        # Jika seluruh data sudah lengkap, order OPEN maupun CLOSE langsung
        # menghasilkan CONFIG/REPORT/STO sesuai menu yang diminta.
        return await original_continue_order(update, context, order)

    @wraps(original_send_outputs)
    async def send_outputs_with_auto_close(update, context, order, action) -> None:
        await original_send_outputs(update, context, order, action)

        # Mencetak ulang CONFIG/REPORT/STO dari order yang sudah selesai tidak
        # boleh menjalankan proses close atau pembaruan Excel untuk kedua kali.
        if normalize(order.result) in CLOSED_STATUSES:
            return

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

    order_flow_module.continue_order = continue_order_with_validation
    order_flow_module.send_outputs = send_outputs_with_auto_close
