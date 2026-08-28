from __future__ import annotations

import sys
from datetime import timedelta
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# `python webapp/server_ext.py` starts with /app/webapp on sys.path.
# Add the repository root so `webapp.server` can be imported reliably
# inside the Docker container.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from webapp import server as base


_original_load_my_open_orders = base.load_my_open_orders
_original_load_technician = base.load_technician
_original_do_get = base.Handler.do_GET


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in {"", "-", "N/A", "NA", "NONE", "#N/A"} else text


def _service_key(value: object) -> str:
    return base.sheet_ref.normalize_key(value)


def load_my_open_orders(telegram_id: int, force: bool = False) -> dict:
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
                    "result": "",
                }
            )
    return payload


def load_technician(identity_key: str, area: str) -> dict:
    payload = _original_load_technician(identity_key, area)
    today = base.datetime.now().date()
    trend = []
    try:
        with base.connect() as conn:
            _, rows = base._identity_members(conn, identity_key, area)
            for offset in range(6, -1, -1):
                day = today - timedelta(days=offset)
                services = {
                    str(row["service_number"] or "").strip()
                    for row in rows
                    if str(row["message_date"] or "")[:10] == day.isoformat()
                    and str(row["service_number"] or "").strip()
                }
                trend.append({"date": day.isoformat(), "label": base.DAYS[day.weekday()], "total": len(services)})
    except Exception as exc:
        print(f"[miniapp] gagal membuat trend teknisi: {exc}")
    payload["trend"] = trend
    return payload


base.load_my_open_orders = load_my_open_orders
base.load_technician = load_technician


def load_my_report(telegram_id: int) -> dict:
    technician = base._technician_by_telegram_id(telegram_id)
    if not technician:
        return {"ok": False, "error": "technician_not_registered", "message": "Akun Telegram belum terdaftar sebagai teknisi."}

    identity_key = f"NAME:{base._norm_name(technician['name'])}"
    detail = load_technician(identity_key, "ALL")
    return {
        "ok": True,
        "technician": {
            "telegram_id": telegram_id,
            "nik": str(technician.get("nik") or detail.get("nik") or "").strip(),
            "name": str(technician.get("name") or detail.get("name") or "-").strip(),
            "sto": str(technician.get("sto") or "").strip().upper(),
        },
        "daily": detail.get("daily", 0),
        "weekly": detail.get("weekly", 0),
        "all": detail.get("all", 0),
        "orders": detail.get("orders", []),
        "trend": detail.get("trend", []),
    }


def _extended_do_get(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/api/my-report":
        query = parse_qs(parsed.query)
        raw_id = (query.get("telegram_id") or [""])[0].strip()
        if not raw_id.isdigit():
            self._send_json({"ok": False, "error": "telegram_id_required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = load_my_report(int(raw_id))
            self._send_json(payload, HTTPStatus.OK if payload.get("ok") else HTTPStatus.NOT_FOUND)
        except Exception as exc:
            print(f"[miniapp] gagal membaca laporan pribadi: {exc}")
            self._send_json({"ok": False, "error": "report_error", "message": "Gagal membaca laporan pribadi."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return
    _original_do_get(self)


base.Handler.do_GET = _extended_do_get


if __name__ == "__main__":
    print(f"Kerja Bot Mini App listening on http://{base.HOST}:{base.PORT}")
    print(f"Database: {base.DATABASE_PATH}")
    ThreadingHTTPServer((base.HOST, base.PORT), base.Handler).serve_forever()
