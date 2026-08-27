from __future__ import annotations

from http.server import ThreadingHTTPServer

from webapp import server as base


_original_load_my_open_orders = base.load_my_open_orders


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in {"", "-", "N/A", "NA", "NONE", "#N/A"} else text


def load_my_open_orders(telegram_id: int, force: bool = False) -> dict:
    """Use the existing Orderanku logic, then expose workflow fields already present in Sheet.

    The Mini App should ask technicians only for fields that are genuinely missing.
    Ticket priority remains centralized in google_sheet_reference:
    INSERA TODAY -> TIKET -> MANUAL.
    """
    payload = _original_load_my_open_orders(telegram_id, force=force)
    if not payload.get("ok"):
        return payload

    statuses = base._configured_sheet_statuses(force=False)
    for area in payload.get("areas", []):
        for order in area.get("orders", []):
            service = str(order.get("service_number") or "").strip()
            ticket = str(order.get("ticket_id") or "").strip()
            reference = base.sheet_ref.status_for_order(statuses, ticket, service)
            if reference is None:
                continue

            order.update(
                {
                    "voip_number": _clean(reference.voip_number),
                    "old_sn": _clean(reference.old_sn),
                    "new_sn": _clean(reference.new_sn),
                    "ont_type": _clean(reference.ont_type),
                    "sto": _clean(reference.sto),
                    "valins_id": _clean(reference.valins_id),
                    "config_description": _clean(reference.config_description),
                    "report_description": _clean(reference.report_description),
                    # Sheet status OPEN/CLOSE is an order status, not necessarily
                    # the technician's REPORT result, so don't prefill RESULT.
                    "result": "",
                }
            )
    return payload


# Handler.do_GET resolves this name from the base module at request time.
base.load_my_open_orders = load_my_open_orders


if __name__ == "__main__":
    print(f"Kerja Bot Mini App listening on http://{base.HOST}:{base.PORT}")
    print(f"Database: {base.DATABASE_PATH}")
    ThreadingHTTPServer((base.HOST, base.PORT), base.Handler).serve_forever()
