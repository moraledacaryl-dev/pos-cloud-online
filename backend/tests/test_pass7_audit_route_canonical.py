from fastapi.testclient import TestClient

from app.main import app


def test_audit_collection_uses_canonical_no_trailing_slash_route():
    client = TestClient(app, follow_redirects=False)

    response = client.get('/api/audit?limit=50')

    assert response.status_code == 401
    assert 'location' not in response.headers
