"""Loopback-only synthetic Inventory receiver for the Pass 16 HTTP replay drill.

Keeps stock deltas and accepted event IDs in ephemeral process memory only.
HTTP 503 can be returned before or after acceptance to test POS retry safety.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlsplit

LOCK = Lock()
EVENTS: dict[str, dict] = {}
STOCK_DELTAS: dict[str, Decimal] = {}
ATTEMPTS: list[dict] = []
MODE = "fail_before_accept"
TOKEN = "Pass16InventoryReplayToken2026_ABCDEF012345"
MAX_BODY_BYTES = 65536


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, obj: dict):
        encoded = json.dumps(obj, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _json_body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY_BYTES:
                return None
            item = json.loads(self.rfile.read(size))
            return item if isinstance(item, dict) else None
        except (ValueError, UnicodeDecodeError):
            return None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            return self._send(200, {"ok": True, "fixture": "pass16-synthetic-inventory"})
        if path == "/__ci__/state":
            with LOCK:
                return self._send(200, {
                    "mode": MODE,
                    "accepted": len(EVENTS),
                    "events": sorted(EVENTS),
                    "stock_deltas": {k: str(v) for k, v in sorted(STOCK_DELTAS.items())},
                    "attempts": list(ATTEMPTS),
                })
        return self._send(404, {"error": "unexpected synthetic Inventory route"})

    def do_POST(self):
        global MODE
        path = urlsplit(self.path).path
        body = self._json_body()
        if body is None:
            return self._send(400, {"error": "invalid synthetic request"})

        if path == "/__ci__/mode":
            next_mode = body.get("mode")
            if next_mode not in {"fail_before_accept", "healthy", "accept_then_503"}:
                return self._send(400, {"error": "unrecognized synthetic mode"})
            with LOCK:
                MODE = next_mode
            return self._send(200, {"ok": True})

        if path != "/api/v1/integrations/pos/events":
            return self._send(404, {"error": "unexpected synthetic Inventory route"})
        if self.headers.get("X-Integration-Token") != TOKEN:
            return self._send(401, {"error": "incorrect synthetic Inventory token"})
        event_id = str(body.get("external_event_id") or "")
        sale_id = str(body.get("external_sale_id") or "")
        event_type = str(body.get("event_type") or "")
        if (
            not event_id.startswith("pos:pass16-inventory-order-")
            or not sale_id.startswith("pass16-inventory-order-")
            or body.get("pos_system") != "hidden-oasis-pos"
            or event_type not in {"sale_completed", "sale_voided"}
            or not isinstance(body.get("lines"), list)
            or not body["lines"]
        ):
            return self._send(422, {"error": "invalid synthetic Inventory contract"})
        if event_id != f"pos:{sale_id}:{event_type}":
            return self._send(422, {"error": "unstable synthetic Inventory identity"})
        try:
            deltas = {}
            for line in body["lines"]:
                sku = str(line.get("external_product_id") or "")
                quantity = Decimal(str(line.get("quantity")))
                if sku != "PASS16-COFFEE" or not quantity.is_finite() or quantity <= 0:
                    raise ValueError("bad synthetic SKU/quantity")
                delta = -quantity if event_type == "sale_completed" else quantity
                deltas[sku] = deltas.get(sku, Decimal("0")) + delta
        except (InvalidOperation, ValueError, TypeError):
            return self._send(422, {"error": "invalid stock movement"})
        with LOCK:
            mode = MODE
            if mode == "fail_before_accept":
                ATTEMPTS.append({"event": event_id, "mode": mode, "accepted": False})
                return self._send(503, {"error": "synthetic Inventory unavailable"})
            existing = EVENTS.get(event_id)
            if existing is not None and existing != body:
                return self._send(409, {"error": "event identity conflict"})
            new = existing is None
            if new:
                EVENTS[event_id] = body
                for sku, delta in deltas.items():
                    STOCK_DELTAS[sku] = STOCK_DELTAS.get(sku, Decimal("0")) + delta
            ATTEMPTS.append({"event": event_id, "mode": mode, "accepted": True})
            if mode == "accept_then_503":
                return self._send(503, {"error": "synthetic ACK unavailable after stock commit"})
            return self._send(201 if new else 200, {"ok": True, "deduplicated": not new})

    def log_message(self, _format, *_args):
        return


def main():
    if not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("PASS16_INVENTORY_REPLAY_CI") == "1"
        and os.environ.get("ENVIRONMENT") == "staging"
    ):
        raise RuntimeError("Inventory replay stub restricted to isolated staging CI")
    ThreadingHTTPServer(("127.0.0.1", 18992), Handler).serve_forever()


if __name__ == "__main__":
    main()
