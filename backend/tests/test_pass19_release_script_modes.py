import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


RELEASE_SCRIPTS = [
    'scripts/deploy-release.sh',
    'scripts/production-certify.sh',
    'scripts/adversarial-production-certify.sh',
    'scripts/pass16-staging-certify.sh',
    'scripts/pass16-restore-rehearsal.sh',
    'scripts/production-backup.sh',
]


def test_release_and_backup_scripts_are_executable():
    for relative_path in RELEASE_SCRIPTS:
        path = REPO_ROOT / relative_path
        mode = path.stat().st_mode
        assert mode & os.X_OK, f'{relative_path} must be executable in Git checkout'


def test_deploy_installs_and_rolls_back_canonical_systemd_units():
    text = (REPO_ROOT / 'scripts' / 'deploy-release.sh').read_text()
    assert "[[ \"$EUID\" -eq 0 ]]" in text
    assert 'install_systemd_units()' in text
    assert text.count('install_systemd_units') >= 3
    assert '/etc/systemd/system/pos-backend.service' in text
    assert '/etc/systemd/system/pos-frontend.service' in text
    assert '/etc/systemd/system/pos-sync-worker.service' in text
    assert '/etc/systemd/system/pos-backup.service' in text
    assert '/etc/systemd/system/pos-backup.timer' in text
    assert 'install -d -o hiddenoasis -g hiddenoasis -m 0750 frontend/.next/cache' in text
    assert "wait_for_http 'http://127.0.0.1:8100/healthz'" in text
    assert "wait_for_http 'http://127.0.0.1:3100/login'" in text
    assert 'systemctl start pos-backup.service' in text
    assert 'systemctl show pos-backup.service --property=Result --value' in text
    assert 'bash scripts/production-backup.sh' not in text


def test_deploy_propagates_the_narrow_accounting_outage_override():
    text = (REPO_ROOT / 'scripts' / 'deploy-release.sh').read_text()
    workflow = (REPO_ROOT / '.github/workflows/deploy-pos.yml').read_text()
    assert 'ALLOW_ACCOUNTING_UNAVAILABLE' in text
    assert 'CERTIFICATION_SCRIPT' in text
    assert 'CERTIFICATION_PHASE=predeploy' in text
    assert 'CERTIFICATION_PHASE=postdeploy' in text
    assert 'allow_accounting_unavailable' in workflow
    assert 'git show "$EXPECTED_COMMIT:scripts/deploy-release.sh"' in workflow
    assert 'git show "$EXPECTED_COMMIT:scripts/production-certify.sh"' in workflow
