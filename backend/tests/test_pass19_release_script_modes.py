from pathlib import Path
import os


REPO_ROOT = Path(__file__).resolve().parents[2]


RELEASE_SCRIPTS = [
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
