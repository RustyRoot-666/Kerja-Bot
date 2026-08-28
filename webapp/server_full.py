from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from webapp import server_ext as ext

base = ext.base
_original_get = base.Handler.do_GET
_original_post = base.Handler.do_POST


def _history_rows(telegram_id: int, service_number: str) -> list[dict]:
    technician = base._technician_by_telegram_id(telegram_id)
    if not technician:
        return []
    with base.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, kind, ticket_id, service_number, old_sn, new_sn, ont_type,
                   sto, valins_id, content, created_at
            FROM histories
            WHERE telegram_id=? AND service_number=?
            ORDER BY created_at ASC, id ASC
            """,
            (telegram_id, service_number),
        ).fetchall()
    return [dict(row) for row in rows]


def _update_history(telegram_id: int, history_id: int, content: str) -> bool:
    technician = base._technician_by_telegram_id(telegram_id)
    if not technician:
        return False
    with base.connect() as conn:
        cur = conn.execute(
            "UPDATE histories SET content=? WHERE id=? AND telegram_id=?",
            (content, history_id, telegram_id),
        )
        conn.commit()
        return cur.rowcount > 0


def do_get(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/api/workflow-history":
        query = parse_qs(parsed.query)
        raw_id = (query.get("telegram_id") or [""])[0].strip()
        service = (query.get("service_number") or [""])[0].strip()
        if not raw_id.isdigit() or not service:
            self._send_json({"ok": False, "error": "invalid_request"}, HTTPStatus.BAD_REQUEST)
            return
        rows = _history_rows(int(raw_id), service)
        self._send_json({"ok": True, "service_number": service, "items": rows})
        return
    _original_get(self)


def do_post(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path != "/api/workflow-history":
        _original_post(self)
        return
    try:
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length) if length else b"{}"
        payload = json.loads(body.decode("utf-8") or "{}")
        raw_id = str(payload.get("telegram_id") or "").strip()
        raw_history_id = str(payload.get("history_id") or "").strip()
        content = str(payload.get("content") or "")
        if not raw_id.isdigit() or not raw_history_id.isdigit():
            self._send_json({"ok": False, "error": "invalid_request"}, HTTPStatus.BAD_REQUEST)
            return
        ok = _update_history(int(raw_id), int(raw_history_id), content)
        self._send_json({"ok": ok}, HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND)
    except Exception as exc:
        print(f"[miniapp] gagal update history: {exc}")
        self._send_json({"ok": False, "error": "history_update_error"}, HTTPStatus.INTERNAL_SERVER_ERROR)


base.Handler.do_GET = do_get
base.Handler.do_POST = do_post


if __name__ == "__main__":
    print(f"Kerja Bot Mini App listening on http://{base.HOST}:{base.PORT}")
    print(f"Database: {base.DATABASE_PATH}")
    ThreadingHTTPServer((base.HOST, base.PORT), base.Handler).serve_forever()
