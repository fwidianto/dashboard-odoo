"""
Tests for sync engine behavior.

These tests verify:
1. Model-specific sync only initializes requested models
2. Incremental sync uses server-side filtering with write_date domain
3. Full sync behavior
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestModelScopedInitialization:
    """Test that only requested models are initialized."""

    def test_initialize_with_specific_models(self):
        """
        When initialize() is called with model_names=['account.move.line'],
        only account.move.line should be validated.
        """
        from src.engine.sync_engine import SyncEngine
        from src.models.config import ModelConfig, FieldConfig, SyncConfig
        
        model1 = ModelConfig(
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
            ],
        )
        model2 = ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="BIGINT",
                    primary_key=True,
                    nullable=False,
                ),
            ],
        )
        
        config = SyncConfig(models=[model1, model2])
        
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._odoo.test_connection.return_value = True
            # Return valid field definitions so validation passes
            engine._odoo.get_model_fields.return_value = {
                "id": {"type": "integer", "required": True}
            }
            engine._pg = MagicMock()
            engine._pg.test_connection.return_value = True
            engine._config = config
            engine._validated_models = {}
            engine._error_reporter = MagicMock()
            engine._schema_recommender = MagicMock()
            
            validated_models = []
            
            def mock_validate_schema(model_config, odoo_fields):
                validated_models.append(model_config.odoo_model)
                return {'mismatches': [], 'warnings': []}
            
            engine._pg.validate_schema_against_odoo.side_effect = mock_validate_schema
            engine._pg.ensure_table_schema.return_value = {'added_columns': [], 'migrated_columns': []}
            
            engine.initialize(model_names=["account.move.line"])
            
            assert validated_models == ["account.move.line"], (
                f"Expected only account.move.line to be validated, got: {validated_models}"
            )

    def test_initialize_without_model_names(self):
        """When initialize() is called without model_names, all models should be initialized."""
        from src.engine.sync_engine import SyncEngine
        from src.models.config import ModelConfig, FieldConfig, SyncConfig
        
        model1 = ModelConfig(
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
            ],
        )
        model2 = ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="BIGINT",
                    primary_key=True,
                    nullable=False,
                ),
            ],
        )
        
        config = SyncConfig(models=[model1, model2])
        
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._odoo.test_connection.return_value = True
            # Return valid field definitions so validation passes
            engine._odoo.get_model_fields.return_value = {
                "id": {"type": "integer", "required": True}
            }
            engine._pg = MagicMock()
            engine._pg.test_connection.return_value = True
            engine._config = config
            engine._validated_models = {}
            engine._error_reporter = MagicMock()
            engine._schema_recommender = MagicMock()
            
            validated_models = []
            
            def mock_validate_schema(model_config, odoo_fields):
                validated_models.append(model_config.odoo_model)
                return {'mismatches': [], 'warnings': []}
            
            engine._pg.validate_schema_against_odoo.side_effect = mock_validate_schema
            engine._pg.ensure_table_schema.return_value = {'added_columns': [], 'migrated_columns': []}
            
            engine.initialize()
            
            assert validated_models == ["account.move.line", "res.partner"], (
                f"Expected both models to be validated, got: {validated_models}"
            )


class TestIncrementalSyncFiltering:
    """Test that incremental sync uses server-side filtering."""

    def test_incremental_sync_uses_domain_filter(self):
        """
        Incremental sync should use write_date >= last_sync_date domain filter
        and pass it to search_count (server-side filtering).
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
        
        last_sync = datetime(2026, 6, 18, 10, 0, 0)
        
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._state_mgr = MagicMock()
            engine._state_mgr.get_last_sync_date.return_value = last_sync
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
            
            count_calls_with_domain = []
            
            def mock_count(model, domain):
                if domain:
                    count_calls_with_domain.append(domain)
                    return 23
                return 417994
            engine._odoo.count.side_effect = mock_count
            engine._odoo.read_batched.return_value = iter([])
            engine._pg.upsert.return_value = (0, 0, 0)
            
            result = engine.sync_model(model, full_sync=False)
            
            expected_domain = [("write_date", ">=", "2026-06-18 10:00:00")]
            assert expected_domain in count_calls_with_domain, (
                f"Expected count to be called with domain {expected_domain}. "
                f"Called with: {count_calls_with_domain}"
            )

    def test_incremental_sync_logs_diagnostic_info(self):
        """Incremental sync should log diagnostic info showing changed_records."""
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
        
        last_sync = datetime(2026, 6, 18, 10, 0, 0)
        
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._state_mgr = MagicMock()
            engine._state_mgr.get_last_sync_date.return_value = last_sync
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
            
            def mock_count(model, domain):
                if domain:
                    return 23
                return 417994
            engine._odoo.count.side_effect = mock_count
            engine._odoo.read_batched.return_value = iter([])
            engine._pg.upsert.return_value = (0, 0, 0)
            
            result = engine.sync_model(model, full_sync=False)
            
            info_calls = engine._logger.info.call_args_list
            incremental_log = None
            for call in info_calls:
                if "changed_records" in str(call):
                    incremental_log = call
                    break
            
            assert incremental_log is not None, (
                f"Expected 'changed_records' in log call. Got: {[str(c) for c in info_calls]}"
            )


class TestFullSyncBehavior:
    """Test that full sync fetches all records."""

    def test_full_sync_no_domain_filter(self):
        """Full sync should NOT call get_last_sync_date (no incremental logic)."""
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
        
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._state_mgr = MagicMock()
            engine._pg = MagicMock()
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
            engine._odoo.count.return_value = 417994
            engine._odoo.read_batched.return_value = iter([])
            engine._pg.upsert.return_value = (0, 0, 0)
            
            result = engine.sync_model(model, full_sync=True)
            
            # Full sync should NOT call get_last_sync_date
            engine._state_mgr.get_last_sync_date.assert_not_called()


class TestSyncModelFiltering:
    """Test that sync_all respects model filtering."""

    def test_sync_all_respects_model_names(self):
        """
        sync_all() with model_names=['account.move.line'] should
        only sync account.move.line.
        """
        from src.engine.sync_engine import SyncEngine
        from src.models.config import ModelConfig, FieldConfig, SyncConfig
        
        model1 = ModelConfig(
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
            ],
        )
        model2 = ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="BIGINT",
                    primary_key=True,
                    nullable=False,
                ),
            ],
        )
        
        config = SyncConfig(models=[model1, model2])
        
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._pg = MagicMock()
            engine._pg.validate_and_migrate_schema.return_value = {}
            engine._state_mgr = MagicMock()
            engine._pg.get_table_row_count.return_value = 0
            engine._config = config
            engine._error_reporter = MagicMock()
            engine._validated_models = {}
            engine._schema_recommender = MagicMock()
            engine._error_reporter.has_errors.return_value = False
            engine._error_reporter.get_sync_report.return_value = MagicMock(models={})
            
            def mock_fields_get(model):
                return {"id": {"type": "integer", "required": True}}
            engine._odoo.get_model_fields.side_effect = mock_fields_get
            engine._odoo.count.return_value = 0
            engine._odoo.read_batched.return_value = iter([])
            engine._pg.upsert.return_value = (0, 0, 0)
            
            results = engine.sync_all(
                full_sync=True, 
                model_names=["account.move.line"]
            )
            
            call_args = engine._pg.validate_and_migrate_schema.call_args
            passed_models = call_args[0][0]
            
            assert len(passed_models) == 1, (
                f"Expected 1 model in validate_and_migrate_schema, got {len(passed_models)}"
            )
            assert passed_models[0].odoo_model == "account.move.line"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
