from __future__ import annotations

import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

# `python webapp/server_ext.py` starts with /app/webapp on sys.path.
# Add the repository root so `webapp.server` can be imported reliably
# inside the Docker container.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from webapp import server as base


_original_load_my_open_orders = base.load_my_open_orders


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in {"", "-", "N/A", "NA", "NONE", "#N/A"} else text


def _service_key(value: object) -> str:
    return base.sheet_ref.normalize_key(value)


def load_my_open_orders(telegram_id: int, force: bool = False) -> dict:
    """Expose Sheet fields needed by the Mini App workflow.

    Orderanku already comes from the same unique Sheet references used by the
    chatbot. We deliberately re-match by service number (not ticket), because
    historical/updated ticket aliases can differ while the INET stays stable.
    Ticket priority itself remains centralized in google_sheet_reference:
    INSERA TODAY -> TIKET -> MANUAL.
    """
    payload = _original_load_my_open_orders(telegram_id, force=force)
    if not payload.get("ok"):
        return payload

    statuses = base._configured_sheet_statuses(force=False)
    references = base.sheet_ref.unique_reference_orders(statuses)
    by_service = {
        _service_key(reference.service_number): reference
        for reference in references
        if _service_key(reference.service_number)
    }

    for area in payload.get("areas", []):
        for order in area.get("orders", []):
            service = _service_key(order.get("service_number"))
            reference = by_service.get(service)
            if reference is None:
                continue

            # These fields are already present on the Order Sheet. Mini App
            # must not ask the technician to type them again when populated.
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
                    "onu_rx": _clean(reference.onu_rx) or _clean(order.get("onu_rx")),
                    "package": _clean(reference.package) or _clean(order.get("package")),
                    "rca": _clean(reference.rca) or _clean(order.get("rca")),
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
