from fastapi.routing import APIRoute

from app.main import app


def test_audit_collection_route_is_registered_without_redirect_path():
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert '/api/audit' in paths
