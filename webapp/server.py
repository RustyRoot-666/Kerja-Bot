from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "payments.json"
HOST = "0.0.0.0"
PORT = 8080


def load_payments() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("items", [])
    return payload if isinstance(payload, list) else []


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
        route = urlparse(self.path).path
        if route == "/health":
            self._send_json({"ok": True})
            return
        if route == "/api/payments":
            self._send_json({"items": load_payments()})
            return

        if route in {"/", "/index.html"}:
            self._serve_file(BASE_DIR / "index.html")
            return

        relative = route.lstrip("/")
        self._serve_file(BASE_DIR / relative)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[miniapp] {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    print(f"Kerja Bot Mini App listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
