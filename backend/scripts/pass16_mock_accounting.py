"""CI-only local Accounting health stub for the isolated Pass 16 staging runtime.

Never points at or writes to a real downstream Accounting service.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") == "/healthz":
            self._respond(200, {"ok": True, "source": "pass16-synthetic-accounting"})
        else:
            self._respond(200, {"ok": True, "items": [], "results": [], "bookings": [], "data": []})

    def do_POST(self):
        self._respond(200, {"ok": True, "items": [], "results": [], "bookings": [], "data": []})

    def _respond(self, status: int, value: dict):
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("ENVIRONMENT") != "staging"
            or os.environ.get("PASS16_STAGING_CI") != "1"):
        raise RuntimeError("Pass 16 Accounting stub only runs in isolated staging GitHub CI")
    ThreadingHTTPServer(("127.0.0.1", 18990), Handler).serve_forever()


if __name__ == "__main__":
    main()
