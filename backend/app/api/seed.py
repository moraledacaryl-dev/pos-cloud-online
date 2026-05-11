from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.services.pos_service import ensure_default_outlet_registers

router = APIRouter()


@router.post('/defaults')
def seed_defaults(db: Session = Depends(get_db), user=Depends(require_permissions('settings.manage'))):
    ensure_default_outlet_registers(db)
    return {'ok': True}
