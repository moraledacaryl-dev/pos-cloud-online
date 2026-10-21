#!/usr/bin/env python3
"""Fail-closed POS deploy target checks, without changing any remote state.

validate-url is suitable for GitHub Actions before SSH.
validate-runtime reads the direct local backend health JSON from stdin on the
target host, before service restarts, database backup, or code switch.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlsplit

CANONICAL_PRODUCTION_HOST = "pos.hiddenoasis.app"


def fail(message: str) -> None:
    raise SystemExit(f"DEPLOY TARGET FAIL: {message}")


def selected_target() -> tuple[str, str]:
    environment = os.environ.get("TARGET_ENVIRONMENT", "")
    raw = os.environ.get("PUBLIC_BASE", "")
    if environment not in {"staging", "production"}:
        fail("TARGET_ENVIRONMENT must be staging or production")
    if not raw:
        fail(f"PUBLIC_BASE is missing for {environment}; configure the GitHub environment URL")
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        fail("PUBLIC_BASE is not a valid HTTPS origin")
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        fail("PUBLIC_BASE must be an HTTPS origin without path, credentials, query or nonstandard port")
    if environment == "staging" and host == CANONICAL_PRODUCTION_HOST:
        fail("staging may not target the production POS hostname")
    if environment == "production" and host != CANONICAL_PRODUCTION_HOST:
        fail("production must use the canonical production POS hostname")
    return environment, host


def verify_runtime(environment: str) -> None:
    try:
        body = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        fail("local backend detailed health did not return valid JSON")
    if not isinstance(body, dict):
        fail("local backend health JSON must be an object")
    reported = body.get("environment")
    if reported != environment:
        fail(
            f"backend runtime environment {reported!r} does not match "
            f"TARGET_ENVIRONMENT={environment!r}; refusing to touch services"
        )
    print(f"DEPLOY TARGET PASS: local runtime environment is {environment}")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"validate-url", "validate-runtime"}:
        fail("usage: deploy-target-gate.py validate-url|validate-runtime")
    environment, _host = selected_target()
    if sys.argv[1] == "validate-runtime":
        verify_runtime(environment)
    else:
        print(f"DEPLOY TARGET PASS: configured {environment} origin accepted")


if __name__ == "__main__":
    main()
