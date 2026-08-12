from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.staff_identity import PosUserStaffLink, StaffIdentity
from app.models.entities import User
from app.schemas.staff_identity import StaffEmployeeSyncEnvelope


EXPECTED_SOURCE = 'hidden_oasis_staff_payroll'
EXPECTED_EVENT = 'employee.sync'


def serialize_identity(row: StaffIdentity) -> dict:
    return {
        'id': row.id,
        'source_staff_id': row.source_staff_id,
        'employee_code': row.employee_code,
        'display_name': row.display_name,
        'department': row.department,
        'position': row.position,
        'role': row.staff_role,
        'primary_department': row.primary_department,
        'active': bool(row.is_active),
        'last_external_id': row.last_external_id,
        'last_synced_at': row.last_synced_at_text,
    }


def sync_staff_employees(db: Session, envelope: StaffEmployeeSyncEnvelope) -> dict:
    if envelope.external_source != EXPECTED_SOURCE:
        raise ValueError('Unsupported Staff identity source.')
    if envelope.event_type != EXPECTED_EVENT:
        raise ValueError('Unsupported Staff integration event type.')

    synced: list[StaffIdentity] = []
    for employee in envelope.payload.employees:
        code = employee.employee_code.strip()
        display_name = employee.display_name.strip()
        if not code or not display_name:
            raise ValueError('Employee code and display name are required.')

        by_staff_id = db.query(StaffIdentity).filter(StaffIdentity.source_staff_id == employee.source_staff_id).first()
        by_code = db.query(StaffIdentity).filter(StaffIdentity.employee_code == code).first()
        if by_staff_id and by_code and by_staff_id.id != by_code.id:
            raise ValueError(f'Employee code {code} is already assigned to another Staff identity.')
        if by_code and not by_staff_id and by_code.source_staff_id != employee.source_staff_id:
            raise ValueError(f'Employee code {code} conflicts with a different Staff employee.')

        row = by_staff_id or by_code or StaffIdentity(source_staff_id=employee.source_staff_id, employee_code=code, display_name=display_name)
        row.source_staff_id = employee.source_staff_id
        row.employee_code = code
        row.display_name = display_name
        row.department = employee.department.strip() if employee.department else None
        row.position = employee.position.strip() if employee.position else None
        row.staff_role = employee.role.strip() if employee.role else None
        row.primary_department = employee.primary_department.strip() if employee.primary_department else None
        row.is_active = bool(employee.active)
        row.last_external_id = envelope.external_id
        row.last_synced_at_text = envelope.generated_at
        db.add(row)
        synced.append(row)

    db.commit()
    for row in synced:
        db.refresh(row)
    return {
        'ok': True,
        'external_id': envelope.external_id,
        'synced_count': len(synced),
        'identities': [serialize_identity(row) for row in synced],
    }


def list_staff_identities(db: Session) -> list[dict]:
    rows = db.query(StaffIdentity).order_by(StaffIdentity.display_name.asc(), StaffIdentity.employee_code.asc()).all()
    links = {row.staff_identity_id: row.user_id for row in db.query(PosUserStaffLink).all()}
    return [{**serialize_identity(row), 'linked_user_id': links.get(row.id)} for row in rows]


def list_user_staff_links(db: Session) -> list[dict]:
    rows = db.query(PosUserStaffLink).order_by(PosUserStaffLink.user_id.asc()).all()
    identities = {row.id: row for row in db.query(StaffIdentity).all()}
    result = []
    for row in rows:
        identity = identities.get(row.staff_identity_id)
        result.append({
            'user_id': row.user_id,
            'staff_identity_id': row.staff_identity_id,
            'staff_identity': serialize_identity(identity) if identity else None,
        })
    return result


def set_user_staff_link(db: Session, user_id: int, staff_identity_id: int | None) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise LookupError('POS user not found.')

    existing = db.query(PosUserStaffLink).filter(PosUserStaffLink.user_id == user_id).first()
    if staff_identity_id is None:
        if existing:
            db.delete(existing)
            db.commit()
        return {'user_id': user_id, 'staff_identity_id': None, 'staff_identity': None}

    identity = db.get(StaffIdentity, staff_identity_id)
    if not identity:
        raise LookupError('Staff identity not found.')
    collision = db.query(PosUserStaffLink).filter(PosUserStaffLink.staff_identity_id == staff_identity_id, PosUserStaffLink.user_id != user_id).first()
    if collision:
        raise ValueError('That Staff identity is already linked to another POS user.')

    row = existing or PosUserStaffLink(user_id=user_id, staff_identity_id=staff_identity_id)
    row.staff_identity_id = staff_identity_id
    db.add(row)
    db.commit()
    db.refresh(row)
    return {'user_id': user_id, 'staff_identity_id': identity.id, 'staff_identity': serialize_identity(identity)}
