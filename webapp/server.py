from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
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


def load_dashboard(area: str, period: str) -> dict:
    today = datetime.now().date()
    area_sql, area_params = area_condition(area)
    time_sql, time_params, label = time_condition(period, today)

    try:
        with connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.technician_nik AS nik,
                       MAX(r.technician_name) AS name,
                       COUNT(DISTINCT r.service_number) AS total
                FROM report_group_orders r
                WHERE {time_sql} AND {area_sql}
                GROUP BY r.technician_nik
                ORDER BY total DESC, UPPER(MAX(r.technician_name)) ASC
                """,
                (*time_params, *area_params),
            ).fetchall()

            leaderboard = []
            for row in rows:
                nik = str(row["nik"] or "")
                area_row = conn.execute(
                    """
                    SELECT UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''), ra.sto_code))) AS label,
                           UPPER(TRIM(ra.sto_code)) AS sto
                    FROM report_group_orders r
                    LEFT JOIN report_area_orders ra
                      ON ra.service_number=r.service_number AND ra.period_start=r.period_start
                    WHERE r.technician_nik=?
                    ORDER BY r.message_date DESC
                    LIMIT 1
                    """,
                    (nik,),
                ).fetchone()
                leaderboard.append({
                    "nik": nik,
                    "name": str(row["name"] or "-"),
                    "total": int(row["total"] or 0),
                    "area_label": str(area_row["label"] if area_row else ""),
                    "sto": str(area_row["sto"] if area_row else ""),
                })

            trend = []
            week_start, _ = period_bounds(today)
            for offset in range(7):
                day = week_start + timedelta(days=offset)
                result = conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT r.service_number) AS total
                    FROM report_group_orders r
                    WHERE substr(r.message_date,1,10)=? AND {area_sql}
                    """,
                    (day.isoformat(), *area_params),
                ).fetchone()
                trend.append({
                    "date": day.isoformat(),
                    "label": DAYS[day.weekday()],
                    "total": int(result["total"] or 0),
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


def load_technician(nik: str, area: str) -> dict:
    today = datetime.now().date()
    week_start, _ = period_bounds(today)
    area_sql, area_params = area_condition(area)

    def count(conn: sqlite3.Connection, extra_sql: str, extra_params: tuple[str, ...]) -> int:
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT r.service_number) AS total
            FROM report_group_orders r
            WHERE r.technician_nik=? AND {extra_sql} AND {area_sql}
            """,
            (nik, *extra_params, *area_params),
        ).fetchone()
        return int(row["total"] or 0)

    try:
        with connect() as conn:
            identity = conn.execute(
                "SELECT MAX(technician_name) AS name FROM report_group_orders WHERE technician_nik=?",
                (nik,),
            ).fetchone()
            daily = count(conn, "substr(r.message_date,1,10)=?", (today.isoformat(),))
            weekly = count(conn, "r.period_start=?", (week_start.isoformat(),))
            all_count = count(conn, "1=1", ())
            orders = conn.execute(
                f"""
                SELECT r.service_number,
                       substr(r.message_date,1,10) AS message_day,
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
                WHERE r.technician_nik=? AND {area_sql}
                GROUP BY r.service_number, r.period_start
                ORDER BY r.message_date DESC
                LIMIT 100
                """,
                (nik, *area_params),
            ).fetchall()
            payload_orders = []
            for row in orders:
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
                })
    except sqlite3.Error:
        return {"nik": nik, "name": "-", "daily": 0, "weekly": 0, "all": 0, "orders": []}

    return {
        "nik": nik,
        "name": str(identity["name"] if identity and identity["name"] else "-"),
        "daily": daily,
        "weekly": weekly,
        "all": all_count,
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
            nik = (query.get("nik") or [""])[0].strip()
            area = (query.get("area") or ["ALL"])[0]
            if not nik:
                self._send_json({"error": "nik required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(load_technician(nik, area))
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
