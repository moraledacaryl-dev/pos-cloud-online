"""Seed deterministic, non-production data for the isolated visual-audit database.

This script is intentionally only invoked by the screenshot workflow. It creates enough
catalog, register, session, and order density to exercise real operational layouts.
"""
from datetime import date
from decimal import Decimal

from app.db.database import SessionLocal
from app.models.entities import Register
from app.schemas.common import CatalogItemCreate, OrderCreate, OrderLineCreate, RegisterSessionOpen
from app.services.pos_service import (
    create_catalog_item,
    create_order,
    ensure_default_outlet_registers,
    list_catalog_items,
    list_registers,
    list_register_sessions,
    open_register_session,
    set_order_status,
)

CATALOG = [
    ("Classic Beef Burger", "Burgers", "kitchen", "285"),
    ("Double Bacon Cheeseburger with Caramelized Onions", "Burgers", "kitchen", "395"),
    ("Chicken Inasal Rice Bowl", "Rice Meals", "kitchen", "265"),
    ("Seafood Garlic Butter Pasta", "Pasta", "kitchen", "345"),
    ("Truffle Mushroom Cream Pasta — Large", "Pasta", "kitchen", "425"),
    ("Iced Spanish Latte", "Coffee", "bar", "185"),
    ("Salted Caramel Cold Brew", "Coffee", "bar", "195"),
    ("Mango Passionfruit Sparkling Cooler", "Cold Drinks", "bar", "175"),
    ("Hidden Oasis Club Sandwich", "All Day", "kitchen", "325"),
    ("Chocolate Lava Cake with Vanilla Ice Cream", "Desserts", "kitchen", "245"),
    ("Family Breakfast Platter for Four", "Breakfast", "kitchen", "895"),
    ("Fresh Calamansi Juice", "Cold Drinks", "bar", "135"),
]

GUESTS = [
    ("Maria Santos", "Garden 01", "Birthday lunch — please serve cake after mains."),
    ("Walk-in", "Pool 03", "No onions on burger; extra napkins."),
    ("Jonathan dela Cruz", "Hall A-12", "Function hall guest — long reference scenario."),
    ("Ana Reyes", "Room 204", "Guest requested separate drinks and food preparation."),
    ("Corporate Team Alpha", "Garden 08", "Large group order with mixed kitchen and bar items."),
    ("Miguel Garcia", "Pool 01", "Allergy note: no peanuts; confirm with guest before serving."),
    ("Patricia Lim", "Cafe 06", "Takeout after coffee."),
    ("Walk-in", "Cafe 02", "Rush order."),
]


def _id(row):
    return int(row["id"] if isinstance(row, dict) else row.id)


def _is_active(row):
    value = row.get("is_active") if isinstance(row, dict) else getattr(row, "is_active", True)
    return bool(value)


def main():
    db = SessionLocal()
    try:
        ensure_default_outlet_registers(db)

        existing = list_catalog_items(db, active_only=False, available_only=False)
        if not existing:
            for idx, (name, category, station, price) in enumerate(CATALOG, start=1):
                create_catalog_item(db, CatalogItemCreate(
                    menu_item_name=name,
                    display_name=name,
                    sku_code=f"VA-{idx:03d}",
                    category_name=category,
                    module_slug="restaurant",
                    prep_station=station,
                    price=Decimal(price),
                    tax_rate=Decimal("0.12"),
                    service_charge_rate=Decimal("0.10"),
                    sort_order=idx,
                    notes="Deterministic visual-audit fixture",
                ))

        items = list_catalog_items(db, active_only=True, available_only=True)
        registers = [row for row in list_registers(db) if _is_active(row)]
        if not registers:
            raise RuntimeError("Visual audit seed expected at least one default register")

        # Production correctly requires an Accounting drawer mapping before a shift can
        # open. Give the disposable CI register a deterministic fake mapping rather than
        # weakening or bypassing that invariant in application code.
        register = db.get(Register, _id(registers[0]))
        if not register:
            raise RuntimeError("Visual audit seed could not load its default register")
        if register.accounting_financial_account_id is None:
            register.accounting_financial_account_id = 900001
            register.accounting_financial_account_code = "VA-CASH-DRAWER"
            db.commit()

        sessions = list_register_sessions(db, status="open", limit=20)
        if sessions:
            session_id = _id(sessions[0])
        else:
            opened = open_register_session(db, RegisterSessionOpen(
                register_id=register.id,
                business_date=date.today().isoformat(),
                shift_name="Visual Audit Day Shift",
                opening_float=Decimal("5000"),
                opening_note="Deterministic screenshot fixture",
            ), user_id=None)
            session_id = _id(opened)

        # Idempotent inside a fresh CI database and safe if the script is re-run.
        from app.services.pos_service import list_orders
        if not list_orders(db, session_id=session_id, limit=20):
            item_ids = [_id(row) for row in items]
            for idx, (guest, table, note) in enumerate(GUESTS):
                chosen = [item_ids[(idx + offset) % len(item_ids)] for offset in range(3 if idx < 4 else 5)]
                lines = [
                    OrderLineCreate(
                        catalog_item_id=item_id,
                        quantity=Decimal("2") if line_idx == 0 and idx % 2 == 0 else Decimal("1"),
                        note=("Extra sauce on the side; modifier note intentionally long for responsive testing." if line_idx == 1 else None),
                    )
                    for line_idx, item_id in enumerate(chosen)
                ]
                order = create_order(db, OrderCreate(
                    register_session_id=session_id,
                    order_type="dine_in" if idx < 6 else "takeout",
                    source_channel="visual_audit",
                    guest_name=None if guest == "Walk-in" else guest,
                    service_area="Garden" if "Garden" in table else ("Pool" if "Pool" in table else "Cafe"),
                    table_label=table,
                    seat_count=2 + (idx % 5),
                    note=note,
                    lines=lines,
                ), user_id=None)
                if idx in {1, 5}:
                    set_order_status(db, _id(order), "held", user_id=None)

        print(f"visual_audit_catalog_items={len(list_catalog_items(db, active_only=True, available_only=True))}")
        print(f"visual_audit_open_sessions={len(list_register_sessions(db, status='open', limit=20))}")
        print(f"visual_audit_orders={len(list_orders(db, session_id=session_id, limit=50))}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
