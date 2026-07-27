"""Control Tower v0.3 truth and finding lifecycle.

Revision ID: 002
Revises: 001
"""

from typing import Sequence, Union

from alembic import op

from src.control_tower.relation_extractor import CREATE_SCHEMA_SQL
from src.control_tower.v03 import V03_DOWNGRADE_SQL, ensure_v03_schema


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTRACT_DOWNGRADE_SQL = """
DROP TABLE IF EXISTS ct_data_contract_field;
DROP INDEX IF EXISTS idx_ct_snapshot_incremental;
DROP INDEX IF EXISTS idx_ct_snapshot_so_business_date;
DROP INDEX IF EXISTS idx_ct_snapshot_po_business_date;
DROP INDEX IF EXISTS idx_ct_snapshot_account_business_date;
DROP INDEX IF EXISTS idx_ct_snapshot_approval_business_date;
"""


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(CREATE_SCHEMA_SQL)
    ensure_v03_schema(bind)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(V03_DOWNGRADE_SQL)
    op.get_bind().exec_driver_sql(CONTRACT_DOWNGRADE_SQL)
