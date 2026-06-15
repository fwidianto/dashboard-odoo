"""Tests for PostgreSQL client table creation and schema operations."""

import pytest
from unittest.mock import MagicMock, patch
from src.models.config import FieldConfig, ModelConfig


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
            mock_conn.execute.return_value = MagicMock(rowcount=1)
            client._engine = MagicMock()
            client._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            client._engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            
            # Test upsert
            records = [
                {"id": 1, "name": "Test", "email": "test@example.com"},
                {"id": 2, "name": "Test2", "email": "test2@example.com"},
            ]
            
            client.upsert("res_partner", records, "id")
            
            # Verify the SQL contains ON CONFLICT
            call_args = mock_conn.execute.call_args_list[0]
            sql_query = str(call_args[0][0])
            
            assert 'ON CONFLICT ("id")' in sql_query, \
                f"SQL should contain ON CONFLICT (id), got: {sql_query}"
            assert 'DO UPDATE SET' in sql_query, \
                "SQL should contain DO UPDATE SET clause"


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