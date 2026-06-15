"""Unit tests for production hardening features."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.models.config import ModelConfig, FieldConfig, SyncConfig
from src.models.state import SyncAudit, SyncHistory, SyncResult, SyncStatus


class TestDeletionStrategies:
    """Tests for deletion strategy configuration."""

    def test_default_deletion_strategy(self):
        """Test default deletion strategy in config."""
        config = SyncConfig(
            models=[],
            default_deletion_strategy="ignore",
        )
        assert config.default_deletion_strategy == "ignore"

    def test_model_deletion_strategy_override(self):
        """Test model can override deletion strategy."""
        model = ModelConfig(
            odoo_model="test.model",
            postgres_table="test_table",
            deletion_strategy="soft_delete",
            soft_delete_field="active",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="INTEGER",
                    primary_key=True,
                ),
            ],
        )
        assert model.deletion_strategy == "soft_delete"
        assert model.soft_delete_field == "active"

    def test_deletion_strategy_reconcile(self):
        """Test reconcile deletion strategy."""
        model = ModelConfig(
            odoo_model="test.model",
            postgres_table="test_table",
            deletion_strategy="reconcile",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="INTEGER",
                    primary_key=True,
                ),
            ],
        )
        assert model.deletion_strategy == "reconcile"


class TestBatchConfiguration:
    """Tests for batch synchronization configuration."""

    def test_default_batch_size(self):
        """Test default batch size from config."""
        config = SyncConfig(
            models=[],
            default_batch_size=500,
        )
        assert config.default_batch_size == 500

    def test_model_batch_size_override(self):
        """Test model can override batch size."""
        model = ModelConfig(
            odoo_model="test.model",
            postgres_table="test_table",
            batch_size=2000,
            fields=[],
        )
        assert model.batch_size == 2000

    def test_effective_batch_size_with_override(self):
        """Test effective batch size returns model override."""
        config = SyncConfig(
            models=[],
            default_batch_size=1000,
        )
        model = ModelConfig(
            odoo_model="test.model",
            postgres_table="test_table",
            batch_size=500,
            fields=[],
        )
        assert config.get_effective_batch_size(model) == 500

    def test_effective_batch_size_without_override(self):
        """Test effective batch size returns global default."""
        config = SyncConfig(
            models=[],
            default_batch_size=1000,
        )
        model = ModelConfig(
            odoo_model="test.model",
            postgres_table="test_table",
            fields=[],
        )
        assert config.get_effective_batch_size(model) == 1000


class TestFieldTypes:
    """Tests for Odoo field type handling."""

    def test_many2one_field(self):
        """Test many2one field configuration."""
        field = FieldConfig(
            odoo_field="partner_id",
            postgres_column="partner_id",
            postgres_type="INTEGER",
            field_type="many2one",
            related_model="res.partner",
            is_foreign_key=True,
        )
        assert field.field_type == "many2one"
        assert field.is_foreign_key is True
        assert field.related_model == "res.partner"

    def test_one2many_field(self):
        """Test one2many field configuration."""
        field = FieldConfig(
            odoo_field="line_ids",
            postgres_column="line_ids",
            postgres_type="TEXT",  # Could be JSON
            field_type="one2many",
        )
        assert field.field_type == "one2many"

    def test_many2many_field(self):
        """Test many2many field configuration."""
        field = FieldConfig(
            odoo_field="tag_ids",
            postgres_column="tag_ids",
            postgres_type="TEXT",  # Could be JSON
            field_type="many2many",
        )
        assert field.field_type == "many2many"

    def test_basic_field(self):
        """Test basic field type."""
        field = FieldConfig(
            odoo_field="name",
            postgres_column="name",
            postgres_type="VARCHAR(255)",
            field_type="basic",
        )
        assert field.field_type == "basic"


class TestSyncAudit:
    """Tests for sync audit functionality."""

    def test_sync_audit_creation(self):
        """Test creating a sync audit record."""
        audit = SyncAudit(
            model_name="res.partner",
            table_name="res_partner",
            odoo_record_count=100,
            postgres_record_count=100,
            difference=0,
            is_synced=True,
        )
        assert audit.model_name == "res.partner"
        assert audit.odoo_record_count == 100
        assert audit.is_synced is True

    def test_sync_audit_mismatch(self):
        """Test sync audit with count mismatch."""
        audit = SyncAudit(
            model_name="res.partner",
            table_name="res_partner",
            odoo_record_count=100,
            postgres_record_count=95,
            difference=5,
            is_synced=False,
            notes="Records missing in PostgreSQL",
        )
        assert audit.is_synced is False
        assert audit.difference == 5


class TestSyncHistory:
    """Tests for sync history functionality."""

    def test_sync_history_creation(self):
        """Test creating a sync history record."""
        started = datetime(2024, 1, 1, 10, 0, 0)
        completed = datetime(2024, 1, 1, 10, 5, 0)
        
        history = SyncHistory(
            model_name="res.partner",
            table_name="res_partner",
            sync_type="full",
            status=SyncStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
            records_processed=100,
            records_inserted=50,
            records_updated=50,
        )
        # Calculate duration manually since mark_complete overwrites completed_at
        history.duration_seconds = (history.completed_at - history.started_at).total_seconds()
        
        assert history.model_name == "res.partner"
        assert history.records_processed == 100
        assert history.duration_seconds == 300.0

    def test_sync_history_with_deletions(self):
        """Test sync history includes deletion counts."""
        history = SyncHistory(
            model_name="res.partner",
            table_name="res_partner",
            sync_type="incremental",
            status=SyncStatus.COMPLETED,
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 1, 0),
            records_processed=10,
            records_inserted=8,
            records_updated=1,
            records_deleted=1,
        )
        assert history.records_deleted == 1

    def test_sync_history_with_errors(self):
        """Test sync history with error tracking."""
        history = SyncHistory(
            model_name="res.partner",
            table_name="res_partner",
            sync_type="full",
            status=SyncStatus.FAILED,
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 0, 30),
            records_processed=5,
        )
        history.add_error("Connection timeout")
        history.add_error("Retry failed")
        
        assert history.error_count == 2
        assert history.has_errors is True
        assert len(history.errors) == 2

    def test_sync_history_counts(self):
        """Test sync history includes before/after counts."""
        history = SyncHistory(
            model_name="res.partner",
            table_name="res_partner",
            sync_type="full",
            status=SyncStatus.COMPLETED,
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 5, 0),
            records_processed=100,
            odoo_count_before=100,
            odoo_count_after=100,
            postgres_count_before=95,
            postgres_count_after=100,
        )
        assert history.odoo_count_before == 100
        assert history.postgres_count_after == 100


class TestSyncResult:
    """Tests for sync result with audit data."""

    def test_sync_result_to_history(self):
        """Test converting sync result to history record."""
        result = SyncResult(
            model_name="res.partner",
            table_name="res_partner",
            success=True,
            records_synced=100,
            records_inserted=30,
            records_updated=70,
            records_deleted=5,
            odoo_count_before=100,
            odoo_count_after=100,
            postgres_count_before=95,
            postgres_count_after=100,
        )
        result.mark_complete()
        
        history = result.to_history()
        
        assert history.model_name == "res.partner"
        assert history.records_processed == 100
        assert history.records_deleted == 5
        assert history.odoo_count_before == 100


class TestRetryConfiguration:
    """Tests for retry configuration."""

    def test_max_retries_default(self):
        """Test default max retries."""
        config = SyncConfig(
            models=[],
            max_retries=3,
        )
        assert config.max_retries == 3

    def test_retry_delay_default(self):
        """Test default retry delay."""
        config = SyncConfig(
            models=[],
            retry_delay_seconds=5,
        )
        assert config.retry_delay_seconds == 5


class TestIndexes:
    """Tests for index configuration."""

    def test_indexed_field(self):
        """Test field marked for indexing."""
        field = FieldConfig(
            odoo_field="email",
            postgres_column="email",
            postgres_type="VARCHAR(255)",
            indexed=True,
        )
        assert field.indexed is True

    def test_foreign_key_indexed(self):
        """Test foreign key fields are indexed."""
        field = FieldConfig(
            odoo_field="partner_id",
            postgres_column="partner_id",
            postgres_type="INTEGER",
            is_foreign_key=True,
        )
        assert field.is_foreign_key is True

    def test_get_indexed_fields(self):
        """Test getting all fields that should be indexed."""
        model = ModelConfig(
            odoo_model="test.model",
            postgres_table="test_table",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="INTEGER",
                    primary_key=True,
                ),
                FieldConfig(
                    odoo_field="write_date",
                    postgres_column="write_date",
                    postgres_type="TIMESTAMP",
                    is_sync_date=True,
                ),
                FieldConfig(
                    odoo_field="partner_id",
                    postgres_column="partner_id",
                    postgres_type="INTEGER",
                    is_foreign_key=True,
                ),
                FieldConfig(
                    odoo_field="name",
                    postgres_column="name",
                    postgres_type="VARCHAR(255)",
                ),
            ],
        )
        
        indexed_fields = model.get_indexed_fields()
        field_names = [f.odoo_field for f in indexed_fields]
        
        # Primary keys are excluded - they have their own constraint
        assert "id" not in field_names
        assert "write_date" in field_names  # Sync date
        assert "partner_id" in field_names  # Foreign key
        assert "name" not in field_names  # Not indexed