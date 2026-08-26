from sqlalchemy import Column, Index, String

from app.models.entities import ManagerApproval


# Pass 1 evolved the manager_approvals table through Alembic 0008. Keep the ORM
# mapper/metadata aligned with that deployed schema so autogenerate validation
# cannot mistake security-critical grant fields for columns that should be dropped.
_table = ManagerApproval.__table__
_mapper = ManagerApproval.__mapper__

for _name, _length in (
    ('payload_digest', 64),
    ('expires_at_text', 80),
    ('consumed_at_text', 80),
):
    if _name not in _table.c:
        _column = Column(_name, String(_length), nullable=True)
        _table.append_column(_column)
        _mapper.add_property(_name, _column)

for _name, _column_name in (
    ('ix_manager_approvals_payload_digest', 'payload_digest'),
    ('ix_manager_approvals_expires_at_text', 'expires_at_text'),
    ('ix_manager_approvals_consumed_at_text', 'consumed_at_text'),
):
    if not any(index.name == _name for index in _table.indexes):
        Index(_name, _table.c[_column_name], unique=False)
