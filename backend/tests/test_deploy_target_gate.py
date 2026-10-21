"""Deployment target isolation gates; all tests are network/SSH-free."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / 'scripts/deploy-target-gate.py'


def invoke(environment='staging', public_base='https://staging-pos.hiddenoasis.app',
           action='validate-url', body=None):
    return subprocess.run(
        [sys.executable, str(GATE), action], cwd=ROOT,
        env={**os.environ, 'TARGET_ENVIRONMENT': environment, 'PUBLIC_BASE': public_base},
        text=True, input=body, capture_output=True, check=False,
    )


def test_staging_requires_explicit_public_url():
    result = invoke(public_base='')
    assert result.returncode != 0
    assert 'PUBLIC_BASE is missing for staging' in result.stderr


def test_staging_rejects_canonical_production_host_variants():
    for url in ('https://pos.hiddenoasis.app', 'https://POS.HIDDENOASIS.APP:443',
                'https://pos.hiddenoasis.app.', 'https://pos.hiddenoasis.app/?q=1'):
        result = invoke(public_base=url)
        assert result.returncode != 0, url
        assert 'DEPLOY TARGET FAIL:' in result.stderr


def test_staging_accepts_only_canonical_https_origins():
    assert invoke().returncode == 0
    for url in ('http://staging-pos.hiddenoasis.app',
                'https://staging-pos.hiddenoasis.app/api',
                'https://staging-pos.hiddenoasis.app:8443',
                'https://user:secret@staging-pos.hiddenoasis.app',
                'https://staging-pos.hiddenoasis.app/?token=fake'):
        assert invoke(public_base=url).returncode != 0, url


def test_staging_cannot_write_a_production_runtime_even_with_staging_url():
    rejected = invoke(action='validate-runtime', body=json.dumps({'environment': 'production'}))
    assert rejected.returncode != 0
    assert 'does not match TARGET_ENVIRONMENT' in rejected.stderr
    assert 'refusing to touch services' in rejected.stderr
    accepted = invoke(action='validate-runtime', body=json.dumps({'environment': 'staging'}))
    assert accepted.returncode == 0
    assert 'local runtime environment is staging' in accepted.stdout


def test_production_requires_canonical_host_and_runtime():
    assert invoke(environment='production', public_base='https://pos.hiddenoasis.app').returncode == 0
    assert invoke(environment='production', public_base='https://staging-pos.hiddenoasis.app').returncode != 0
    rejected = invoke(environment='production', public_base='https://pos.hiddenoasis.app',
                      action='validate-runtime', body=json.dumps({'environment': 'staging'}))
    assert rejected.returncode != 0


def test_health_payload_must_be_valid_json_object_with_runtime_identity():
    for health in ('not-json', 'null', '{}', '[]'):
        assert invoke(action='validate-runtime', body=health).returncode != 0


def test_deploy_validates_environment_before_backups_or_services():
    release = (ROOT / 'scripts/deploy-release.sh').read_text()
    workflow = (ROOT / '.github/workflows/deploy-pos.yml').read_text()
    assert 'python3 "$DEPLOY_TARGET_GATE_SCRIPT" validate-url' in release
    assert 'python3 "$DEPLOY_TARGET_GATE_SCRIPT" validate-runtime' in release
    assert release.index('validate-runtime') < release.index('run_production_backup\n') if False else True
    assert release.index('validate-runtime') < release.index('run_production_backup\n\n')
    assert release.index('validate-runtime') < release.index('git switch --detach "$EXPECTED_COMMIT"')
    assert 'Verify destination URL before opening SSH' in workflow
    assert 'Checkout deploy target gate' in workflow
    assert workflow.index('Verify destination URL before opening SSH') < workflow.index('Deploy and certify exact SHA')
    assert 'git show "$EXPECTED_COMMIT:scripts/deploy-target-gate.py"' in workflow
    assert 'DEPLOY_TARGET_GATE_SCRIPT="$TARGET_GATE_SCRIPT"' in workflow
    assert 'inputs.target_environment' in workflow
    assert "vars.PUBLIC_BASE || (inputs.target_environment == 'production'" in workflow
