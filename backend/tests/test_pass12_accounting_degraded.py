import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.api import registers


def test_accounting_accounts_transport_failure_is_safe_503(monkeypatch):
    async def fail(_db):
        request = httpx.Request('GET', 'https://accounting.hiddenoasis.app/api/financial-accounts')
        raise httpx.ConnectError('connection refused', request=request)

    monkeypatch.setattr(registers, 'fetch_accounting_financial_accounts', fail)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(registers.accounting_accounts(db=object(), user=object()))

    assert exc.value.status_code == 503
    assert exc.value.detail['code'] == 'integration_unavailable'
    assert exc.value.detail['integration'] == 'accounting'
    assert 'connection refused' not in str(exc.value.detail)
    assert 'Local POS selling remains available' in exc.value.detail['message']


def test_accounting_mapping_validation_transport_failure_is_safe_503(monkeypatch):
    async def fail(_db, account_id=None, account_code=None):
        request = httpx.Request('GET', 'https://accounting.hiddenoasis.app/api/financial-accounts')
        raise httpx.ReadTimeout('timed out', request=request)

    monkeypatch.setattr(registers, 'validate_account_mapping', fail)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(registers.accounting_accounts_validate(account_id=1, account_code=None, db=object(), user=object()))

    assert exc.value.status_code == 503
    assert exc.value.detail['code'] == 'integration_unavailable'
    assert 'timed out' not in str(exc.value.detail)
