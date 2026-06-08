from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.models.entities import Permission, Role, RolePermission, User, UserPermissionOverride, UserRole
from app.schemas.permissions import RoleCreate, RoleUpdate


DEFAULT_PERMISSION_DEFS = [
    ('dashboard.view', 'View Dashboard', 'Main'),
    ('pos.use', 'Use POS Terminal', 'POS'),
    ('orders.manage', 'Create and Edit Orders', 'POS'),
    ('orders.void', 'Void Orders', 'POS'),
    ('catalog.view', 'View Catalog', 'Setup'),
    ('catalog.manage', 'Manage Catalog', 'Setup'),
    ('recipes.view', 'View Recipe Library', 'Operations'),
    ('recipes.manage', 'Manage Recipe PDFs', 'Setup'),
    ('registers.view', 'View Registers', 'Setup'),
    ('registers.manage', 'Manage Registers', 'Setup'),
    ('sessions.manage', 'Open and Close Sessions', 'Operations'),
    ('cash.manage', 'Manage Paid In and Paid Out', 'Operations'),
    ('kitchen.view', 'View Kitchen Screen', 'Operations'),
    ('room_charges.view', 'View Room Charge Queue', 'Operations'),
    ('room_charges.manage', 'Manage Room Charge Queue', 'Operations'),
    ('sync.view', 'View Sync Queue', 'Integrations'),
    ('sync.manage', 'Run Sync Queue', 'Integrations'),
    ('settings.manage', 'Manage System Settings', 'Integrations'),
    ('users.manage', 'Manage Users', 'Admin'),
    ('roles.manage', 'Manage Roles', 'Admin'),
    ('reports.view', 'View POS Reports', 'Reports'),
    ('audit.view', 'View Audit Log', 'Reports'),
    ('approvals.view', 'View Manager Approvals', 'Reports'),
    ('approvals.manage', 'Manage Manager Approvals', 'Reports'),
]

DEFAULT_ROLES = [
    ('owner', 'Owner', 'Full access to all POS functions.'),
    ('manager', 'Manager', 'Register, session, cash, and reporting access.'),
    ('cashier', 'Cashier', 'Can use POS, create orders, and collect payments.'),
    ('kitchen', 'Kitchen', 'Kitchen screen access only.'),
]

ROLE_PERMISSION_PRESETS = {
    'owner': {key for key, _label, _group in DEFAULT_PERMISSION_DEFS},
    'manager': {
        'dashboard.view', 'pos.use', 'orders.manage', 'orders.void', 'catalog.view', 'catalog.manage',
        'recipes.view', 'recipes.manage',
        'registers.view', 'registers.manage', 'sessions.manage', 'cash.manage', 'kitchen.view', 'room_charges.view', 'room_charges.manage',
        'sync.view', 'sync.manage', 'settings.manage', 'reports.view', 'audit.view', 'approvals.view', 'approvals.manage',
    },
    'cashier': {
        'dashboard.view', 'pos.use', 'orders.manage', 'catalog.view', 'registers.view', 'sessions.manage', 'cash.manage', 'room_charges.view', 'room_charges.manage',
        'recipes.view',
    },
    'kitchen': {'dashboard.view', 'kitchen.view', 'catalog.view', 'recipes.view'},
}


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _code(value: str | None) -> str:
    return (value or '').strip().lower().replace(' ', '_')


def _serialize_permission(row: Permission) -> dict:
    return {
        'id': row.id,
        'key': row.key,
        'label': row.label,
        'group_name': row.group_name,
        'description': row.description,
        'is_active': bool(row.is_active),
    }


def _serialize_role(row: Role) -> dict:
    permission_keys = sorted([
        link.permission.key
        for link in (row.permissions or [])
        if link.allowed and link.permission and link.permission.is_active
    ])
    return {
        'id': row.id,
        'code': row.code,
        'name': row.name,
        'description': row.description,
        'is_active': bool(row.is_active),
        'permission_keys': permission_keys,
        'permission_count': len(permission_keys),
    }


def ensure_permissions_seed(db: Session):
    existing_permissions = {row.key: row for row in db.query(Permission).all()}
    touched = 0
    for key, label, group_name in DEFAULT_PERMISSION_DEFS:
        row = existing_permissions.get(key)
        if row:
            changed = False
            if row.label != label:
                row.label = label
                changed = True
            if row.group_name != group_name:
                row.group_name = group_name
                changed = True
            if not row.is_active:
                row.is_active = True
                changed = True
            if changed:
                db.add(row)
                touched += 1
            continue
        db.add(Permission(key=key, label=label, group_name=group_name, is_active=True))
        touched += 1

    existing_roles = {row.code: row for row in db.query(Role).all()}
    for code, name, description in DEFAULT_ROLES:
        role = existing_roles.get(code)
        if role:
            changed = False
            if role.name != name:
                role.name = name
                changed = True
            if role.description != description:
                role.description = description
                changed = True
            if not role.is_active:
                role.is_active = True
                changed = True
            if changed:
                db.add(role)
                touched += 1
            continue
        db.add(Role(code=code, name=name, description=description, is_active=True))
        touched += 1

    if touched:
        db.commit()

    permission_by_key = {row.key: row for row in db.query(Permission).all()}
    roles = {row.code: row for row in db.query(Role).all()}

    for role_code, permission_keys in ROLE_PERMISSION_PRESETS.items():
        role = roles.get(role_code)
        if not role:
            continue
        current_links = {
            link.permission.key: link
            for link in db.query(RolePermission).options(selectinload(RolePermission.permission)).filter(RolePermission.role_id == role.id).all()
            if link.permission
        }
        for key in permission_keys:
            permission = permission_by_key.get(key)
            if not permission:
                continue
            link = current_links.get(key)
            if link:
                if not link.allowed:
                    link.allowed = True
                    db.add(link)
                continue
            db.add(RolePermission(role_id=role.id, permission_id=permission.id, allowed=True))
    db.commit()


def list_permissions(db: Session):
    ensure_permissions_seed(db)
    rows = db.query(Permission).filter(Permission.is_active == True).order_by(Permission.group_name.asc(), Permission.key.asc()).all()
    return [_serialize_permission(row) for row in rows]


def list_roles(db: Session, *, active_only: bool = False):
    ensure_permissions_seed(db)
    query = db.query(Role).options(selectinload(Role.permissions).selectinload(RolePermission.permission))
    if active_only:
        query = query.filter(Role.is_active == True)
    rows = query.order_by(Role.name.asc()).all()
    return [_serialize_role(row) for row in rows]


def create_role(db: Session, payload: RoleCreate):
    ensure_permissions_seed(db)
    code = _code(payload.code)
    name = _norm(payload.name)
    if not code:
        raise ValueError('code is required.')
    if not name:
        raise ValueError('name is required.')
    if db.query(Role).filter(Role.code == code).first():
        raise ValueError(f'Role code {code} already exists.')
    if db.query(Role).filter(Role.name == name).first():
        raise ValueError(f'Role name {name} already exists.')
    row = Role(code=code, name=name, description=payload.description, is_active=bool(payload.is_active))
    db.add(row)
    db.commit()
    row = db.query(Role).options(selectinload(Role.permissions).selectinload(RolePermission.permission)).filter(Role.id == row.id).first()
    return _serialize_role(row)


def update_role(db: Session, role_id: int, payload: RoleUpdate):
    row = db.get(Role, int(role_id))
    if not row:
        raise ValueError('Role not found.')
    data = payload.model_dump(exclude_unset=True)
    if 'code' in data:
        code = _code(data.get('code'))
        if not code:
            raise ValueError('code cannot be blank.')
        dup = db.query(Role).filter(Role.code == code, Role.id != row.id).first()
        if dup:
            raise ValueError(f'Role code {code} already exists.')
        row.code = code
    if 'name' in data:
        name = _norm(data.get('name'))
        if not name:
            raise ValueError('name cannot be blank.')
        dup = db.query(Role).filter(Role.name == name, Role.id != row.id).first()
        if dup:
            raise ValueError(f'Role name {name} already exists.')
        row.name = name
    for key in ('description', 'is_active'):
        if key in data:
            setattr(row, key, data.get(key))
    db.add(row)
    db.commit()
    row = db.query(Role).options(selectinload(Role.permissions).selectinload(RolePermission.permission)).filter(Role.id == row.id).first()
    return _serialize_role(row)


def assign_role_permissions(db: Session, role_id: int, permission_keys: list[str]):
    role = db.get(Role, int(role_id))
    if not role:
        raise ValueError('Role not found.')
    ensure_permissions_seed(db)
    permission_by_key = {row.key: row for row in db.query(Permission).filter(Permission.is_active == True).all()}
    desired = {key for key in permission_keys if key in permission_by_key}
    current = db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
    current_by_permission = {row.permission_id: row for row in current}
    desired_ids = {permission_by_key[key].id for key in desired}

    for permission_id, link in current_by_permission.items():
        if permission_id not in desired_ids:
            db.delete(link)
    for key in desired:
        permission = permission_by_key[key]
        if permission.id not in current_by_permission:
            db.add(RolePermission(role_id=role.id, permission_id=permission.id, allowed=True))
    db.commit()
    role = db.query(Role).options(selectinload(Role.permissions).selectinload(RolePermission.permission)).filter(Role.id == role.id).first()
    return _serialize_role(role)


def assign_user_roles(db: Session, user_id: int, role_ids: list[int]):
    user = db.get(User, int(user_id))
    if not user:
        raise ValueError('User not found.')
    valid_ids = {row.id for row in db.query(Role).filter(Role.id.in_(role_ids)).all()} if role_ids else set()
    current = db.query(UserRole).filter(UserRole.user_id == user.id).all()
    current_ids = {row.role_id for row in current}
    for row in current:
        if row.role_id not in valid_ids:
            db.delete(row)
    for role_id in valid_ids:
        if role_id not in current_ids:
            db.add(UserRole(user_id=user.id, role_id=role_id))
    db.commit()


def get_user_roles(db: Session, user_id: int):
    rows = db.query(UserRole).options(selectinload(UserRole.role)).filter(UserRole.user_id == int(user_id)).all()
    roles = [row.role for row in rows if row.role and row.role.is_active]
    return {
        'role_ids': [row.id for row in roles],
        'roles': [{ 'id': row.id, 'code': row.code, 'name': row.name } for row in roles],
    }


def get_user_permission_keys(db: Session, user: User) -> set[str]:
    ensure_permissions_seed(db)
    keys: set[str] = set()
    if user.role in {'owner', 'admin'}:
        return {'*'}

    role_links = db.query(UserRole).options(
        selectinload(UserRole.role).selectinload(Role.permissions).selectinload(RolePermission.permission)
    ).filter(UserRole.user_id == user.id).all()
    for link in role_links:
        if not link.role or not link.role.is_active:
            continue
        for role_permission in link.role.permissions or []:
            if role_permission.allowed and role_permission.permission and role_permission.permission.is_active:
                keys.add(role_permission.permission.key)

    fallback = ROLE_PERMISSION_PRESETS.get(str(user.role or '').lower(), set())
    keys.update(fallback)

    overrides = db.query(UserPermissionOverride).options(selectinload(UserPermissionOverride.permission)).filter(UserPermissionOverride.user_id == user.id).all()
    for override in overrides:
        if not override.permission:
            continue
        if override.is_allowed:
            keys.add(override.permission.key)
        else:
            keys.discard(override.permission.key)
    return keys


def get_user_effective_permissions(db: Session, user_id: int):
    user = db.get(User, int(user_id))
    if not user:
        raise ValueError('User not found.')
    role_meta = get_user_roles(db, user.id)
    return {
        'roles': role_meta,
        'permissions': sorted(get_user_permission_keys(db, user)),
    }
