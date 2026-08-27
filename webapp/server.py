from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/app/database/bot.sqlite3"))
HOST = "0.0.0.0"
PORT = int(os.getenv("MINIAPP_PORT", "8080"))

MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
DAYS = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


def period_bounds(day: date) -> tuple[date, date]:
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    return start, start + timedelta(days=6)


def date_label(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def area_condition(area: str) -> tuple[str, tuple[str, ...]]:
    area = area.upper().strip()
    if area == "JGR":
        return (
            "EXISTS (SELECT 1 FROM report_area_orders ra WHERE ra.service_number=r.service_number AND ra.period_start=r.period_start AND UPPER(TRIM(ra.sto_code))=?)",
            ("JGR",),
        )
    if area == "MYR":
        return (
            "(EXISTS (SELECT 1 FROM report_area_orders ra WHERE ra.service_number=r.service_number AND ra.period_start=r.period_start AND UPPER(TRIM(ra.sto_code))=?) OR (NOT EXISTS (SELECT 1 FROM report_area_orders ra0 WHERE ra0.service_number=r.service_number AND ra0.period_start=r.period_start) AND EXISTS (SELECT 1 FROM orders o WHERE o.service_number=r.service_number AND UPPER(TRIM(o.sto))=?)))",
            ("MYR", "MYR"),
        )
    return "1=1", ()


def time_condition(period: str, today: date) -> tuple[str, tuple[str, ...], str]:
    period = period.lower().strip()
    start, end = period_bounds(today)
    if period == "daily":
        return "substr(r.message_date,1,10)=?", (today.isoformat(),), date_label(today)
    if period == "weekly":
        return "r.period_start=?", (start.isoformat(),), f"{date_label(start)} - {date_label(end)}"
    return "1=1", (), "Keseluruhan"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _norm_name(value: str) -> str:
    text = str(value or "").upper().strip()
    text = re.sub(r"^(?:NAME|NAMA)\s*[-:=]\s*", "", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def _norm_nik(value: str) -> str:
    text = str(value or "").upper().strip()
    return re.sub(r"[^A-Z0-9]", "", text)


def _technician_registry(conn: sqlite3.Connection) -> tuple[dict[str, dict], dict[str, dict]]:
    by_nik: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    try:
        rows = conn.execute("SELECT nik, name, sto FROM technicians").fetchall()
    except sqlite3.OperationalError:
        return by_nik, by_name
    for row in rows:
        item = {
            "nik": str(row["nik"] or "").strip(),
            "name": str(row["name"] or "").strip(),
            "sto": str(row["sto"] or "").strip().upper(),
        }
        nik_key = _norm_nik(item["nik"])
        name_key = _norm_name(item["name"])
        if nik_key:
            by_nik[nik_key] = item
        if name_key:
            by_name[name_key] = item
    return by_nik, by_name


def _identity_for(row: sqlite3.Row, by_nik: dict[str, dict], by_name: dict[str, dict]) -> dict:
    raw_nik = str(row["nik"] or "").strip()
    raw_name = str(row["name"] or "").strip()
    nik_key = _norm_nik(raw_nik)
    name_key = _norm_name(raw_name)

    registered = by_nik.get(nik_key) if nik_key else None
    if registered is None and name_key:
        registered = by_name.get(name_key)

    if registered:
        canonical_nik = registered["nik"] or raw_nik
        canonical_name = registered["name"] or raw_name or "-"
        key = f"NIK:{_norm_nik(canonical_nik)}" if canonical_nik else f"NAME:{_norm_name(canonical_name)}"
        return {
            "key": key,
            "nik": canonical_nik,
            "name": canonical_name,
            "sto": registered.get("sto", ""),
        }

    if name_key:
        return {
            "key": f"NAME:{name_key}",
            "nik": raw_nik,
            "name": raw_name or "-",
            "sto": "",
        }

    return {
        "key": f"NIK:{nik_key or raw_nik}",
        "nik": raw_nik,
        "name": raw_name or raw_nik or "-",
        "sto": "",
    }


def _report_rows(conn: sqlite3.Connection, where_sql: str, params: tuple[str, ...]) -> list[sqlite3.Row]:
    return conn.execute(
        f"""
        SELECT r.technician_nik AS nik,
               r.technician_name AS name,
               r.service_number,
               r.period_start,
               r.message_date,
               UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''), ra.sto_code, o.sto, ''))) AS area_label,
               UPPER(TRIM(COALESCE(ra.sto_code, o.sto, ''))) AS sto
        FROM report_group_orders r
        LEFT JOIN report_area_orders ra
          ON ra.service_number=r.service_number AND ra.period_start=r.period_start
        LEFT JOIN orders o ON o.id=(
            SELECT o2.id FROM orders o2
            WHERE o2.service_number=r.service_number
            ORDER BY o2.id DESC LIMIT 1
        )
        WHERE {where_sql}
        """,
        params,
    ).fetchall()


def _group_rows(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    by_nik, by_name = _technician_registry(conn)
    grouped: dict[str, dict] = {}
    for row in rows:
        identity = _identity_for(row, by_nik, by_name)
        key = identity["key"]
        item = grouped.setdefault(
            key,
            {
                **identity,
                "services": set(),
                "area_label": "",
                "area_sto": "",
                "latest": "",
            },
        )
        service = str(row["service_number"] or "").strip()
        if service:
            item["services"].add(service)
        message_date = str(row["message_date"] or "")
        if message_date >= item["latest"]:
            item["latest"] = message_date
            item["area_label"] = str(row["area_label"] or "")
            item["area_sto"] = str(row["sto"] or "")
        # Prefer a real NIK over imported placeholders such as NAME-... or TG-...
        raw_nik = str(row["nik"] or "").strip()
        if (not item["nik"] or item["nik"].upper().startswith(("NAME-", "TG-"))) and raw_nik and not raw_nik.upper().startswith(("NAME-", "TG-")):
            item["nik"] = raw_nik

    result = []
    for item in grouped.values():
        result.append({
            "key": item["key"],
            "nik": item["nik"],
            "name": item["name"],
            "total": len(item["services"]),
            "area_label": item["area_label"],
            "sto": item["area_sto"] or item.get("sto", ""),
        })
    result.sort(key=lambda item: (-item["total"], _norm_name(item["name"])))
    return result


def load_dashboard(area: str, period: str) -> dict:
    today = datetime.now().date()
    area_sql, area_params = area_condition(area)
    time_sql, time_params, label = time_condition(period, today)

    try:
        with connect() as conn:
            rows = _report_rows(conn, f"{time_sql} AND {area_sql}", (*time_params, *area_params))
            leaderboard = _group_rows(conn, rows)

            trend = []
            week_start, _ = period_bounds(today)
            for offset in range(7):
                day = week_start + timedelta(days=offset)
                day_rows = _report_rows(
                    conn,
                    f"substr(r.message_date,1,10)=? AND {area_sql}",
                    (day.isoformat(), *area_params),
                )
                total = len({str(row["service_number"] or "").strip() for row in day_rows if str(row["service_number"] or "").strip()})
                trend.append({
                    "date": day.isoformat(),
                    "label": DAYS[day.weekday()],
                    "total": total,
                })
    except sqlite3.Error:
        leaderboard = []
        trend = []

    total_close = sum(item["total"] for item in leaderboard)
    active = len(leaderboard)
    return {
        "area": area.upper(),
        "period": period,
        "period_label": label,
        "summary": {
            "total_close": total_close,
            "active_technicians": active,
            "average_close": round(total_close / active, 1) if active else 0,
        },
        "trend": trend,
        "leaderboard": leaderboard,
    }


def _identity_members(conn: sqlite3.Connection, identity_key: str, area: str) -> tuple[dict, list[sqlite3.Row]]:
    area_sql, area_params = area_condition(area)
    rows = _report_rows(conn, area_sql, area_params)
    by_nik, by_name = _technician_registry(conn)
    members: list[sqlite3.Row] = []
    chosen = {"key": identity_key, "nik": "", "name": "-", "sto": ""}
    for row in rows:
        identity = _identity_for(row, by_nik, by_name)
        if identity["key"] == identity_key:
            members.append(row)
            chosen = identity
    return chosen, members


def load_technician(identity_key: str, area: str) -> dict:
    today = datetime.now().date()
    week_start, _ = period_bounds(today)

    try:
        with connect() as conn:
            identity, rows = _identity_members(conn, identity_key, area)
            services_all = {str(r["service_number"] or "").strip() for r in rows if str(r["service_number"] or "").strip()}
            services_daily = {
                str(r["service_number"] or "").strip()
                for r in rows
                if str(r["message_date"] or "")[:10] == today.isoformat() and str(r["service_number"] or "").strip()
            }
            services_weekly = {
                str(r["service_number"] or "").strip()
                for r in rows
                if str(r["period_start"] or "") == week_start.isoformat() and str(r["service_number"] or "").strip()
            }

            # Collect all aliases/NIKs that belong to this canonical identity.
            aliases = sorted({str(r["nik"] or "").strip() for r in rows if str(r["nik"] or "").strip()})
            if aliases and (not identity["nik"] or identity["nik"].upper().startswith(("NAME-", "TG-"))):
                real = next((nik for nik in aliases if not nik.upper().startswith(("NAME-", "TG-"))), aliases[0])
                identity["nik"] = real

            service_periods = {(str(r["service_number"] or "").strip(), str(r["period_start"] or "").strip()) for r in rows}
            payload_orders = []
            for service_number, period_start in sorted(service_periods):
                if not service_number:
                    continue
                row = conn.execute(
                    """
                    SELECT r.service_number,
                           substr(MAX(r.message_date),1,10) AS message_day,
                           COALESCE(NULLIF(TRIM(m.ticket_id),''), NULLIF(TRIM(o.ticket_id),''), 'MANUAL') AS ticket_id,
                           UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''), ra.sto_code, o.sto, ''))) AS area_label,
                           UPPER(TRIM(COALESCE(ra.sto_code, o.sto, ''))) AS sto
                    FROM report_group_orders r
                    LEFT JOIN report_ticket_metadata m
                      ON m.service_number=r.service_number AND m.period_start=r.period_start
                    LEFT JOIN report_area_orders ra
                      ON ra.service_number=r.service_number AND ra.period_start=r.period_start
                    LEFT JOIN orders o ON o.id=(
                        SELECT o2.id FROM orders o2
                        WHERE o2.service_number=r.service_number
                        ORDER BY o2.id DESC LIMIT 1
                    )
                    WHERE r.service_number=? AND r.period_start=?
                    GROUP BY r.service_number, r.period_start
                    """,
                    (service_number, period_start),
                ).fetchone()
                if not row:
                    continue
                raw_day = str(row["message_day"] or "")
                try:
                    parsed = date.fromisoformat(raw_day)
                    formatted = date_label(parsed)
                except ValueError:
                    formatted = raw_day or "-"
                ticket = str(row["ticket_id"] or "MANUAL").strip()
                if ticket.upper() in {"", "-", "N/A", "NA", "NONE"}:
                    ticket = "MANUAL"
                payload_orders.append({
                    "service_number": str(row["service_number"] or "-"),
                    "ticket_id": ticket,
                    "area_label": str(row["area_label"] or ""),
                    "sto": str(row["sto"] or ""),
                    "date_label": formatted,
                    "raw_day": raw_day,
                })
            payload_orders.sort(key=lambda item: item["raw_day"], reverse=True)
            for item in payload_orders:
                item.pop("raw_day", None)
            payload_orders = payload_orders[:100]
    except sqlite3.Error:
        return {"key": identity_key, "nik": "", "name": "-", "daily": 0, "weekly": 0, "all": 0, "orders": []}

    return {
        "key": identity_key,
        "nik": identity["nik"],
        "name": identity["name"],
        "daily": len(services_daily),
        "weekly": len(services_weekly),
        "all": len(services_all),
        "orders": payload_orders,
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            if BASE_DIR not in resolved.parents and resolved != BASE_DIR:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            body = resolved.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime, _ = mimetypes.guess_type(str(resolved))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route == "/health":
            self._send_json({"ok": True, "database": str(DATABASE_PATH)})
            return
        if route == "/api/dashboard":
            area = (query.get("area") or ["ALL"])[0]
            period = (query.get("period") or ["daily"])[0]
            self._send_json(load_dashboard(area, period))
            return
        if route == "/api/technician":
            identity_key = (query.get("key") or query.get("nik") or [""])[0].strip()
            area = (query.get("area") or ["ALL"])[0]
            if not identity_key:
                self._send_json({"error": "key required"}, HTTPStatus.BAD_REQUEST)
                return
            # Backward compatibility for old callers that still send a raw NIK.
            if not identity_key.startswith(("NIK:", "NAME:")):
                identity_key = f"NIK:{_norm_nik(identity_key)}"
            self._send_json(load_technician(identity_key, area))
            return
        if route in {"/", "/index.html"}:
            self._serve_file(BASE_DIR / "index.html")
            return
        self._serve_file(BASE_DIR / route.lstrip("/"))

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[miniapp] {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    print(f"Kerja Bot Mini App listening on http://{HOST}:{PORT}")
    print(f"Database: {DATABASE_PATH}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
