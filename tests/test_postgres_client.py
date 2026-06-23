"""Tests for PostgreSQL client table creation and schema operations."""

import pytest
from unittest.mock import MagicMock, patch
from src.models.config import FieldConfig, ModelConfig


class TestGetSqlAlchemyType:
    """Test type mapping for Odoo fields."""

    def test_numeric_upgraded_for_large_values(self):
        """Test that NUMERIC(12,2) is upgraded to NUMERIC(20,4)."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Test NUMERIC(12,2) -> should be upgraded
            result = client._get_sqlalchemy_type("NUMERIC(12,2)")
            assert str(result) == "NUMERIC(20, 4)", \
                f"NUMERIC(12,2) should be upgraded to NUMERIC(20,4), got {result}"

    def test_numeric_precision_preserved_for_large_config(self):
        """Test that large NUMERIC precision is preserved."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Test NUMERIC(20,4) -> should be kept
            result = client._get_sqlalchemy_type("NUMERIC(20,4)")
            assert str(result) == "NUMERIC(20, 4)", \
                f"NUMERIC(20,4) should be preserved, got {result}"

    def test_varchar_converted_to_text(self):
        """Test that VARCHAR(255) is converted to TEXT."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Test VARCHAR(255) -> TEXT
            result = client._get_sqlalchemy_type("VARCHAR(255)")
            assert "TEXT" in str(result).upper() or str(result) == "TEXT()", \
                f"VARCHAR(255) should be converted to TEXT, got {result}"

    def test_varchar_large_converted_to_text(self):
        """Test that VARCHAR(1000) is converted to TEXT."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Test VARCHAR(1000) -> TEXT
            result = client._get_sqlalchemy_type("VARCHAR(1000)")
            assert "TEXT" in str(result).upper() or str(result) == "TEXT()", \
                f"VARCHAR(1000) should be converted to TEXT, got {result}"

    def test_small_varchar_preserved(self):
        """Test that small VARCHAR is preserved."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Test VARCHAR(50) -> should be preserved as VARCHAR
            result = client._get_sqlalchemy_type("VARCHAR(50)")
            assert "VARCHAR" in str(result).upper() or "50" in str(result), \
                f"VARCHAR(50) should be preserved, got {result}"


class TestNeedsMigration:
    """Test schema migration detection."""

    def test_varchar_needs_migration_to_text(self):
        """Test that VARCHAR needs migration to TEXT."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            field = FieldConfig(odoo_field="name", postgres_column="name", postgres_type="VARCHAR(255)")
            current_col = {"type": "VARCHAR(255)", "nullable": False}
            
            result = client._needs_migration("VARCHAR(255)", "TEXT", current_col, field)
            assert result is True, "VARCHAR(255) should need migration to TEXT"

    def test_integer_needs_migration_to_text_for_display_name_fields(self):
        """Existing FK id columns should migrate to TEXT when storing display names."""
        from src.clients.postgres_client import PostgresClient

        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"

            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")

            field = FieldConfig(odoo_field="partner_id", postgres_column="partner_id", postgres_type="TEXT")
            current_col = {"type": "INTEGER", "nullable": True}

            result = client._needs_migration("INTEGER", "TEXT", current_col, field)
            assert result is True, "INTEGER partner_id should migrate to TEXT for display names"

    def test_numeric_12_needs_migration(self):
        """Test that NUMERIC(12,2) needs migration."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            field = FieldConfig(odoo_field="amount", postgres_column="amount_total", postgres_type="NUMERIC(12,2)")
            current_col = {"type": "NUMERIC(12,2)", "nullable": False}
            
            result = client._needs_migration("NUMERIC(12,2)", "NUMERIC(20,4)", current_col, field)
            assert result is True, "NUMERIC(12,2) should need migration to NUMERIC(20,4)"

    def test_numeric_20_needs_migration_to_numeric_30_10(self):
        """Test that NUMERIC(20,4) is widened to NUMERIC(30,10)."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            field = FieldConfig(odoo_field="amount", postgres_column="amount_total", postgres_type="NUMERIC(20,4)")
            current_col = {"type": "NUMERIC(20,4)", "nullable": False}
            
            result = client._needs_migration("NUMERIC(20,4)", "NUMERIC(30,10)", current_col, field)
            assert result is True, "NUMERIC(20,4) should migrate to NUMERIC(30,10)"


class TestCreateModelTable:
    """Test table creation with primary key constraints."""

    @pytest.fixture
    def model_config_with_pk(self):
        """Model config with primary key defined."""
        return ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="INTEGER",
                    primary_key=True,
                    nullable=False,
                    indexed=True,
                ),
                FieldConfig(
                    odoo_field="name",
                    postgres_column="name",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                    indexed=True,
                ),
                FieldConfig(
                    odoo_field="email",
                    postgres_column="email",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
            ],
        )

    def test_column_definition_includes_primary_key(self, model_config_with_pk):
        """Test that Column definitions include primary_key=True."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Capture columns created
            captured_columns = []
            original_column = __import__('sqlalchemy', fromlist=['Column']).Column
            
            def capture_column(*args, **kwargs):
                captured_columns.append(kwargs)
                return original_column(*args, **kwargs)
            
            with patch('src.clients.postgres_client.Column', side_effect=capture_column):
                with patch('src.clients.postgres_client.Table', return_value=MagicMock()):
                    with patch('src.clients.postgres_client.inspect') as mock_inspect:
                        mock_inspect.return_value.get_table_names.return_value = []
                        mock_inspect.return_value.get_pk_constraint.return_value = {'constrained_columns': ['id']}
                        
                        # Mock engine to avoid real connection
                        client._engine = MagicMock()
                        
                        client.create_model_table(model_config_with_pk)
            
            # Find the id column kwargs
            id_col_kwargs = next((c for c in captured_columns if c.get('name') == 'id'), None)
            assert id_col_kwargs is not None, "ID column not found"
            assert id_col_kwargs.get('primary_key') is True, \
                "ID column should have primary_key=True"
            
    def test_table_created_without_primary_key_param(self, model_config_with_pk):
        """Test that Table() is called WITHOUT primary_key parameter."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            table_calls = []
            
            def capture_table(*args, **kwargs):
                table_calls.append(kwargs)
                return MagicMock()
            
            with patch('src.clients.postgres_client.Table', side_effect=capture_table):
                with patch('src.clients.postgres_client.inspect') as mock_inspect:
                    mock_inspect.return_value.get_table_names.return_value = []
                    mock_inspect.return_value.get_pk_constraint.return_value = {'constrained_columns': ['id']}
                    
                    client._engine = MagicMock()
                    client.create_model_table(model_config_with_pk)
            
            # Verify Table() was called
            assert len(table_calls) > 0, "Table() should have been called"
            
            # Verify Table() was NOT called with primary_key parameter
            for kwargs in table_calls:
                assert 'primary_key' not in kwargs, \
                    "Table() should NOT have primary_key parameter - use Column.primary_key=True"

    def test_create_model_table_idempotent(self, model_config_with_pk):
        """
        Test that create_model_table() can be called multiple times without error.
        
        This verifies the fix for:
        sqlalchemy.exc.InvalidRequestError: Table 'res_partner' is already defined
        """
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Use a mutable dict for testing
            client._metadata.tables = {}
            
            # Track Table() calls
            table_calls = []
            
            def capture_table(*args, **kwargs):
                table_calls.append(kwargs)
                # Simulate SQLAlchemy: Table() adds itself to metadata.tables
                table_name = args[0] if args else kwargs.get('name')
                if table_name and table_name not in client._metadata.tables:
                    client._metadata.tables[table_name] = MagicMock()
                return MagicMock()
            
            with patch('src.clients.postgres_client.Table', side_effect=capture_table):
                with patch('src.clients.postgres_client.inspect') as mock_inspect:
                    mock_inspect.return_value.get_table_names.return_value = []
                    mock_inspect.return_value.get_pk_constraint.return_value = {'constrained_columns': ['id']}
                    
                    client._engine = MagicMock()
                    
                    # Call create_model_table() twice - should NOT raise
                    client.create_model_table(model_config_with_pk)
                    client.create_model_table(model_config_with_pk)  # Second call
                    
                    # Table() should only be called ONCE (idempotent)
                    assert len(table_calls) == 1, \
                        f"Table() should only be called once for idempotency, got {len(table_calls)} calls"

    def test_table_extend_existing_parameter(self, model_config_with_pk):
        """Test that Table() is created with extend_existing=True."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Use a mutable dict for testing
            client._metadata.tables = {}
            
            table_calls = []
            def capture_table(*args, **kwargs):
                table_calls.append(kwargs)
                # Simulate SQLAlchemy adding to metadata
                table_name = args[0] if args else kwargs.get('name')
                if table_name:
                    client._metadata.tables[table_name] = MagicMock()
                return MagicMock()
            
            with patch('src.clients.postgres_client.Table', side_effect=capture_table):
                with patch('src.clients.postgres_client.inspect') as mock_inspect:
                    mock_inspect.return_value.get_table_names.return_value = []
                    mock_inspect.return_value.get_pk_constraint.return_value = {'constrained_columns': ['id']}
                    
                    client._engine = MagicMock()
                    client.create_model_table(model_config_with_pk)
            
            # Verify extend_existing=True was passed
            assert len(table_calls) == 1
            assert table_calls[0].get('extend_existing') is True, \
                "Table() should be called with extend_existing=True"


class TestSchemaValidationIdempotency:
    """Test that schema validation can run multiple times without conflicts."""

    def test_validate_and_migrate_schema_idempotent(self):
        """
        Test that validate_and_migrate_schema() can be called multiple times.
        
        Verifies the full flow:
        - create_model_table()
        - validate_and_migrate_schema()
        - ensure_table_schema()
        
        All can run repeatedly without metadata conflicts.
        """
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Use a mutable dict for testing
            client._metadata.tables = {}
            
            model_config = ModelConfig(
                odoo_model="res.partner",
                postgres_table="res_partner",
                fields=[
                    FieldConfig(
                        odoo_field="id",
                        postgres_column="id",
                        postgres_type="INTEGER",
                        primary_key=True,
                        nullable=False,
                    ),
                    FieldConfig(
                        odoo_field="name",
                        postgres_column="name",
                        postgres_type="VARCHAR(255)",
                        nullable=True,
                    ),
                ],
            )
            
            table_calls = []
            def capture_table(*args, **kwargs):
                table_calls.append(kwargs)
                # Simulate SQLAlchemy adding to metadata
                table_name = args[0] if args else kwargs.get('name')
                if table_name and table_name not in client._metadata.tables:
                    client._metadata.tables[table_name] = MagicMock()
                return MagicMock()
            
            with patch('src.clients.postgres_client.Table', side_effect=capture_table):
                with patch('src.clients.postgres_client.inspect') as mock_inspect:
                    mock_inspect.return_value.get_table_names.return_value = []
                    mock_inspect.return_value.get_pk_constraint.return_value = {'constrained_columns': ['id']}
                    mock_inspect.return_value.get_columns.return_value = [
                        {'name': 'id', 'type': 'INTEGER', 'nullable': False},
                        {'name': 'name', 'type': 'VARCHAR(255)', 'nullable': True},
                    ]
                    
                    client._engine = MagicMock()
                    
                    # Run the full flow multiple times
                    for i in range(3):
                        # This should NOT raise InvalidRequestError
                        client.create_model_table(model_config)
                        client.ensure_table_schema(model_config)
                    
                    # Table() should only be called ONCE despite multiple invocations
                    assert len(table_calls) == 1, \
                        f"Table() should only be called once, got {len(table_calls)} calls"


class TestUpsertWithPrimaryKey:
    """Test that upsert requires a primary key constraint."""

    def test_upsert_sql_uses_conflict_target(self):
        """Test that upsert SQL correctly specifies ON CONFLICT target."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Mock engine
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchone.return_value = (1, 0)  # id=1, xmax=0 (insert)
            mock_conn.execute.return_value = mock_result
            client._engine = MagicMock()
            client._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            client._engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            
            # Test upsert
            records = [
                {"id": 1, "name": "Test", "email": "test@example.com"},
                {"id": 2, "name": "Test2", "email": "test2@example.com"},
            ]
            
            inserted, updated, errors = client.upsert("res_partner", records, "id")
            
            # Verify the SQL contains ON CONFLICT
            call_args = mock_conn.execute.call_args_list[0]
            sql_query = str(call_args[0][0])
            
            assert 'ON CONFLICT ("id")' in sql_query, \
                f"SQL should contain ON CONFLICT (id), got: {sql_query}"
            assert 'DO UPDATE SET' in sql_query, \
                "SQL should contain DO UPDATE SET clause"
            assert 'RETURNING' in sql_query, \
                "SQL should contain RETURNING for accurate metrics"
    
    def test_upsert_returns_error_count(self):
        """Test that upsert returns error count."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            # Mock engine
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchone.return_value = (1, 0)  # id=1, xmax=0 (insert)
            mock_conn.execute.return_value = mock_result
            client._engine = MagicMock()
            client._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            client._engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            
            # Test upsert
            records = [{"id": 1, "name": "Test"}]
            
            result = client.upsert("res_partner", records, "id")
            
            # Verify it returns 3 values
            assert len(result) == 3, "upsert should return (inserted, updated, errors)"
            inserted, updated, errors = result
            assert isinstance(inserted, int)
            assert isinstance(updated, int)
            assert isinstance(errors, int)


class TestModelConfigGetIndexedFields:
    """Test that ModelConfig.get_indexed_fields excludes primary keys."""

    def test_primary_key_not_in_indexed_fields(self):
        """Verify primary key fields are excluded from get_indexed_fields."""
        config = ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="INTEGER",
                    primary_key=True,
                    nullable=False,
                    indexed=True,  # Would normally add to indexed
                ),
                FieldConfig(
                    odoo_field="write_date",
                    postgres_column="write_date",
                    postgres_type="TIMESTAMP",
                    nullable=True,
                    is_sync_date=True,
                    indexed=True,
                ),
            ],
        )
        
        indexed_fields = config.get_indexed_fields()
        indexed_names = [f.odoo_field for f in indexed_fields]
        
        # Primary key should NOT be in indexed fields
        assert "id" not in indexed_names, \
            "Primary key should not be included in get_indexed_fields()"
        # Sync date should be included
        assert "write_date" in indexed_names, \
            "Sync date fields should be included in get_indexed_fields()"

    def test_non_primary_key_indexed_field_included(self):
        """Verify non-primary key indexed fields are included."""
        config = ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=[
                FieldConfig(
                    odoo_field="id",
                    postgres_column="id",
                    postgres_type="INTEGER",
                    primary_key=True,
                    nullable=False,
                ),
                FieldConfig(
                    odoo_field="email",
                    postgres_column="email",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                    indexed=True,  # Regular indexed field
                ),
            ],
        )
        
        indexed_fields = config.get_indexed_fields()
        indexed_names = [f.odoo_field for f in indexed_fields]
        
        assert "email" in indexed_names, \
            "Indexed non-primary key field should be included"
        assert "id" not in indexed_names, \
            "Primary key should not be included even if it has indexed=True"


class TestExpectedPostgresType:
    """Test expected PostgreSQL type calculation for Odoo fields."""

    def test_numeric_becomes_numeric_20_4(self):
        """Test that NUMERIC types are expected as NUMERIC(20,4)."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            field = FieldConfig(odoo_field="list_price", postgres_column="list_price", postgres_type="NUMERIC(12,2)")
            result = client._get_expected_postgres_type(field)
            
            assert result == "NUMERIC(30,10)", \
                f"NUMERIC should become NUMERIC(30,10), got {result}"

    def test_varchar_255_becomes_text(self):
        """Test that VARCHAR(255) is expected as TEXT."""
        from src.clients.postgres_client import PostgresClient
        
        with patch('src.clients.postgres_client.get_settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.postgres.connection_url = "postgresql://test:test@localhost/test"
            
            client = PostgresClient(connection_url="postgresql://test:test@localhost/test")
            
            field = FieldConfig(odoo_field="name", postgres_column="name", postgres_type="VARCHAR(255)")
            result = client._get_expected_postgres_type(field)
            
            assert result == "TEXT", \
                f"VARCHAR(255) should become TEXT, got {result}"
