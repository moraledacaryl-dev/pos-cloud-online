"""Provision isolated finance fixtures for the CI browser acceptance database only.

Never run this against a real property database or outside the pos_browser CI
environment. Test data is deliberately created through the ORM because
register/account mappings are normally checked against the live Accounting API.
"""
from __future__ import annotations

import os

from app.db.database import SessionLocal
from app.models.entities import CatalogItem, Outlet, Register

OUTLET_CODE = 'E2E-FINANCE'
REGISTER_CODE = 'E2E-FINANCE'
ITEM_SKU = 'E2E-FINANCE-100'


def main() -> None:
    database_url = os.getenv('DATABASE_URL', '')
    if (
        os.getenv('E2E_FINANCIAL_FIXTURES') != '1'
        or os.getenv('ENVIRONMENT') != 'development'
        or '/pos_browser' not in database_url
    ):
        raise RuntimeError('Financial browser fixtures are allowed only in the isolated pos_browser CI database.')

    with SessionLocal() as db:
        outlet = db.query(Outlet).filter(Outlet.code == OUTLET_CODE).first()
        if outlet is None:
            outlet = Outlet(code=OUTLET_CODE, name='CI Financial Acceptance', business_unit='F&B', is_active=True)
            db.add(outlet)
            db.flush()
        # Independent drawers prevent simultaneous Playwright specs from
        # fighting over PostgreSQL's single-open-session-per-register invariant.
        register_names = (
            (REGISTER_CODE, 'CI Financial Drawer'),
            ('E2E-VISUAL-D', 'CI Desktop Visual Drawer'),
            ('E2E-VISUAL-M', 'CI Mobile Visual Drawer'),
        )
        for register_code, register_name in register_names:
            register = db.query(Register).filter(Register.code == register_code).first()
            if register is None:
                db.add(Register(
                    outlet_id=outlet.id, code=register_code,
                    name=register_name, register_type='cash_drawer',
                    accounting_financial_account_id=1,
                    accounting_financial_account_code='CI-TEST-DRAWER',
                    is_active=True,
                ))
        item = db.query(CatalogItem).filter(CatalogItem.sku_code == ITEM_SKU).first()
        if item is None:
            item = CatalogItem(
                menu_item_name='CI Financial Test Item',
                display_name='CI Financial Test Item',
                sku_code=ITEM_SKU,
                category_name='CI Tests',
                module_slug='restaurant', prep_station='kitchen',
                price='100.00', tax_rate='0', service_charge_rate='0',
                is_active=True, is_available=True,
            )
            db.add(item)
        db.commit()
        print(f'CI financial acceptance fixture ready: register={REGISTER_CODE}, sku={ITEM_SKU}')


if __name__ == '__main__':
    main()
