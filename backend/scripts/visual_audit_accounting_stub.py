"""Local, read-only synthetic Accounting health endpoint for visual CI only.

This intentionally accepts no financial writes and never uses any production
credentials. It lets screenshot reviewers see the healthy POS baseline while
Playwright separately captures dependency-error states by aborting API requests.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path == "/healthz":
            body = json.dumps({"ok": True, "source": "visual-audit-only"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "Unrecognized visual-audit-only route")

    def do_POST(self):
        self.send_error(405, "Visual audit receiver is strictly read-only")

    def do_PUT(self):
        self.send_error(405, "Visual audit receiver is strictly read-only")

    def do_DELETE(self):
        self.send_error(405, "Visual audit receiver is strictly read-only")

    def log_message(self, _format, *_args):
        return


def main():
    if not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("VISUAL_AUDIT_CI") == "1"
        and os.environ.get("ENVIRONMENT") == "development"
        and os.environ.get("DATABASE_URL", "").endswith("/pos_visual_audit")
    ):
        raise RuntimeError("Visual Accounting health stub restricted to disposable visual CI")
    ThreadingHTTPServer(("127.0.0.1", 18993), Handler).serve_forever()


if __name__ == "__main__":
    main()
