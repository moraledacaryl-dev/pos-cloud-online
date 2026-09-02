from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "adversarial-production-certify.sh"


def test_adversarial_certification_script_exists_and_is_non_destructive():
    text = SCRIPT.read_text(encoding="utf-8")

    required = [
        "/api/auth/me",
        "/api/auth/bootstrap",
        "/api/audit?limit=25",
        "/api/customer-display/main",
        "/api/kitchen/stream?token=legacy-adversarial-test",
        "/api/kitchen/stream-metrics",
        "approved_by_user_id",
        "pos_refresh_token",
        "strict-transport-security",
        "kds_stream_ticket_store",
        "attention_required",
        "integration_reachability",
        "127\\.0\\.0\\.1:${port}",
        "ADVERSARIAL PRODUCTION CERTIFICATION: PASS",
    ]

    for marker in required:
        assert marker in text

    forbidden_mutation_markers = [
        "POST $PUBLIC_BASE/api/orders",
        "POST $PUBLIC_BASE/api/refunds",
        "POST $PUBLIC_BASE/api/cash-movements",
        "DELETE $PUBLIC_BASE/api/orders",
    ]

    for marker in forbidden_mutation_markers:
        assert marker not in text


def test_adversarial_certification_requires_expected_security_codes():
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'http_probe GET "$PUBLIC_BASE/api/auth/me" 401' in text
    assert 'http_probe POST "$PUBLIC_BASE/api/auth/bootstrap" 403' in text
    assert 'http_probe GET "$PUBLIC_BASE/api/audit?limit=25" 401' in text
    assert 'http_probe GET "$PUBLIC_BASE/api/customer-display/main" 401' in text
    assert 'http_probe GET "$PUBLIC_BASE/api/kitchen/stream?token=legacy-adversarial-test" 422' in text
    assert 'http_probe GET "$PUBLIC_BASE/api/kitchen/stream-metrics" 401' in text
