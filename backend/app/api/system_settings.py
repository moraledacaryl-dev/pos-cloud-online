from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_any_permissions, require_permissions
from app.db.database import get_db
from app.schemas.common import SystemSettingsUpdate
from app.services.pos_service import save_setting_json, setting_json

router = APIRouter()
SENSITIVE_SYNC_FIELDS = {'api_token', 'integration_secret'}


def public_accounting_sync(settings: dict | None) -> dict:
    public = dict(settings or {})
    for field in SENSITIVE_SYNC_FIELDS:
        value = public.pop(field, '')
        public[f'{field}_configured'] = bool(value)
    return public

DEFAULT_TABLE_LAYOUT = {
    'areas': ['Lobby', 'Terrace', 'Garden', 'Gazebo', 'Above Kitchen', 'Pool', 'Room Service', 'Takeout'],
    'tables': [
        {'id': 'l1', 'area': 'Lobby', 'code': 'L1', 'x': 16, 'y': 24, 'seats': 4, 'shape': 'round'},
        {'id': 'l2', 'area': 'Lobby', 'code': 'L2', 'x': 56, 'y': 26, 'seats': 4, 'shape': 'round'},
        {'id': 'lounge', 'area': 'Lobby', 'code': 'Lounge', 'x': 32, 'y': 62, 'seats': 6, 'shape': 'sofa'},
        {'id': 'tr1', 'area': 'Terrace', 'code': 'TR1', 'x': 12, 'y': 22, 'seats': 2, 'shape': 'umbrella'},
        {'id': 'tr2', 'area': 'Terrace', 'code': 'TR2', 'x': 46, 'y': 26, 'seats': 4, 'shape': 'umbrella'},
        {'id': 'tr3', 'area': 'Terrace', 'code': 'TR3', 'x': 72, 'y': 58, 'seats': 4, 'shape': 'square'},
        {'id': 'g1', 'area': 'Garden', 'code': 'G1', 'x': 16, 'y': 30, 'seats': 4, 'shape': 'umbrella'},
        {'id': 'g2', 'area': 'Garden', 'code': 'G2', 'x': 48, 'y': 18, 'seats': 4, 'shape': 'umbrella'},
        {'id': 'g3', 'area': 'Garden', 'code': 'G3', 'x': 68, 'y': 64, 'seats': 6, 'shape': 'round'},
        {'id': 'gz1', 'area': 'Gazebo', 'code': 'Gazebo 1', 'x': 30, 'y': 36, 'seats': 8, 'shape': 'gazebo'},
        {'id': 'gz2', 'area': 'Gazebo', 'code': 'Gazebo 2', 'x': 66, 'y': 58, 'seats': 6, 'shape': 'gazebo'},
        {'id': 'ak1', 'area': 'Above Kitchen', 'code': 'AK1', 'x': 18, 'y': 24, 'seats': 4, 'shape': 'square'},
        {'id': 'ak2', 'area': 'Above Kitchen', 'code': 'AK2', 'x': 58, 'y': 28, 'seats': 4, 'shape': 'square'},
        {'id': 'ak3', 'area': 'Above Kitchen', 'code': 'AK3', 'x': 42, 'y': 66, 'seats': 6, 'shape': 'rectangle'},
        {'id': 'p1', 'area': 'Pool', 'code': 'Pool 1', 'x': 18, 'y': 26, 'seats': 4, 'shape': 'umbrella'},
        {'id': 'p2', 'area': 'Pool', 'code': 'Pool 2', 'x': 52, 'y': 24, 'seats': 4, 'shape': 'umbrella'},
        {'id': 'cabana', 'area': 'Pool', 'code': 'Cabana', 'x': 68, 'y': 66, 'seats': 6, 'shape': 'cabana'},
    ],
}


@router.get('')
def get_settings(db: Session = Depends(get_db), user=Depends(require_permissions('settings.manage'))):
    return {
        'accounting_sync': public_accounting_sync(setting_json(db, 'accounting_sync', default={})),
        'ui_preferences': setting_json(db, 'ui_preferences', default={}),
    }


@router.put('')
def update_settings(payload: SystemSettingsUpdate, db: Session = Depends(get_db), current_user=Depends(require_permissions('settings.manage'))):
    data = payload.model_dump(exclude_unset=True)
    if 'accounting_sync' in data:
        accounting_sync = data['accounting_sync'] or {}
        stored_sync = setting_json(db, 'accounting_sync', default={}) or {}
        mode = str(accounting_sync.get('mode') or 'current_erp').strip().lower()
        if mode != 'current_erp':
            raise HTTPException(status_code=400, detail='Only current_erp accounting sync is supported. The integration facade is not available yet.')
        next_sync = {**stored_sync, **accounting_sync, 'mode': 'current_erp'}
        for field in SENSITIVE_SYNC_FIELDS:
            next_sync.pop(f'{field}_configured', None)
            if not accounting_sync.get(field):
                if stored_sync.get(field):
                    next_sync[field] = stored_sync[field]
                else:
                    next_sync.pop(field, None)
        save_setting_json(db, 'accounting_sync', next_sync, username=getattr(current_user, 'username', None))
    if 'ui_preferences' in data:
        save_setting_json(db, 'ui_preferences', data['ui_preferences'] or {}, username=getattr(current_user, 'username', None))
    return {
        'ok': True,
        'accounting_sync': public_accounting_sync(setting_json(db, 'accounting_sync', default={})),
        'ui_preferences': setting_json(db, 'ui_preferences', default={}),
    }


@router.get('/table-layout')
def get_table_layout(db: Session = Depends(get_db), user=Depends(require_any_permissions('pos.use', 'orders.manage', 'settings.manage'))):
    prefs = setting_json(db, 'ui_preferences', default={}) or {}
    return prefs.get('table_layout') or DEFAULT_TABLE_LAYOUT


@router.put('/table-layout')
def update_table_layout(payload: dict, db: Session = Depends(get_db), current_user=Depends(require_permissions('settings.manage'))):
    prefs = setting_json(db, 'ui_preferences', default={}) or {}
    layout = {
        'areas': payload.get('areas') if isinstance(payload.get('areas'), list) else DEFAULT_TABLE_LAYOUT['areas'],
        'tables': payload.get('tables') if isinstance(payload.get('tables'), list) else [],
    }
    prefs['table_layout'] = layout
    save_setting_json(db, 'ui_preferences', prefs, username=getattr(current_user, 'username', None))
    return layout
