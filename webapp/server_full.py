from __future__ import annotations

import json
import sys
from datetime import datetime
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


def _ensure_completed_workflows(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS miniapp_completed_workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            technician_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            service_number TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            UNIQUE(telegram_id, action, service_number)
        )
        """
    )


def _save_completed_workflow(payload: dict) -> dict:
    raw_id = str(payload.get("telegram_id") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    service = base.sheet_ref.normalize_key(payload.get("service_number"))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), list) else []

    if not raw_id.isdigit() or action not in {"lengkap", "config", "report", "sto"} or not service:
        return {"ok": False, "error": "invalid_request", "message": "Teknisi, workflow, atau INET tidak valid."}

    clean_outputs: list[tuple[str, str]] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().upper()
        content = str(item.get("content") or "").strip()
        if kind in {"CONFIG", "REPORT", "STO"} and content:
            clean_outputs.append((kind, content))
    if not clean_outputs:
        return {"ok": False, "error": "outputs_required", "message": "Output CONFIG/REPORT/STO belum tersedia."}

    telegram_id = int(raw_id)
    now = datetime.now().isoformat(timespec="seconds")
    with base.connect() as conn:
        technician = conn.execute(
            "SELECT id, telegram_id, nik, name, sto FROM technicians WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()
        if not technician:
            return {"ok": False, "error": "technician_not_registered", "message": "Akun Telegram belum terdaftar sebagai teknisi."}

        _ensure_completed_workflows(conn)
        history_ids: list[int] = []
        for kind, content in clean_outputs:
            existing = conn.execute(
                """
                SELECT id FROM histories
                WHERE telegram_id=? AND service_number=? AND kind=?
                ORDER BY id DESC LIMIT 1
                """,
                (telegram_id, service, kind),
            ).fetchone()
            values = (
                str(data.get("ticket_id") or "MANUAL").strip() or "MANUAL",
                service,
                str(data.get("old_sn") or "").strip(),
                str(data.get("new_sn") or "").strip(),
                str(data.get("ont_type") or "").strip(),
                str(data.get("sto") or technician["sto"] or "").strip().upper(),
                str(data.get("valins_id") or "").strip(),
                content,
            )
            if existing:
                conn.execute(
                    """
                    UPDATE histories
                    SET ticket_id=?, service_number=?, old_sn=?, new_sn=?, ont_type=?,
                        sto=?, valins_id=?, content=?
                    WHERE id=? AND telegram_id=?
                    """,
                    (*values, int(existing["id"]), telegram_id),
                )
                history_ids.append(int(existing["id"]))
            else:
                cur = conn.execute(
                    """
                    INSERT INTO histories (
                        technician_id, telegram_id, kind, ticket_id, service_number,
                        old_sn, new_sn, ont_type, sto, valins_id, content, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(technician["id"]), telegram_id, kind,
                        *values[:-1], content, now,
                    ),
                )
                history_ids.append(int(cur.lastrowid))

        conn.execute(
            """
            INSERT INTO miniapp_completed_workflows
                (technician_id, telegram_id, action, service_number, completed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id, action, service_number) DO UPDATE SET
                technician_id=excluded.technician_id,
                completed_at=excluded.completed_at
            """,
            (int(technician["id"]), telegram_id, action, service, now),
        )

        try:
            conn.execute(
                "DELETE FROM miniapp_workflow_drafts WHERE telegram_id=? AND action=? AND service_number=?",
                (telegram_id, action, service),
            )
        except Exception:
            pass
        conn.commit()

    return {
        "ok": True,
        "action": action,
        "service_number": service,
        "history_ids": history_ids,
        "completed_at": now,
    }


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
    if parsed.path == "/api/workflow-complete":
        try:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8") or "{}")
            result = _save_completed_workflow(payload if isinstance(payload, dict) else {})
            self._send_json(result, HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            print(f"[miniapp] gagal menyimpan workflow selesai: {exc}")
            self._send_json({"ok": False, "error": "workflow_complete_error", "message": "Gagal menyimpan pekerjaan ke history."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return

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
