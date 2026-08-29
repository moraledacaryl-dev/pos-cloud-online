from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_staging_certification_refuses_production_target():
    script = read('scripts/pass16-staging-certify.sh')
    assert 'TARGET_ENVIRONMENT' in script
    assert 'https://pos.hiddenoasis.app' in script
    assert 'refusing to run staging certification against production' in script
    assert 'PASS 16 STAGING AUTOMATED CERTIFICATION: PASS' in script


def test_restore_rehearsal_requires_explicit_non_production_guard():
    script = read('scripts/pass16-restore-rehearsal.sh')
    assert 'I_CONFIRM_NON_PRODUCTION_RESTORE_TARGET' in script
    assert 'hiddenoasis_pos_live' in script
    assert 'refusing a restore target that appears to be production' in script
    assert 'target public schema is not empty' in script
    assert 'RESTORE_ELAPSED_SECONDS=' in script


def test_final_acceptance_document_covers_audit_evidence_categories():
    document = read('docs/PASS_16_OPERATIONAL_ACCEPTANCE.md')
    required = [
        'Staging clone',
        'Backup restore and RTO/RPO',
        'Migration forward/rollback rehearsal',
        'Downstream staging contracts',
        'Physical peripheral acceptance',
        'Offline / dependency recovery',
        'Controlled live pilot',
        'Role acceptance',
        'Final audit rerun',
    ]
    for heading in required:
        assert heading in document
    assert 'Do not run it merely because the repository contains this checklist.' in document
    assert 'code/deployment certified with operational evidence pending' in document


def test_evidence_template_defaults_to_not_run_or_pending():
    template = read('docs/PASS_16_EVIDENCE_TEMPLATE.md')
    assert 'NOT RUN' in template
    assert 'OPERATIONAL ACCEPTANCE: PENDING / PASS / FAIL' in template
    assert 'Do not record passwords, API keys, card details' in template


def test_production_certifier_does_not_overclaim_operational_acceptance():
    script = read('scripts/production-certify.sh')
    assert 'docs/PASS_16_OPERATIONAL_ACCEPTANCE.md' in script
    assert 'proves the deployed code/runtime gate only' in script
    assert 'before declaring literal operational acceptance' in script
