from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import AuditLog
from app.services.audit_service import list_audit_logs


def test_audit_cursor_pages_are_stable_and_bounded():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine, tables=[AuditLog.__table__])
    Session = sessionmaker(bind=engine, future=True)
    with Session() as db:
        for idx in range(1, 8):
            db.add(AuditLog(action=f'action.{idx}', entity_type='test', entity_id=str(idx), details_json='{}'))
        db.commit()

        first = list_audit_logs(db, limit=3)
        assert len(first['items']) == 3
        assert first['next_cursor'] == first['items'][-1]['id']

        second = list_audit_logs(db, limit=3, before_id=first['next_cursor'])
        assert len(second['items']) == 3
        assert {row['id'] for row in first['items']}.isdisjoint({row['id'] for row in second['items']})
        assert max(row['id'] for row in second['items']) < min(row['id'] for row in first['items'])
