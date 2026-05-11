from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.services.pos_service import dashboard_summary

router = APIRouter()


@router.get('/summary')
def summary(db: Session = Depends(get_db), user=Depends(require_permissions('dashboard.view'))):
    return dashboard_summary(db)
