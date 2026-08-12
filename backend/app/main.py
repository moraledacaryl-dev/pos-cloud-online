import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.logging_config import configure_logging, log_json, set_request_id
from app.core.migrations import ensure_database_ready
from app.core.rate_limit import enforce_rate_limit, init_rate_limiter
from app.core.settings import settings
from app.db.database import SessionLocal, engine
from app.services import sync_service
from app.services.accounting_review_defaults import ensure_accounting_review_routes, install_accounting_review_transport
from app.services.audit_service import write_audit_log
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
    log_json(logger, 'info', 'request.completed', path=request.url.path, method=request.method, status_code=response.status_code, duration_ms=duration_ms)
    try:
        if request.url.path.startswith(settings.api_prefix):
            with SessionLocal() as db:
                write_audit_log(
                    db,
                    action='http.request',
                    entity_type='request',
                    entity_id=request_id,
                    request_path=request.url.path,
                    request_method=request.method,
                    ip_address=client_ip,
                    status_code=response.status_code,
                    details={'duration_ms': duration_ms},
                )
    except Exception:
        pass
    return response


@app.get('/')
def root():
    return {'app': settings.app_name, 'status': 'ok'}


@app.get('/healthz')
def healthz():
    return {'ok': True, 'environment': settings.environment}


@app.get('/api/healthz')
def api_healthz():
    return healthz()


@app.get('/healthz/details')
async def healthz_details():
    with SessionLocal() as db:
        return await build_health_report(db, engine)


@app.get('/api/healthz/details')
async def api_healthz_details():
    return await healthz_details()


app.include_router(api_router, prefix=settings.api_prefix)
