"""Loopback-only, fail-closed synthetic Accounting intake for Pass 16 CI.

Simulates outage, successful acceptance, and persisted acceptance with a lost
HTTP acknowledgement. Contains no credentials or access to production systems.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlsplit

ORDERS: dict[str, dict] = {}
ATTEMPTS: list[dict] = []
MODE = "fail_before_accept"
LOCK = Lock()
MAX_BODY_BYTES = 65536


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, value: dict):
        body = json.dumps(value, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if not 0 < size <= MAX_BODY_BYTES:
            return None
        try:
            obj = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            return None
        return obj if isinstance(obj, dict) else None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            return self._send(200, {"ok": True, "fixture": "pass16-accounting-replay"})
        if path == "/__ci__/state":
            with LOCK:
                return self._send(200, {
                    "mode": MODE,
                    "accepted": len(ORDERS),
                    "identities": sorted(ORDERS),
                    "attempts": list(ATTEMPTS),
                })
        return self._send(404, {"error": "unexpected synthetic Accounting route"})

    def do_POST(self):
        global MODE
        path = urlsplit(self.path).path
        data = self._read_json()
        if data is None:
            return self._send(400, {"error": "invalid fixture request"})

        if path == "/__ci__/mode":
            mode = data.get("mode")
            if mode not in {"fail_before_accept", "healthy", "accept_then_503"}:
                return self._send(400, {"error": "invalid fixture mode"})
            with LOCK:
                MODE = mode
            return self._send(200, {"ok": True})

        if path != "/api/integrations/pos/order":
            return self._send(404, {"error": "unexpected synthetic Accounting route"})

        external_id = str(data.get("external_id") or "")
        order_uuid = str(data.get("order_uuid") or "")
        order_no = str(data.get("order_no") or "")
        if (not external_id.startswith("pass16-replay-") or
                external_id != order_uuid or
                not order_no.startswith("PASS16-REPLAY-") or
                not isinstance(data.get("lines"), list) or
                not data["lines"]):
            return self._send(422, {"error": "invalid synthetic POS order contract"})
        with LOCK:
            current_mode = MODE
            if current_mode == "fail_before_accept":
                ATTEMPTS.append({"external_id": external_id, "mode": current_mode, "accepted": False})
                return self._send(503, {"error": "synthetic Accounting outage"})
            existing = ORDERS.get(external_id)
            if existing is not None and existing != data:
                return self._send(409, {"error": "external_id payload conflict"})
            created = existing is None
            if created:
                ORDERS[external_id] = data
            ATTEMPTS.append({"external_id": external_id, "mode": current_mode, "accepted": True})
            if current_mode == "accept_then_503":
                return self._send(503, {"error": "synthetic acknowledgement lost after commit"})
            return self._send(201 if created else 200, {"ok": True, "external_id": external_id, "deduplicated": not created})

    def log_message(self, _format, *_args):
        return


def main():
    if not (
        os.getenv("GITHUB_ACTIONS") == "true"
        and os.getenv("PASS16_ACCOUNTING_REPLAY_CI") == "1"
        and os.getenv("ENVIRONMENT") == "staging"
    ):
        raise RuntimeError("Pass 16 Accounting replay stub requires isolated staging CI")
    ThreadingHTTPServer(("127.0.0.1", 18991), Handler).serve_forever()


if __name__ == "__main__":
    main()
