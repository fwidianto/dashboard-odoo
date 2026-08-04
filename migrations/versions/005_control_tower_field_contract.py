"""Phase 8C-2R2 durable field-contract fingerprint for fetch/apply runs.

Revision ID: 005
Revises: 004
"""

from typing import Sequence, Union

from alembic import op


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE public.ct_fetch_apply_run
        ADD COLUMN field_contract_version TEXT
    """)
    op.execute("""
        ALTER TABLE public.ct_fetch_apply_run
        ADD COLUMN field_contract_fingerprint TEXT
    """)
    op.execute("""
        ALTER TABLE public.ct_fetch_apply_run
        ADD COLUMN field_contract_allowlist_fingerprint TEXT
    """)
    op.execute("""
        UPDATE public.ct_fetch_apply_run
        SET field_contract_version = 'unknown',
            field_contract_fingerprint = NULL,
            field_contract_allowlist_fingerprint = NULL
        WHERE field_contract_version IS NULL
    """)
    op.execute("""
        ALTER TABLE public.ct_fetch_apply_run
        ALTER COLUMN field_contract_version SET NOT NULL
    """)
    op.execute("""
        ALTER TABLE public.ct_fetch_apply_run
        ADD CONSTRAINT ck_ct_fetch_apply_field_contract_fp CHECK (
            field_contract_version = 'unknown'
            OR (length(btrim(field_contract_fingerprint)) = 64
                AND field_contract_fingerprint ~ '^[0-9a-f]{64}$'
                AND length(btrim(field_contract_allowlist_fingerprint)) = 64
                AND field_contract_allowlist_fingerprint ~ '^[0-9a-f]{64}$')
        )
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE public.ct_fetch_apply_run
        DROP CONSTRAINT ck_ct_fetch_apply_field_contract_fp
    """)
    op.execute("ALTER TABLE public.ct_fetch_apply_run DROP COLUMN field_contract_allowlist_fingerprint")
    op.execute("ALTER TABLE public.ct_fetch_apply_run DROP COLUMN field_contract_fingerprint")
    op.execute("ALTER TABLE public.ct_fetch_apply_run DROP COLUMN field_contract_version")
