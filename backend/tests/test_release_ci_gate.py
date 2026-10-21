"""No-network contracts for the fail-closed production CI release gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/verify-release-ci.py"
SPEC = importlib.util.spec_from_file_location("verify_release_ci", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

SHA = "a" * 40
OTHER_SHA = "b" * 40


def make_run(*, sha=SHA, status="completed", conclusion="success",
             branch="main", event="push", run_id=10,
             started="2026-10-22T01:00:00Z", attempt=1):
    return {
        "id": run_id,
        "run_attempt": attempt,
        "head_sha": sha,
        "head_branch": branch,
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "run_started_at": started,
    }


def payload(*runs):
    return {"total_count": len(runs), "workflow_runs": list(runs)}


def test_all_required_workflows_are_unique_and_release_scoped():
    assert len(gate.REQUIRED_WORKFLOWS) == 8
    assert len(set(gate.REQUIRED_WORKFLOWS)) == 8
    assert "ci.yml" in gate.REQUIRED_WORKFLOWS
    assert "production-equivalent-ci.yml" in gate.REQUIRED_WORKFLOWS
    assert "pass16-accounting-replay-ci.yml" in gate.REQUIRED_WORKFLOWS
    assert "pass16-inventory-replay-ci.yml" in gate.REQUIRED_WORKFLOWS


def test_successful_exact_sha_main_push_run_is_accepted():
    assert gate.verify_workflow_runs(
        payload(make_run()), workflow="ci.yml", release_sha=SHA
    ) == 10


@pytest.mark.parametrize(
    "changes",
    [
        {"sha": OTHER_SHA},
        {"branch": "feature/misleading-green"},
        {"event": "pull_request"},
        {"event": "workflow_dispatch"},
    ],
)
def test_wrong_commit_branch_or_event_does_not_satisfy_gate(changes):
    with pytest.raises(gate.ReleaseGateFailure, match="no completed main push"):
        gate.verify_workflow_runs(
            payload(make_run(**changes)), workflow="ci.yml", release_sha=SHA
        )


@pytest.mark.parametrize(
    ("status", "conclusion"),
    [
        ("queued", None),
        ("in_progress", None),
        ("completed", "failure"),
        ("completed", "cancelled"),
        ("completed", "skipped"),
        ("completed", "neutral"),
    ],
)
def test_non_success_results_fail_closed(status, conclusion):
    with pytest.raises(gate.ReleaseGateFailure, match="not completed/success"):
        gate.verify_workflow_runs(
            payload(make_run(status=status, conclusion=conclusion)),
            workflow="ci.yml",
            release_sha=SHA,
        )


def test_later_failed_attempt_cannot_be_masked_by_older_success():
    older = make_run(run_id=100, started="2026-10-22T01:00:00Z")
    newer = make_run(
        run_id=101, started="2026-10-22T02:00:00Z", conclusion="failure"
    )
    with pytest.raises(gate.ReleaseGateFailure, match="latest run 101"):
        gate.verify_workflow_runs(
            payload(newer, older), workflow="ci.yml", release_sha=SHA
        )


def test_newest_success_selected_independent_of_response_order():
    older = make_run(run_id=200, started="2026-10-22T01:00:00Z", conclusion="failure")
    newer = make_run(run_id=201, started="2026-10-22T02:00:00Z")
    assert gate.verify_workflow_runs(
        payload(older, newer), workflow="ci.yml", release_sha=SHA
    ) == 201


@pytest.mark.parametrize(
    "bad_payload",
    [
        None,
        [],
        {},
        {"total_count": "1", "workflow_runs": [make_run()]},
        {"total_count": 101, "workflow_runs": [make_run()]},
        {"total_count": 0, "workflow_runs": [make_run()]},
        {"total_count": 1, "workflow_runs": {}},
        payload(),
    ],
)
def test_missing_or_malformed_evidence_fails_closed(bad_payload):
    with pytest.raises(gate.ReleaseGateFailure):
        gate.verify_workflow_runs(
            bad_payload, workflow="ci.yml", release_sha=SHA
        )


@pytest.mark.parametrize(
    "values",
    [
        {"release_sha": OTHER_SHA},
        {"release_sha": "badsha"},
        {"workflow_sha": OTHER_SHA},
        {"workflow_ref": "refs/heads/feature"},
        {"repository": "not-repo"},
        {"target_environment": "staging"},
    ],
)
def test_mismatched_production_dispatch_is_rejected(values):
    normal = {
        "release_sha": SHA,
        "workflow_sha": SHA,
        "workflow_ref": "refs/heads/main",
        "repository": "moraledacaryl-dev/pos-cloud-online",
        "target_environment": "production",
    }
    with pytest.raises(gate.ReleaseGateFailure):
        gate.validate_identity(**{**normal, **values})


def test_empty_github_token_fails_without_network():
    with pytest.raises(gate.ReleaseGateFailure, match="GITHUB_TOKEN"):
        gate.load_workflow_runs(
            repository="moraledacaryl-dev/pos-cloud-online",
            workflow="ci.yml",
            release_sha=SHA,
            token="",
            api_url="https://api.github.com",
        )


def test_no_http_api_credential_forwarding():
    with pytest.raises(gate.ReleaseGateFailure, match="HTTPS"):
        gate.load_workflow_runs(
            repository="moraledacaryl-dev/pos-cloud-online",
            workflow="ci.yml",
            release_sha=SHA,
            token="not-real",
            api_url="http://untrusted.local",
        )


def test_main_checks_every_workflow_without_network(monkeypatch, capsys):
    monkeypatch.setenv("RELEASE_SHA", SHA)
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_REPOSITORY", "moraledacaryl-dev/pos-cloud-online")
    monkeypatch.setenv("TARGET_ENVIRONMENT", "production")
    touched = []

    def fake_load(**kwargs):
        touched.append(kwargs["workflow"])
        return payload(make_run())

    monkeypatch.setattr(gate, "load_workflow_runs", fake_load)
    assert gate.main() == 0
    assert tuple(touched) == gate.REQUIRED_WORKFLOWS
    assert "CI RELEASE GATE: PASS (8 exact-SHA" in capsys.readouterr().out


def test_main_stops_at_first_missing_required_workflow(monkeypatch, capsys):
    monkeypatch.setenv("RELEASE_SHA", SHA)
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_REPOSITORY", "moraledacaryl-dev/pos-cloud-online")
    monkeypatch.setenv("TARGET_ENVIRONMENT", "production")

    def fake_load(**kwargs):
        if kwargs["workflow"] == "production-equivalent-ci.yml":
            return payload()
        return payload(make_run())

    monkeypatch.setattr(gate, "load_workflow_runs", fake_load)
    assert gate.main() == 1
    assert "CI RELEASE GATE FAIL" in capsys.readouterr().err


def test_deploy_workflow_checks_gates_before_tests_and_ssh():
    workflow = (ROOT / ".github/workflows/deploy-pos.yml").read_text()
    assert "  actions: read" in workflow
    assert "if: ${{ inputs.target_environment == 'production' }}" in workflow
    gate_step = workflow.index("python3 scripts/verify-release-ci.py")
    assert gate_step < workflow.index("name: Frontend contract tests and build")
    assert gate_step < workflow.index("name: Deploy and certify exact SHA")
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
    assert "RELEASE_SHA: ${{ steps.release.outputs.sha }}" in workflow
