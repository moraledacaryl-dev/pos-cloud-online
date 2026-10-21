#!/usr/bin/env python3
"""Require the exact production release commit to have completed every main CI gate.

Read-only GitHub Actions preflight. No deployment, database or external app writes.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REQUIRED_WORKFLOWS = (
    "ci.yml",
    "production-equivalent-ci.yml",
    "container-parity-ci.yml",
    "role-matrix-recertification.yml",
    "pass16-staging-ci.yml",
    "pass16-restore-ci.yml",
    "pass16-accounting-replay-ci.yml",
    "pass16-inventory-replay-ci.yml",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ReleaseGateFailure(ValueError):
    """A required production release condition cannot be verified."""


def validate_identity(*, release_sha: str, workflow_sha: str, workflow_ref: str,
                      repository: str, target_environment: str) -> None:
    if target_environment != "production":
        raise ReleaseGateFailure("this CI gate is only valid for production releases")
    if not SHA_RE.fullmatch(release_sha):
        raise ReleaseGateFailure("release SHA must be exactly 40 lowercase hexadecimal characters")
    if not SHA_RE.fullmatch(workflow_sha) or release_sha != workflow_sha:
        raise ReleaseGateFailure("release SHA differs from the workflow-dispatch commit")
    if workflow_ref != "refs/heads/main":
        raise ReleaseGateFailure("production workflow must be dispatched from main")
    if not REPO_RE.fullmatch(repository):
        raise ReleaseGateFailure("GITHUB_REPOSITORY is missing or malformed")


def verify_workflow_runs(payload: object, *, workflow: str, release_sha: str) -> int:
    """Return the newest successful push run ID or fail closed.

    The GitHub endpoint is scoped to a specific workflow and SHA. Validate each
    returned run independently instead of trusting the server-side query alone.
    """
    if not isinstance(payload, dict):
        raise ReleaseGateFailure(f"{workflow}: GitHub returned non-object JSON")
    count = payload.get("total_count")
    entries = payload.get("workflow_runs")
    if type(count) is not int or count < 0 or count > 100:
        raise ReleaseGateFailure(f"{workflow}: result count missing or exceeds one page")
    if not isinstance(entries, list) or len(entries) > 100 or len(entries) > count:
        raise ReleaseGateFailure(f"{workflow}: malformed workflow run collection")

    eligible = [
        run for run in entries
        if isinstance(run, dict)
        and run.get("head_sha") == release_sha
        and run.get("head_branch") == "main"
        and run.get("event") == "push"
    ]
    if not eligible:
        raise ReleaseGateFailure(f"{workflow}: no completed main push run for release SHA")

    def order(run: dict) -> tuple[str, int, int]:
        created = run.get("run_started_at") or run.get("created_at")
        run_id, attempt = run.get("id"), run.get("run_attempt", 1)
        if not isinstance(created, str) or not created:
            raise ReleaseGateFailure(f"{workflow}: missing run timestamp")
        if type(run_id) is not int or type(attempt) is not int:
            raise ReleaseGateFailure(f"{workflow}: invalid run identity")
        return created, run_id, attempt

    latest = max(eligible, key=order)
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise ReleaseGateFailure(
            f"{workflow}: latest run {latest.get('id')} is "
            f"{latest.get('status')}/{latest.get('conclusion')}, not completed/success"
        )
    return latest["id"]


def load_workflow_runs(*, repository: str, workflow: str, release_sha: str,
                       token: str, api_url: str) -> object:
    if not token:
        raise ReleaseGateFailure("GITHUB_TOKEN is required to verify CI evidence")
    if not api_url.startswith("https://"):
        raise ReleaseGateFailure("GitHub API URL must use HTTPS")
    endpoint = (
        f"{api_url.rstrip('/')}/repos/{repository}/actions/workflows/"
        f"{quote(workflow, safe='')}/runs"
        f"?head_sha={release_sha}&event=push&per_page=100"
    )
    request = Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hidden-oasis-pos-release-ci-gate",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        status = getattr(exc, "code", "unavailable")
        raise ReleaseGateFailure(f"{workflow}: GitHub CI query failed ({status})") from exc


def main() -> int:
    release_sha = os.environ.get("RELEASE_SHA", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    try:
        validate_identity(
            release_sha=release_sha,
            workflow_sha=os.environ.get("GITHUB_SHA", ""),
            workflow_ref=os.environ.get("GITHUB_REF", ""),
            repository=repository,
            target_environment=os.environ.get("TARGET_ENVIRONMENT", ""),
        )
        for workflow in REQUIRED_WORKFLOWS:
            payload = load_workflow_runs(
                repository=repository, workflow=workflow, release_sha=release_sha,
                token=os.environ.get("GITHUB_TOKEN", ""),
                api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            )
            run_id = verify_workflow_runs(
                payload, workflow=workflow, release_sha=release_sha
            )
            print(f"CI RELEASE GATE PASS: {workflow} run #{run_id} on {release_sha[:12]}")
    except ReleaseGateFailure as exc:
        print(f"CI RELEASE GATE FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"CI RELEASE GATE: PASS ({len(REQUIRED_WORKFLOWS)} exact-SHA main workflows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
