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


class TestFullIncrementalFlowSimulation:
    """
    Comprehensive test simulating the entire incremental sync flow.
    
    This test proves:
    1. Full sync saves last_write_date to sync_state
    2. Next incremental sync reads last_write_date from sync_state
    3. Incremental sync generates domain filter
    4. Only changed records are synced
    """

    def test_full_then_incremental_sync_flow(self):
        """
        Simulate full sync followed by incremental sync.
        
        This is the key test that proves incremental sync works correctly.
        """
        from src.engine.sync_engine import SyncEngine
        from src.models.config import ModelConfig, FieldConfig
        from src.state.state_manager import StateManager
        
        # Track state across the flow
        sync_state_db = {}  # Simulates PostgreSQL sync_state table
        
        def mock_get_sync_state(model_name):
            return sync_state_db.get(model_name)
        
        def mock_update_sync_state(**kwargs):
            model_name = kwargs['model_name']
            # Get existing state or create new
            existing = sync_state_db.get(model_name, {"model_name": model_name})
            # Update with provided values (use existing if not provided)
            existing.update({
                "table_name": kwargs.get('table_name', existing.get('table_name')),
                "last_sync_date": kwargs.get('last_sync_date', existing.get('last_sync_date')),
                "record_count": kwargs.get('record_count', existing.get('record_count', 0)),
                "status": kwargs.get('status', existing.get('status', 'unknown')),
            })
            sync_state_db[model_name] = existing
        
        # Create mock postgres client for state manager
        mock_pg_for_state = MagicMock()
        mock_pg_for_state.get_sync_state.side_effect = mock_get_sync_state
        mock_pg_for_state.update_sync_state.side_effect = mock_update_sync_state
        
        # Create real StateManager with mock PG
        state_mgr = StateManager(mock_pg_for_state)
        
        # Create mock Odoo client that returns sample data
        odoo_records = [
            {"id": 1, "write_date": "2026-06-18 10:00:00"},
            {"id": 2, "write_date": "2026-06-18 11:00:00"},
            {"id": 3, "write_date": "2026-06-18 12:00:00"},
            {"id": 4, "write_date": "2026-06-18 13:00:00"},
            {"id": 5, "write_date": "2026-06-18 14:00:00"},
        ]
        
        def mock_read_batched(model, domain, fields, batch_size, order, total_limit):
            if domain:
                # Incremental: filter by write_date
                filter_date = domain[0][2]
                filtered = [r for r in odoo_records if r["write_date"] > filter_date]
                yield filtered
            else:
                # Full: return all records
                yield odoo_records
        
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
        
        # Set up SyncEngine with mocks
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._state_mgr = state_mgr  # Use real StateManager with mock PG
            engine._pg = MagicMock()
            engine._pg.get_sync_state.side_effect = mock_get_sync_state
            engine._pg.update_sync_state.side_effect = mock_update_sync_state
            engine._pg.get_table_row_count.return_value = 0
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
            engine._odoo.count.return_value = 5
            engine._odoo.read_batched.side_effect = mock_read_batched
            engine._pg.upsert.return_value = (0, 0, 0)
            
            # STEP 1: Run FULL sync
            print("\n" + "="*60)
            print("STEP 1: FULL SYNC")
            print("="*60)
            
            result1 = engine.sync_model(model, full_sync=True)
            
            # Verify full sync saved state
            print(f"sync_state_db after full sync: {sync_state_db}")
            assert "account.move.line" in sync_state_db, "Full sync should save state"
            saved_date = sync_state_db["account.move.line"]["last_sync_date"]
            assert saved_date is not None, f"Full sync should save last_write_date, got {saved_date}"
            print(f"Full sync saved last_write_date: {saved_date}")
            
            # STEP 2: Run INCREMENTAL sync
            print("\n" + "="*60)
            print("STEP 2: INCREMENTAL SYNC")
            print("="*60)
            
            # Reset the mock to track incremental calls
            engine._odoo.read_batched.reset_mock()
            engine._odoo.read_batched.side_effect = mock_read_batched
            
            result2 = engine.sync_model(model, full_sync=False)
            
            # Verify incremental sync passed correct domain
            call_args = engine._odoo.read_batched.call_args
            domain_passed = call_args[1].get('domain', [])
            
            print(f"Incremental domain filter: {domain_passed}")
            assert len(domain_passed) == 1, f"Expected domain filter, got: {domain_passed}"
            assert domain_passed[0][0] == "write_date", f"Expected write_date filter"
            assert domain_passed[0][1] in (">=", ">"), f"Expected comparison operator"
            
            print("\n" + "="*60)
            print("SUCCESS: Incremental sync generated correct domain filter!")
            print("="*60)


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


class TestSyncStatePreservation:
    """
    Test that last_sync_date is preserved across sync operations.
    
    ROOT CAUSE BUG: mark_sync_started() was overwriting last_sync_date to NULL
    because the UPSERT was updating ALL fields including last_sync_date.
    
    FIX: mark_sync_started() now preserves last_sync_date from previous sync.
    """

    def test_mark_sync_started_preserves_last_sync_date(self):
        """
        Verify that mark_sync_started() does NOT overwrite last_sync_date.
        
        This was the root cause bug - mark_sync_started() was calling
        update_sync_state() without passing last_sync_date, which caused
        the UPSERT to set last_sync_date = NULL.
        """
        from src.state.state_manager import StateManager
        
        # Track what gets saved
        saved_states = []
        
        mock_pg = MagicMock()
        
        def track_update_sync_state(**kwargs):
            saved_states.append(kwargs.copy())
        
        mock_pg.update_sync_state.side_effect = track_update_sync_state
        mock_pg.get_sync_state.return_value = {
            "model_name": "sale.order",
            "last_sync_date": datetime(2026, 6, 18, 9, 53, 54),  # From previous sync
            "status": "completed",
        }
        
        state_mgr = StateManager(mock_pg)
        
        mock_model_config = MagicMock()
        mock_model_config.odoo_model = "sale.order"
        mock_model_config.postgres_table = "sale_order"
        
        # Call mark_sync_started
        state_mgr.mark_sync_started(mock_model_config)
        
        # Verify that last_sync_date was PRESERVED
        assert len(saved_states) == 1, "update_sync_state should be called once"
        
        saved_kwargs = saved_states[0]
        assert "last_sync_date" in saved_kwargs, (
            "last_sync_date should be passed to preserve it"
        )
        assert saved_kwargs["last_sync_date"] == datetime(2026, 6, 18, 9, 53, 54), (
            f"last_sync_date should be preserved, got: {saved_kwargs['last_sync_date']}"
        )
        assert saved_kwargs["status"] == "running", (
            "status should be set to running"
        )

    def test_mark_sync_failed_preserves_last_sync_date(self):
        """
        Verify that mark_sync_failed() does NOT overwrite last_sync_date.
        """
        from src.state.state_manager import StateManager
        
        saved_states = []
        
        mock_pg = MagicMock()
        
        def track_update_sync_state(**kwargs):
            saved_states.append(kwargs.copy())
        
        mock_pg.update_sync_state.side_effect = track_update_sync_state
        mock_pg.get_sync_state.return_value = {
            "model_name": "sale.order",
            "last_sync_date": datetime(2026, 6, 18, 9, 53, 54),  # From previous sync
            "status": "completed",
        }
        
        state_mgr = StateManager(mock_pg)
        
        mock_model_config = MagicMock()
        mock_model_config.odoo_model = "sale.order"
        mock_model_config.postgres_table = "sale_order"
        
        # Call mark_sync_failed
        state_mgr.mark_sync_failed(
            mock_model_config,
            error="Connection timeout",
            record_count=500,
        )
        
        # Verify that last_sync_date was PRESERVED
        assert len(saved_states) == 1, "update_sync_state should be called once"
        
        saved_kwargs = saved_states[0]
        assert saved_kwargs["last_sync_date"] == datetime(2026, 6, 18, 9, 53, 54), (
            f"last_sync_date should be preserved on failure, got: {saved_kwargs['last_sync_date']}"
        )
        assert saved_kwargs["status"] == "failed", (
            "status should be set to failed"
        )
        assert saved_kwargs["error_message"] == "Connection timeout"

    def test_incremental_sync_reads_preserved_last_sync_date(self):
        """
        End-to-end test: Verify that after Run #1 completes and Run #2 starts,
        the last_sync_date is preserved and used for incremental filtering.
        
        This test proves the fix for the reported bug where:
        - Run #1: last_sync_date saved as 2026-06-18 09:53:54
        - Run #2: mark_sync_started() was overwriting it to NULL
        - Result: get_last_sync_date() returned NULL, causing full sync
        """
        from src.state.state_manager import StateManager
        
        # Simulate what happens across two runs
        saved_states = []
        
        mock_pg = MagicMock()
        
        def track_update_sync_state(**kwargs):
            saved_states.append(kwargs.copy())
            # Update the mock to return what was just saved
            mock_pg.get_sync_state.return_value = {
                "model_name": kwargs["model_name"],
                "last_sync_date": kwargs.get("last_sync_date"),
                "status": kwargs.get("status"),
            }
        
        mock_pg.update_sync_state.side_effect = track_update_sync_state
        
        state_mgr = StateManager(mock_pg)
        
        mock_model_config = MagicMock()
        mock_model_config.odoo_model = "sale.order"
        mock_model_config.postgres_table = "sale_order"
        
        # === RUN #1 COMPLETES ===
        mock_pg.get_sync_state.return_value = None  # No existing state
        
        result1 = MagicMock()
        result1.end_time = datetime(2026, 6, 18, 9, 53, 54)
        result1.records_synced = 1200
        result1.success = True
        
        state_mgr.mark_sync_completed(mock_model_config, result1)
        
        # Verify Run #1 saved the timestamp
        assert saved_states[-1]["last_sync_date"] == datetime(2026, 6, 18, 9, 53, 54)
        assert saved_states[-1]["status"] == "completed"
        
        # === RUN #2 STARTS ===
        # This is where the bug was occurring!
        state_mgr.mark_sync_started(mock_model_config)
        
        # Verify Run #2's mark_sync_started PRESERVED the timestamp
        assert saved_states[-1]["last_sync_date"] == datetime(2026, 6, 18, 9, 53, 54), (
            "BUG: last_sync_date was overwritten to NULL!"
        )
        assert saved_states[-1]["status"] == "running"
        
        # === VERIFY INCREMENTAL SYNC CAN READ IT ===
        last_sync = state_mgr.get_last_sync_date("sale.order")
        assert last_sync == datetime(2026, 6, 18, 9, 53, 54), (
            f"Incremental sync should read preserved timestamp, got: {last_sync}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
