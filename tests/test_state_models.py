"""Unit tests for sync state models."""

import pytest
from datetime import datetime

from src.models.state import SyncState, SyncStatus, SyncResult


class TestSyncStatus:
    """Tests for SyncStatus enum."""

    def test_all_statuses_defined(self):
        """Test all expected statuses are defined."""
        assert SyncStatus.PENDING.value == "pending"
        assert SyncStatus.RUNNING.value == "running"
        assert SyncStatus.COMPLETED.value == "completed"
        assert SyncStatus.FAILED.value == "failed"
        assert SyncStatus.PARTIAL.value == "partial"


class TestSyncState:
    """Tests for SyncState model."""

    def test_default_state(self):
        """Test creating a state with defaults."""
        state = SyncState(
            model_name="res.partner",
            table_name="res_partner",
        )
        assert state.model_name == "res.partner"
        assert state.table_name == "res_partner"
        assert state.record_count == 0
        assert state.status == SyncStatus.PENDING
        assert state.last_sync_date is None
        assert state.last_sync_id is None

    def test_full_state(self):
        """Test creating a state with all fields."""
        last_sync = datetime(2024, 1, 15, 10, 30, 0)
        state = SyncState(
            model_name="res.partner",
            table_name="res_partner",
            last_sync_date=last_sync,
            last_sync_id=100,
            record_count=1500,
            status=SyncStatus.COMPLETED,
            error_message=None,
        )
        assert state.last_sync_date == last_sync
        assert state.last_sync_id == 100
        assert state.record_count == 1500
        assert state.status == "completed"


class TestSyncResult:
    """Tests for SyncResult model."""

    def test_default_result(self):
        """Test creating a result with defaults."""
        result = SyncResult(
            model_name="res.partner",
            table_name="res_partner",
            success=True,
        )
        assert result.model_name == "res.partner"
        assert result.table_name == "res_partner"
        assert result.success is True
        assert result.records_synced == 0
        assert result.records_inserted == 0
        assert result.records_updated == 0
        assert len(result.errors) == 0
        assert result.start_time is not None
        assert result.end_time is None

    def test_mark_complete(self):
        """Test marking result as complete."""
        result = SyncResult(
            model_name="res.partner",
            table_name="res_partner",
            success=True,
        )
        result.mark_complete()
        
        assert result.end_time is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    def test_add_error(self):
        """Test adding errors to result."""
        result = SyncResult(
            model_name="res.partner",
            table_name="res_partner",
            success=True,
        )
        result.add_error("Connection timeout")
        result.add_error("Invalid data format")
        
        assert len(result.errors) == 2
        assert result.has_errors is True

    def test_result_with_statistics(self):
        """Test result with sync statistics."""
        result = SyncResult(
            model_name="res.partner",
            table_name="res_partner",
            success=True,
            records_synced=100,
            records_inserted=30,
            records_updated=70,
        )
        result.mark_complete()
        
        assert result.records_synced == 100
        assert result.records_inserted == 30
        assert result.records_updated == 70
        assert result.has_errors is False

    def test_failed_result(self):
        """Test result for failed sync."""
        result = SyncResult(
            model_name="res.partner",
            table_name="res_partner",
            success=False,
        )
        result.add_error("Odoo API error: Model not found")
        result.mark_complete()
        
        assert result.success is False
        assert result.has_errors is True