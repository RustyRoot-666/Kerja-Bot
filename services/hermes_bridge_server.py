from __future__ import annotations

import json
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.getenv("HERMES_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.getenv("HERMES_BRIDGE_PORT", "8765"))
HERMES_BIN = os.getenv("HERMES_BIN", "/home/RustyRoot/.local/bin/hermes")
TIMEOUT_SECONDS = int(os.getenv("HERMES_TIMEOUT_SECONDS", "120"))
MAX_PROMPT_CHARS = int(os.getenv("HERMES_MAX_PROMPT_CHARS", "30000"))


class Handler(BaseHTTPRequestHandler):
    server_version = "KerjaBotHermesBridge/1.0"

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True, "hermes_bin": HERMES_BIN})
            return
        self._json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/ask":
            self._json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 200_000:
                self._json({"ok": False, "error": "invalid_body"}, HTTPStatus.BAD_REQUEST)
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            prompt = str(payload.get("prompt") or "").strip()
            if not prompt:
                self._json({"ok": False, "error": "prompt_required"}, HTTPStatus.BAD_REQUEST)
                return
            prompt = prompt[:MAX_PROMPT_CHARS]
            result = subprocess.run(
                [HERMES_BIN, "-z", prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=TIMEOUT_SECONDS,
                env={**os.environ, "HOME": "/home/RustyRoot"},
            )
            if result.returncode != 0:
                self._json(
                    {"ok": False, "error": "hermes_failed", "message": result.stderr.strip()[-1200:]},
                    HTTPStatus.BAD_GATEWAY,
                )
                return
            answer = result.stdout.strip()
            self._json({"ok": True, "answer": answer})
        except subprocess.TimeoutExpired:
            self._json({"ok": False, "error": "timeout"}, HTTPStatus.GATEWAY_TIMEOUT)
        except Exception as exc:
            self._json({"ok": False, "error": "bridge_error", "message": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[hermes-bridge] {self.address_string()} {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[hermes-bridge] listening on http://{HOST}:{PORT} using {HERMES_BIN}")
    server.serve_forever()


if __name__ == "__main__":
    main()
