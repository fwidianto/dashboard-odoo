"""Initial schema migration for sync tables.

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sync tables with indexes."""
    
    # Create sync_state table
    op.create_table(
        'sync_state',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('model_name', sa.Text(), nullable=False),
        sa.Column('table_name', sa.Text(), nullable=False),
        sa.Column('last_sync_date', sa.DateTime(), nullable=True),
        sa.Column('last_sync_id', sa.Integer(), nullable=True),
        sa.Column('record_count', sa.Integer(), server_default='0'),
        sa.Column('status', sa.Text(), server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_name'),
    )
    op.create_index('idx_sync_state_model_name', 'sync_state', ['model_name'])
    
    # Create sync_audit table
    op.create_table(
        'sync_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('model_name', sa.Text(), nullable=False),
        sa.Column('table_name', sa.Text(), nullable=False),
        sa.Column('odoo_record_count', sa.Integer(), server_default='0'),
        sa.Column('postgres_record_count', sa.Integer(), server_default='0'),
        sa.Column('difference', sa.Integer(), server_default='0'),
        sa.Column('is_synced', sa.Boolean(), server_default='true'),
        sa.Column('audit_date', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_sync_audit_model_name', 'sync_audit', ['model_name'])
    op.create_index('idx_sync_audit_audit_date', 'sync_audit', ['audit_date'])
    
    # Create sync_history table
    op.create_table(
        'sync_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('model_name', sa.Text(), nullable=False),
        sa.Column('table_name', sa.Text(), nullable=False),
        sa.Column('sync_type', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('records_processed', sa.Integer(), server_default='0'),
        sa.Column('records_inserted', sa.Integer(), server_default='0'),
        sa.Column('records_updated', sa.Integer(), server_default='0'),
        sa.Column('records_deleted', sa.Integer(), server_default='0'),
        sa.Column('errors', sa.Text(), nullable=True),  # JSON array
        sa.Column('error_count', sa.Integer(), server_default='0'),
        sa.Column('odoo_count_before', sa.Integer(), nullable=True),
        sa.Column('odoo_count_after', sa.Integer(), nullable=True),
        sa.Column('postgres_count_before', sa.Integer(), nullable=True),
        sa.Column('postgres_count_after', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_sync_history_model_name', 'sync_history', ['model_name'])
    op.create_index('idx_sync_history_started_at', 'sync_history', ['started_at'])
    op.create_index('idx_sync_history_status', 'sync_history', ['status'])


def downgrade() -> None:
    """Drop sync tables."""
    op.drop_index('idx_sync_history_status', 'sync_history')
    op.drop_index('idx_sync_history_started_at', 'sync_history')
    op.drop_index('idx_sync_history_model_name', 'sync_history')
    op.drop_table('sync_history')
    
    op.drop_index('idx_sync_audit_audit_date', 'sync_audit')
    op.drop_index('idx_sync_audit_model_name', 'sync_audit')
    op.drop_table('sync_audit')
    
    op.drop_index('idx_sync_state_model_name', 'sync_state')
    op.drop_table('sync_state')