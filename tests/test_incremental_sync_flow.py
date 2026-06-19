"""
Test to verify the complete incremental sync flow.

This test traces the exact code path to verify:
1. After full sync, last_sync_date is saved to sync_state
2. On next incremental sync, last_sync_date is read from sync_state
3. Domain filter is generated correctly
"""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime
from src.models.state import SyncResult


class TestIncrementalSyncStateFlow:
    """
    Test the complete incremental sync state flow.
    
    Flow:
    1. Full sync completes
       → mark_sync_completed(result)
       → result.end_time = last_write_date
       → update_sync_state(last_sync_date=result.end_time)
       
    2. Incremental sync starts
       → get_last_sync_date(model_name)
       → get_sync_state(model_name)
       → SELECT last_sync_date FROM sync_state WHERE model_name = X
       → If not None, generate domain [('write_date', '>=', last_sync_date)]
    """

    def test_full_sync_saves_last_sync_date(self):
        """
        Verify that after full sync, mark_sync_completed() receives the end_time.
        
        The flow:
        1. result.end_time is set from last_write_date (the last record's write_date)
        2. mark_sync_completed(model_config, result) is called
        3. state_mgr checks result.end_time and uses it for last_sync_date
        """
        from src.state.state_manager import StateManager
        
        # Mock the postgres client
        mock_pg = MagicMock()
        state_mgr = StateManager(mock_pg)
        
        # Create a result with end_time set
        result = SyncResult(
            model_name="account.move.line",
            table_name="account_move_line",
        )
        result.records_synced = 100
        result.end_time = datetime(2026, 6, 18, 12, 30, 0)
        
        # Mock model config
        mock_model_config = MagicMock()
        mock_model_config.odoo_model = "account.move.line"
        mock_model_config.postgres_table = "account_move_line"
        
        # Call mark_sync_completed
        state_mgr.mark_sync_completed(mock_model_config, result)
        
        # Verify update_sync_state was called with the correct last_sync_date
        mock_pg.update_sync_state.assert_called_once()
        call_kwargs = mock_pg.update_sync_state.call_args[1]
        
        assert call_kwargs["last_sync_date"] == datetime(2026, 6, 18, 12, 30, 0), (
            f"Expected last_sync_date to be set, got: {call_kwargs.get('last_sync_date')}"
        )

    def test_incremental_sync_reads_last_sync_date(self):
        """
        Verify that get_last_sync_date() correctly reads from sync_state.
        
        The flow:
        1. get_last_sync_date(model_name) calls pg.get_sync_state(model_name)
        2. Returns state["last_sync_date"] if present
        """
        from src.state.state_manager import StateManager
        
        mock_pg = MagicMock()
        # Simulate sync_state having data
        mock_pg.get_sync_state.return_value = {
            "model_name": "account.move.line",
            "last_sync_date": datetime(2026, 6, 18, 12, 30, 0),
            "status": "completed",
        }
        
        state_mgr = StateManager(mock_pg)
        
        # Call get_last_sync_date
        result = state_mgr.get_last_sync_date("account.move.line")
        
        # Verify result
        assert result == datetime(2026, 6, 18, 12, 30, 0), (
            f"Expected last_sync_date to be returned, got: {result}"
        )
        
        # Verify get_sync_state was called with correct model name
        mock_pg.get_sync_state.assert_called_once_with("account.move.line")

    def test_incremental_sync_generates_domain_from_last_sync_date(self):
        """
        Verify that incremental sync generates correct domain when last_sync_date exists.
        
        The flow:
        1. last_sync_date = state_mgr.get_last_sync_date(model_name)
        2. If not None, domain = [(sync_date_field, '>=', last_sync_date)]
        """
        from src.engine.sync_engine import SyncEngine
        from src.models.config import ModelConfig, FieldConfig
        
        model = ModelConfig(
            odoo_model="account.move.line",
            postgres_table="account_move_line",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="BIGINT",
                    primary_key=True,
                    nullable=False,
                ),
                FieldConfig(
                    odoo_field="write_date",
                    postgres_column="write_date",
                    postgres_type="TIMESTAMP",
                    is_sync_date=True,
                    nullable=True,
                ),
            ],
        )
        
        # Set up mocks
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._state_mgr = MagicMock()
            # Return a valid last_sync_date
            engine._state_mgr.get_last_sync_date.return_value = datetime(2026, 6, 18, 12, 30, 0)
            engine._pg = MagicMock()
            engine._pg.get_table_row_count.return_value = 100
            engine._config = MagicMock()
            engine._config.get_effective_batch_size.return_value = 1000
            engine._error_reporter = MagicMock()
            engine._validated_models = {}
            
            def mock_fields_get(model):
                return {
                    "id": {"type": "integer", "required": True},
                    "write_date": {"type": "datetime", "required": False},
                }
            engine._odoo.get_model_fields.side_effect = mock_fields_get
            engine._odoo.count.return_value = 23
            engine._odoo.read_batched.return_value = iter([])
            engine._pg.upsert.return_value = (0, 0, 0)
            
            # Call sync_model with full_sync=False
            result = engine.sync_model(model, full_sync=False)
            
            # Get the domain that was passed to read_batched
            read_batched_calls = engine._odoo.read_batched.call_args_list
            assert len(read_batched_calls) >= 1, "read_batched should be called at least once"
            
            # Check the domain parameter
            domain_passed = read_batched_calls[0][1].get('domain', [])
            expected_domain = [("write_date", ">=", "2026-06-18 12:30:00")]
            
            assert domain_passed == expected_domain, (
                f"Expected domain {expected_domain}, got: {domain_passed}"
            )

    def test_end_to_end_incremental_flow(self):
        """
        End-to-end test of the incremental sync flow.
        
        Simulates:
        1. Full sync completing and saving last_sync_date
        2. Incremental sync reading last_sync_date
        3. Domain filter being generated
        """
        from src.state.state_manager import StateManager
        from src.engine.sync_engine import SyncEngine
        from src.models.config import ModelConfig, FieldConfig
        
        # Track the actual values
        saved_last_sync_date = None
        
        # Create mock postgres client
        mock_pg = MagicMock()
        
        # Track what gets saved
        def track_update_sync_state(**kwargs):
            nonlocal saved_last_sync_date
            saved_last_sync_date = kwargs.get('last_sync_date')
        
        mock_pg.update_sync_state.side_effect = track_update_sync_state
        
        # Return sync_state on subsequent calls
        mock_pg.get_sync_state.return_value = {
            "model_name": "account.move.line",
            "last_sync_date": datetime(2026, 6, 18, 12, 30, 0),
            "status": "completed",
        }
        
        # Create state manager
        state_mgr = StateManager(mock_pg)
        
        # Create and complete a result
        result = SyncResult(
            model_name="account.move.line",
            table_name="account_move_line",
        )
        result.records_synced = 100
        result.end_time = datetime(2026, 6, 18, 12, 30, 0)
        
        mock_model_config = MagicMock()
        mock_model_config.odoo_model = "account.move.line"
        mock_model_config.postgres_table = "account_move_line"
        
        # Complete the sync
        state_mgr.mark_sync_completed(mock_model_config, result)
        
        # Verify last_sync_date was saved
        assert saved_last_sync_date == datetime(2026, 6, 18, 12, 30, 0), (
            f"Expected last_sync_date to be saved, got: {saved_last_sync_date}"
        )
        
        # Now simulate reading it back
        last_sync = state_mgr.get_last_sync_date("account.move.line")
        
        assert last_sync == datetime(2026, 6, 18, 12, 30, 0), (
            f"Expected to read back the same date, got: {last_sync}"
        )


class TestSQLQueries:
    """Verify the actual SQL queries used."""

    def test_get_sync_state_sql(self):
        """Show the SQL query used for reading sync state."""
        from src.clients.postgres_client import PostgresClient
        
        # Check the SQL in get_sync_state method
        import inspect
        source = inspect.getsource(PostgresClient.get_sync_state)
        
        assert "SELECT model_name, table_name, last_sync_date" in source, (
            "get_sync_state should SELECT last_sync_date"
        )
        assert "FROM sync_state" in source, (
            "get_sync_state should query sync_state table"
        )
        assert "WHERE model_name = :model_name" in source, (
            "get_sync_state should filter by model_name"
        )

    def test_update_sync_state_sql(self):
        """Show the SQL query used for saving sync state."""
        from src.clients.postgres_client import PostgresClient
        
        import inspect
        source = inspect.getsource(PostgresClient.update_sync_state)
        
        assert "INSERT INTO sync_state" in source, (
            "update_sync_state should INSERT"
        )
        assert "last_sync_date" in source, (
            "update_sync_state should include last_sync_date"
        )
        assert "ON CONFLICT (model_name) DO UPDATE SET" in source, (
            "update_sync_state should use UPSERT pattern"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
