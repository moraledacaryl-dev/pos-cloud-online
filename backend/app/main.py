import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.logging_config import configure_logging, log_json, set_request_id
from app.core.migrations import ensure_database_ready
from app.core.rate_limit import enforce_rate_limit, init_rate_limiter
from app.core.settings import settings
from app.db.database import SessionLocal, engine
from app.services import sync_service
from app.services.accounting_review_defaults import ensure_accounting_review_routes, install_accounting_review_transport
from app.services.auth_service import ensure_admin_user
from app.services.ops_service import build_health_report
from app.services.permission_service import ensure_permissions_seed
from app.services.pos_service import ensure_default_outlet_registers
import app.models  # noqa: F401

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
install_accounting_review_transport(sync_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail closed before migrations, seeders, integration initialization, or any
    # other startup work can run in production/staging.
    settings.validate_runtime_security()
    init_rate_limiter()
    ensure_database_ready(engine)
    with SessionLocal() as db:
        ensure_permissions_seed(db)
        if settings.bootstrap_enabled:
            ensure_admin_user(db)
        ensure_default_outlet_registers(db)
        ensure_accounting_review_routes(db)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
allowed_origins = settings.cors_origin_list or ['*']
allow_credentials = '*' not in allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get('x-request-id') or str(uuid.uuid4())
    set_request_id(request_id)
    started = time.time()
    client_ip = request.client.host if request.client else 'unknown'
    try:
        enforce_rate_limit(f"{client_ip}:{request.url.path}")
        response = await call_next(request)
    except Exception as exc:
        log_json(logger, 'error', 'request.error', path=request.url.path, method=request.method, error=str(exc))
        raise
    duration_ms = round((time.time() - started) * 1000, 2)
    response.headers['x-request-id'] = request_id
    # Structured access logging is intentionally the request-level record.
    # Business/security audit rows are written explicitly by the services that
    # own those actions; routine GET/poll traffic must not grow the audit table.
    log_json(
        logger,
        'info',
        'request.completed',
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        duration_ms=duration_ms,
        client_ip=client_ip,
    )
    return response


def _require_direct_loopback(request: Request) -> None:
    """Detailed operational health is for direct local monitoring only.

    A reverse-proxied request carries X-Forwarded-For even when Nginx connects
    to Uvicorn over loopback. Reject it so external callers cannot obtain
    database, worker, queue, migration, or downstream dependency details.
    """
    client_ip = request.client.host if request.client else ''
    forwarded_for = (request.headers.get('x-forwarded-for') or '').strip()
    if client_ip not in {'127.0.0.1', '::1'} or forwarded_for:
        raise HTTPException(status_code=404, detail='Not found')


@app.get('/')
def root():
    return {'app': settings.app_name, 'status': 'ok'}


@app.get('/healthz')
def healthz():
    """Public liveness only: process is up and can answer HTTP."""
    return {'ok': True}


@app.get('/api/healthz')
def api_healthz():
    return healthz()


@app.get('/internal/healthz/details')
async def internal_healthz_details(request: Request):
    _require_direct_loopback(request)
    with SessionLocal() as db:
        return await build_health_report(db, engine)


@app.get('/readyz')
async def readyz():
    """Public core readiness with no operational internals."""
    with SessionLocal() as db:
        report = await build_health_report(db, engine)
    sales_ready = bool(report.get('sales_ready'))
    status_code = 200 if sales_ready else 503
    return JSONResponse(status_code=status_code, content={'ok': sales_ready, 'sales_ready': sales_ready})


@app.get('/api/readyz')
async def api_readyz():
    return await readyz()


@app.get('/readyz/integrations')
async def integration_readyz():
    """Public strict dependency readiness with no queue or dependency details."""
    with SessionLocal() as db:
        report = await build_health_report(db, engine)
    ok = bool(report.get('ok'))
    status_code = 200 if ok else 503
    return JSONResponse(status_code=status_code, content={'ok': ok, 'integrations_ready': bool(report.get('integrations_ready'))})


@app.get('/api/readyz/integrations')
async def api_integration_readyz():
    return await integration_readyz()


@app.get('/internal/readyz')
async def internal_readyz(request: Request):
    _require_direct_loopback(request)
    with SessionLocal() as db:
        report = await build_health_report(db, engine)
    status_code = 200 if report.get('sales_ready') else 503
    return JSONResponse(status_code=status_code, content=report)


@app.get('/internal/readyz/integrations')
async def internal_integration_readyz(request: Request):
    _require_direct_loopback(request)
    with SessionLocal() as db:
        report = await build_health_report(db, engine)
    status_code = 200 if report.get('ok') else 503
    return JSONResponse(status_code=status_code, content=report)


app.include_router(api_router, prefix=settings.api_prefix)
