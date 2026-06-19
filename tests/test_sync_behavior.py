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
            
            def mock_count(model, domain=None):
                if domain:
                    return 23
                return 417994
            engine._odoo.count.side_effect = mock_count
            engine._odoo.read_batched.return_value = iter([])
            engine._pg.upsert.return_value = (0, 0, 0)
            
            result = engine.sync_model(model, full_sync=False)
            
            info_calls_str = [str(c) for c in engine._logger.info.call_args_list]
            
            # Check for INCREMENTAL SYNC MODE log
            assert any("INCREMENTAL SYNC MODE" in c for c in info_calls_str), (
                f"Expected 'INCREMENTAL SYNC MODE' in logs. Got: {info_calls_str}"
            )
            
            # Check for domain in logs
            assert any("write_date" in c and ">=" in c for c in info_calls_str), (
                f"Expected domain filter in logs. Got: {info_calls_str}"
            )
            
            # Check for records matching filter
            assert any("417994" in c for c in info_calls_str), (
                f"Expected total records in logs. Got: {info_calls_str}"
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


class TestSingleModelIncrementalSync:
    """Tests proving single-model incremental sync only touches the requested model."""

    def test_single_model_sync_only_validates_one_model(self):
        """
        When --models account.move.line is requested, ONLY account.move.line
        should be validated - NOT all models.
        
        Note: fields_get() may be called twice per model (once in _get_validated_model,
        once in initialize), but ONLY for the requested model.
        """
        from src.engine.sync_engine import SyncEngine
        from src.models.config import ModelConfig, FieldConfig, SyncConfig
        
        # Setup 3 models
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
                FieldConfig(
                    odoo_field="write_date",
                    postgres_column="write_date",
                    postgres_type="TIMESTAMP",
                    is_sync_date=True,
                    nullable=True,
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
        model3 = ModelConfig(
            odoo_model="product.product",
            postgres_table="product_product",
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
        
        config = SyncConfig(models=[model1, model2, model3])
        
        with patch.object(SyncEngine, '__init__', lambda x: None):
            engine = SyncEngine()
            engine._logger = MagicMock()
            engine._odoo = MagicMock()
            engine._odoo.test_connection.return_value = True
            engine._odoo.get_model_fields.return_value = {
                "id": {"type": "integer", "required": True},
                "write_date": {"type": "datetime", "required": False},
            }
            engine._pg = MagicMock()
            engine._pg.test_connection.return_value = True
            engine._config = config
            engine._validated_models = {}
            engine._error_reporter = MagicMock()
            engine._schema_recommender = MagicMock()
            engine._pg.validate_schema_against_odoo.return_value = {'mismatches': [], 'warnings': []}
            engine._pg.ensure_table_schema.return_value = {'added_columns': [], 'migrated_columns': []}
            
            # Call initialize with single model filter
            engine.initialize(model_names=["account.move.line"])
            
            # Verify get_model_fields was called ONLY for account.move.line (possibly twice)
            fields_get_calls = engine._odoo.get_model_fields.call_args_list
            models_called = [call[0][0] for call in fields_get_calls]
            
            # All calls should be for account.move.line (not res.partner or product.product)
            assert all(m == "account.move.line" for m in models_called), (
                f"fields_get() should only be called for account.move.line, "
                f"but was called for: {set(models_called)}"
            )
            
            # Verify ensure_table_schema was called ONLY for account_move_line
            ensure_calls = engine._pg.ensure_table_schema.call_args_list
            tables_called = [call[0][0].postgres_table for call in ensure_calls]
            
            assert tables_called == ["account_move_line"], (
                f"ensure_table_schema() should only be called for account_move_line, "
                f"but was called for: {tables_called}"
            )
            
            # Verify validate_schema_against_odoo was called ONLY once
            validate_calls = engine._pg.validate_schema_against_odoo.call_args_list
            assert len(validate_calls) == 1, (
                f"validate_schema_against_odoo() should be called once, "
                f"but was called {len(validate_calls)} times"
            )

    def test_incremental_sync_generates_correct_domain(self):
        """
        Incremental sync should generate domain with write_date >= last_sync.
        
        The key test: read_batched should be called with the domain filter,
        proving server-side filtering is used.
        """
        from src.engine.sync_engine import SyncEngine
        from src.models.config import ModelConfig, FieldConfig
        from datetime import datetime
        
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
        
        last_sync = datetime(2026, 6, 18, 12, 30, 0)
        
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
            
            # Track the domain passed to read_batched
            read_batched_calls = []
            
            def mock_read_batched(model, domain=None, fields=None, batch_size=None, order=None, total_limit=None):
                read_batched_calls.append(domain if domain else [])
                return iter([])
            
            engine._odoo.read_batched = mock_read_batched
            engine._odoo.count.return_value = 23  # Return 23 for domain, 417994 without
            engine._pg.upsert.return_value = (0, 0, 0)
            
            # Run incremental sync
            result = engine.sync_model(model, full_sync=False)
            
            # Verify read_batched was called with correct domain
            assert len(read_batched_calls) >= 1, (
                f"read_batched should be called at least once, got {len(read_batched_calls)}"
            )
            
            expected_domain = [("write_date", ">=", "2026-06-18 12:30:00")]
            
            # The domain should contain the write_date filter
            actual_domain = read_batched_calls[0]
            assert len(actual_domain) == 1, f"Expected domain with 1 filter, got: {actual_domain}"
            assert actual_domain[0][0] == "write_date", f"Expected write_date filter, got: {actual_domain}"
            assert actual_domain[0][1] == ">=", f"Expected >= operator, got: {actual_domain}"
            assert actual_domain[0][2] == "2026-06-18 12:30:00", f"Expected date string, got: {actual_domain[0][2]}"


class TestConfigLoadingWithModelFilter:
    """Tests proving config loading respects model filter BEFORE field discovery."""

    def test_config_loader_filters_models_before_field_discovery(self):
        """
        When model_names=['account.move.line'] is passed to get_config(),
        ONLY account.move.line should be processed for field discovery.
        
        This is the ROOT CAUSE FIX: config loading must filter models BEFORE
        _process_models() is called, not AFTER.
        """
        from src.utils.config_loader import ConfigLoader
        from unittest.mock import MagicMock, patch
        import tempfile
        import os
        
        # Create a temp config file with multiple models
        config_content = """
models:
  - res.partner
  - account.move.line
  - product.product
  - sale.order
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            temp_config_path = f.name
        
        try:
            # Track which models get field discovery calls
            field_discovery_calls = []
            
            # Mock Odoo client to track field discovery
            mock_odoo_client = MagicMock()
            def track_field_discovery(model_name):
                field_discovery_calls.append(model_name)
                return {"id": {"type": "integer", "required": True}}
            mock_odoo_client.get_model_fields.side_effect = track_field_discovery
            
            # Mock the OdooClient class - it's imported inside the method
            with patch('src.clients.odoo_client.OdooClient', return_value=mock_odoo_client):
                # Load config WITH model filter
                loader = ConfigLoader(temp_config_path)
                config = loader.load(model_names=["account.move.line"])
            
            # Verify ONLY account.move.line got field discovery
            assert field_discovery_calls == ["account.move.line"], (
                f"Expected field discovery for ONLY 'account.move.line', "
                f"but got: {field_discovery_calls}"
            )
            
            # Verify config contains only the filtered model
            assert len(config.models) == 1, (
                f"Expected 1 model in config, got {len(config.models)}"
            )
            assert config.models[0].odoo_model == "account.move.line", (
                f"Expected 'account.move.line', got {config.models[0].odoo_model}"
            )
        finally:
            os.unlink(temp_config_path)

    def test_config_loader_without_filter_discovers_all_models(self):
        """
        When model_names=None (no filter), ALL models should get field discovery.
        """
        from src.utils.config_loader import ConfigLoader
        from unittest.mock import MagicMock, patch
        import tempfile
        import os
        
        config_content = """
models:
  - res.partner
  - account.move.line
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            temp_config_path = f.name
        
        try:
            field_discovery_calls = []
            
            mock_odoo_client = MagicMock()
            def track_field_discovery(model_name):
                field_discovery_calls.append(model_name)
                return {"id": {"type": "integer", "required": True}}
            mock_odoo_client.get_model_fields.side_effect = track_field_discovery
            
            with patch('src.clients.odoo_client.OdooClient', return_value=mock_odoo_client):
                loader = ConfigLoader(temp_config_path)
                config = loader.load(model_names=None)  # No filter
            
            # Verify BOTH models got field discovery
            assert set(field_discovery_calls) == {"res.partner", "account.move.line"}, (
                f"Expected field discovery for both models, got: {field_discovery_calls}"
            )
            
            # Verify config contains both models
            assert len(config.models) == 2, (
                f"Expected 2 models in config, got {len(config.models)}"
            )
        finally:
            os.unlink(temp_config_path)


class TestSyncEngineReceivesConfig:
    """
    Regression test for bug where SyncEngine was created WITHOUT config.
    
    Bug: run_sync() loaded config with model_names, but then created
    SyncEngine() without passing config. SyncEngine's config property
    would reload config WITHOUT model_names filter.
    
    Fix: Pass config to SyncEngine constructor.
    """

    def test_sync_engine_uses_passed_config(self):
        """
        Verify SyncEngine uses the config passed to its constructor.
        
        This was a critical bug - SyncEngine was always created without config,
        causing the lazy-loading property to reload config without model_names.
        """
        from src.engine.sync_engine import SyncEngine
        from src.models.config import SyncConfig, ModelConfig, FieldConfig
        
        # Create a filtered config with only account.move.line
        filtered_config = SyncConfig(
            models=[
                ModelConfig(
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
                ),
            ]
        )
        
        # Create SyncEngine with config
        engine = SyncEngine(config=filtered_config)
        
        # Verify config is set directly, not lazily loaded
        assert engine._config is filtered_config, (
            "SyncEngine._config should be set directly when passed to constructor"
        )
        
        # Verify engine.config returns the passed config
        assert engine.config is filtered_config, (
            "engine.config should return the passed config"
        )
        
        # Verify only 1 model in config
        assert len(engine.config.models) == 1, (
            f"Expected 1 model, got {len(engine.config.models)}"
        )
        assert engine.config.models[0].odoo_model == "account.move.line"

    def test_sync_engine_lazy_loads_when_no_config(self):
        """
        Verify SyncEngine lazy-loads config when None is passed.
        
        This preserves the original behavior for cases where config
        is not explicitly passed.
        """
        from src.engine.sync_engine import SyncEngine
        
        # Create SyncEngine without config - should lazy-load
        engine = SyncEngine()
        
        # Access config to trigger lazy load
        # Note: This will try to load from disk, so we just verify
        # the property exists and _config starts as None
        assert engine._config is None, (
            "SyncEngine._config should be None initially when not passed"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
