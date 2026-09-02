from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = ROOT / 'scripts' / 'production-backup.sh'
BACKUP_SERVICE = ROOT / 'deploy' / 'systemd' / 'pos-backup.service'
BACKUP_TIMER = ROOT / 'deploy' / 'systemd' / 'pos-backup.timer'


def test_backup_script_is_fail_closed_and_validates_archive():
    text = BACKUP_SCRIPT.read_text()
    assert 'set -euo pipefail' in text
    assert 'hiddenoasis_pos_live' in text
    assert 'pg_dump' in text
    assert '--format=custom' in text
    assert 'pg_restore --list' in text
    assert "umask 077" in text
    assert "chmod 0600" in text
    assert "Retention runs only after a new archive has been created and validated" in text


def test_backup_service_runs_as_postgres_with_restricted_write_path():
    text = BACKUP_SERVICE.read_text()
    assert 'Type=oneshot' in text
    assert 'User=postgres' in text
    assert 'Group=postgres' in text
    assert 'ProtectSystem=strict' in text
    assert 'NoNewPrivileges=true' in text
    assert 'ReadWritePaths=/var/backups/hiddenoasis/pos' in text
    assert 'ExecStart=/usr/bin/bash /opt/pos-cloud-online/scripts/production-backup.sh' in text


def test_backup_timer_is_daily_persistent_and_enabled_via_timers_target():
    text = BACKUP_TIMER.read_text()
    assert 'OnCalendar=*-*-* 02:30:00' in text
    assert 'Persistent=true' in text
    assert 'RandomizedDelaySec=15m' in text
    assert 'Unit=pos-backup.service' in text
    assert 'WantedBy=timers.target' in text
