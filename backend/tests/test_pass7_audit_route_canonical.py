import asyncio

import httpx

from app.main import app


def test_audit_collection_uses_canonical_no_trailing_slash_route():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test', follow_redirects=False) as client:
            return await client.get('/api/audit?limit=50')

    response = asyncio.run(request())

    assert response.status_code == 401
    assert 'location' not in response.headers
