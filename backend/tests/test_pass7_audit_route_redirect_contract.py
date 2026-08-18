from app.main import app


def test_fastapi_redirect_slashes_remains_enabled_but_audit_has_canonical_route():
    # Global redirect-slash behavior can remain enabled for unrelated routes; the
    # audit collection itself must be registered canonically at /api/audit so
    # auth runs on the first request rather than after a 307 redirect.
    assert app.router.redirect_slashes is True
    assert any(getattr(route, 'path', None) == '/api/audit' for route in app.routes)
