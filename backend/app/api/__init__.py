from fastapi import APIRouter

from app.api.approvals import router as approvals_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.cash import router as cash_router
from app.api.catalog import router as catalog_router
from app.api.dashboard import router as dashboard_router
from app.api.customer_display import router as customer_display_router
from app.api.kitchen import router as kitchen_router
from app.api.orders import router as orders_router
from app.api.recipes import router as recipes_router
from app.api.reports import router as reports_router
from app.api.room_charges import router as room_charges_router
from app.api.registers import router as registers_router
from app.api.seed import router as seed_router
from app.api.sessions import router as sessions_router
from app.api.sync import router as sync_router
from app.api.system_settings import router as system_settings_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix='/auth', tags=['auth'])
api_router.include_router(dashboard_router, prefix='/dashboard', tags=['dashboard'])
api_router.include_router(customer_display_router, prefix='/customer-display', tags=['customer-display'])
api_router.include_router(catalog_router, prefix='/catalog', tags=['catalog'])
api_router.include_router(registers_router, prefix='/registers', tags=['registers'])
api_router.include_router(sessions_router, prefix='/register-sessions', tags=['register-sessions'])
api_router.include_router(orders_router, prefix='/orders', tags=['orders'])
api_router.include_router(recipes_router, prefix='/recipes', tags=['recipes'])
api_router.include_router(reports_router, prefix='/reports', tags=['reports'])
api_router.include_router(room_charges_router, prefix='/room-charges', tags=['room-charges'])
api_router.include_router(cash_router, prefix='/cash-movements', tags=['cash-movements'])
api_router.include_router(kitchen_router, prefix='/kitchen', tags=['kitchen'])
api_router.include_router(sync_router, prefix='/sync', tags=['sync'])
api_router.include_router(system_settings_router, prefix='/system-settings', tags=['system-settings'])
api_router.include_router(seed_router, prefix='/seed', tags=['seed'])

api_router.include_router(audit_router, prefix='/audit', tags=['audit'])
api_router.include_router(approvals_router, prefix='/approvals', tags=['approvals'])
