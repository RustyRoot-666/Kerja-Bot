from __future__ import annotations

import sys
from datetime import timedelta
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def _order_payload(reference) -> dict:
    package = _clean(reference.package)
    if package and package.replace(".", "", 1).replace(",", "", 1).isdigit():
        package = f"{package} Mbps"
    return {
        "customer_name": _clean(reference.customer_name) or "-",
        "ticket_id": base.sheet_ref.normalize_ticket(reference.ticket_id) or "MANUAL",
        "service_number": _clean(reference.service_number) or "-",
        "customer_phone": _clean(reference.customer_phone) or "-",
        "package": package or "-",
        "onu_rx": _clean(reference.onu_rx) or "-",
        "rca": _clean(reference.rca) or "-",
        "address": _clean(reference.address) or "-",
        "voip_number": _clean(reference.voip_number),
        "old_sn": _clean(reference.old_sn),
        "new_sn": _clean(reference.new_sn),
        "ont_type": _clean(reference.ont_type),
        "sto": _clean(reference.sto),
        "valins_id": _clean(reference.valins_id),
        "config_description": _clean(reference.config_description),
        "report_description": _clean(reference.report_description),
        "result": "",
        "assigned_technician": _clean(reference.assigned_technician) or "-",
        "area": base.classify_area(reference.address),
    }


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
                    "assigned_technician": _clean(reference.assigned_technician) or "-",
                }
            )
    return payload


def search_open_orders(telegram_id: int, query: str, force: bool = False) -> dict:
    """Search OPEN Sheet orders across all technicians by INET.

    Access is limited to registered technicians, but assignment is intentionally
    not used as a filter so one technician can take over another technician's
    OPEN order when operationally needed.
    """
    technician = base._technician_by_telegram_id(telegram_id)
    if not technician:
        return {"ok": False, "error": "technician_not_registered", "message": "Akun Telegram belum terdaftar sebagai teknisi."}

    wanted = "".join(ch for ch in str(query or "") if ch.isdigit())
    if len(wanted) < 6:
        return {"ok": False, "error": "query_too_short", "message": "Masukkan minimal 6 digit nomor INET."}

    statuses = base._configured_sheet_statuses(force=force)
    matches = []
    for reference in base.sheet_ref.unique_reference_orders(statuses):
        if base.sheet_status_bucket(reference) != "open":
            continue
        service = "".join(ch for ch in str(reference.service_number or "") if ch.isdigit())
        if wanted not in service:
            continue
        matches.append(_order_payload(reference))
        if len(matches) >= 20:
            break

    matches.sort(key=lambda item: (item["service_number"] != wanted, item["service_number"]))
    return {
        "ok": True,
        "query": wanted,
        "count": len(matches),
        "orders": matches,
        "technician": {
            "telegram_id": telegram_id,
            "nik": str(technician.get("nik") or "").strip(),
            "name": str(technician.get("name") or "").strip(),
            "sto": str(technician.get("sto") or "").strip().upper(),
        },
    }


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
    orders = [dict(item) for item in detail.get("orders", [])]

    try:
        with base.connect() as conn:
            _, rows = base._identity_members(conn, identity_key, "ALL")
            latest_by_service: dict[str, str] = {}
            for row in rows:
                service = str(row["service_number"] or "").strip()
                raw_day = str(row["message_date"] or "")[:10]
                if service and raw_day and raw_day > latest_by_service.get(service, ""):
                    latest_by_service[service] = raw_day
            for order in orders:
                order["raw_day"] = latest_by_service.get(str(order.get("service_number") or "").strip(), "")
    except Exception as exc:
        print(f"[miniapp] gagal menambahkan raw_day laporan: {exc}")

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
        "orders": orders,
        "trend": detail.get("trend", []),
    }


def _extended_do_get(self) -> None:
    parsed = urlparse(self.path)
    query = parse_qs(parsed.query)

    if parsed.path == "/api/my-report":
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

    if parsed.path == "/api/open-order-search":
        raw_id = (query.get("telegram_id") or [""])[0].strip()
        search_query = (query.get("q") or [""])[0].strip()
        if not raw_id.isdigit():
            self._send_json({"ok": False, "error": "telegram_id_required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = search_open_orders(int(raw_id), search_query, force=(query.get("force") or ["0"])[0] == "1")
            status = HTTPStatus.OK if payload.get("ok") else (HTTPStatus.BAD_REQUEST if payload.get("error") == "query_too_short" else HTTPStatus.NOT_FOUND)
            self._send_json(payload, status)
        except Exception as exc:
            print(f"[miniapp] gagal mencari OPEN INET global: {exc}")
            self._send_json({"ok": False, "error": "sheet_error", "message": "Gagal mencari INET pada Google Sheet."}, HTTPStatus.BAD_GATEWAY)
        return

    _original_do_get(self)


base.Handler.do_GET = _extended_do_get


if __name__ == "__main__":
    print(f"Kerja Bot Mini App listening on http://{base.HOST}:{base.PORT}")
    print(f"Database: {base.DATABASE_PATH}")
    ThreadingHTTPServer((base.HOST, base.PORT), base.Handler).serve_forever()
