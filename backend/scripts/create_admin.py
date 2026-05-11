#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import os

import app.models  # noqa: F401
from app.db.database import SessionLocal
from app.models.entities import User
from app.services.auth_service import hash_password
from app.services.permission_service import assign_user_roles, ensure_permissions_seed, list_roles


def main() -> int:
    parser = argparse.ArgumentParser(description='Create or update a production POS admin user.')
    parser.add_argument('--username', default=os.getenv('ADMIN_USERNAME', 'admin'))
    parser.add_argument('--full-name', default=os.getenv('ADMIN_FULL_NAME', 'System Admin'))
    parser.add_argument('--role', default=os.getenv('ADMIN_ROLE', 'owner'))
    parser.add_argument('--password', default=os.getenv('ADMIN_PASSWORD'))
    args = parser.parse_args()

    password = args.password or getpass.getpass('Admin password: ')
    if len(password) < 12:
        raise SystemExit('Admin password must be at least 12 characters.')

    with SessionLocal() as db:
        ensure_permissions_seed(db)
        user = db.query(User).filter(User.username == args.username).first()
        if not user:
            user = User(
                username=args.username,
                full_name=args.full_name,
                hashed_password=hash_password(password),
                role=args.role,
                is_active=True,
                session_version=1,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            action = 'created'
        else:
            user.full_name = args.full_name
            user.hashed_password = hash_password(password)
            user.role = args.role
            user.is_active = True
            user.session_version = int(user.session_version or 1) + 1
            db.add(user)
            db.commit()
            db.refresh(user)
            action = 'updated'

        roles = list_roles(db)
        role_row = next((row for row in roles if row.get('code') == args.role), None)
        if role_row:
            assign_user_roles(db, user.id, [int(role_row['id'])])

    print(f'POS admin user {args.username!r} {action}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
