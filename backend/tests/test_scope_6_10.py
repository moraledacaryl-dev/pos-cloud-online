from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import Outlet, Register
from app.schemas.common import CashMovementCreate, RegisterSessionClose, RegisterSessionOpen
from app.services.auth_service import create_refresh_token, hash_password, revoke_all_sessions, rotate_refresh_token
from app.models.entities import User
from app.services.pos_service import create_cash_movement, open_register_session, close_register_session


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed_user_and_register(db):
    user = User(username='manager', full_name='Manager', hashed_password=hash_password('secret123'), role='manager', is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    outlet = Outlet(code='RESTO', name='Restaurant', business_unit='F&B', is_active=True)
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    register = Register(outlet_id=outlet.id, code='MAIN', name='Main Drawer', accounting_financial_account_id=1, accounting_financial_account_code='CASH-RESTO', is_active=True)
    db.add(register)
    db.commit()
    db.refresh(register)
    return user, register


def test_refresh_token_rotation():
    db = make_session()
    user, _register = seed_user_and_register(db)
    refresh = create_refresh_token(db, user)
    rotated = rotate_refresh_token(db, refresh)
    assert rotated is not None
    assert rotated['user'].id == user.id
    assert rotated['refresh_token'] != refresh


def test_close_session_keeps_denomination_lines_in_outbox():
    db = make_session()
    user, register = seed_user_and_register(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=500))
    create_cash_movement(db, CashMovementCreate(register_session_id=session['id'], direction='in', movement_type='cash_sale', category='Cash Sale', amount=200))
    closed = close_register_session(db, session['id'], RegisterSessionClose(closing_actual_cash=700, denomination_lines=[{'line_label': '500x1', 'amount': 500, 'sort_order': 1}, {'line_label': '200x1', 'amount': 200, 'sort_order': 2}]), user_id=user.id)
    assert closed['status'] == 'closed'



def test_revoke_all_sessions_invalidates_existing_refresh_tokens():
    db = make_session()
    user, _register = seed_user_and_register(db)
    refresh = create_refresh_token(db, user)
    revoked = revoke_all_sessions(db, user, reason='security')
    assert revoked['ok'] is True
    assert revoked['revoked_tokens'] == 1
    assert rotate_refresh_token(db, refresh) is None
