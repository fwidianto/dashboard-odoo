"""Test NULL constraint migration logic."""
import pytest
from unittest.mock import MagicMock, patch


class TestNullConstraintMigration:
    """Test NULL constraint migration functionality."""

    def test_needs_null_constraint_migration_already_nullable(self):
        """When column is already nullable, no migration needed."""
        from src.clients.postgres_client import PostgresClient
        
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            
            result = client._needs_null_constraint_migration(
                "test_table", "col1", 
                current_nullable=True, 
                expected_nullable=True
            )
            assert result == False

    def test_needs_null_constraint_migration_both_not_nullable(self):
        """When both are NOT NULL, no migration needed."""
        from src.clients.postgres_client import PostgresClient
        
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            
            result = client._needs_null_constraint_migration(
                "test_table", "col1",
                current_nullable=False,
                expected_nullable=False
            )
            assert result == False

    def test_needs_null_constraint_migration_current_nullable_expected_not(self):
        """When current is nullable but expected is NOT NULL - no migration needed."""
        from src.clients.postgres_client import PostgresClient
        
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            
            result = client._needs_null_constraint_migration(
                "test_table", "col1",
                current_nullable=True,  # nullable
                expected_nullable=False  # NOT NULL expected
            )
            assert result == False


class TestNullConstraintMigrationWithDb:
    """Test NULL constraint migration with database mocking."""

    def test_needs_null_constraint_migration_has_nulls(self):
        """When column has NULLs, migration is needed."""
        from src.clients.postgres_client import PostgresClient
        
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            client._engine = MagicMock()
            
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 100
            mock_conn.execute.return_value = mock_result
            client._engine.connect.return_value.__enter__.return_value = mock_conn
            
            result = client._needs_null_constraint_migration(
                "test_table", "col1",
                current_nullable=False,
                expected_nullable=True
            )
            assert result == True

    def test_needs_null_constraint_migration_no_nulls(self):
        """When column has no NULLs, no migration needed."""
        from src.clients.postgres_client import PostgresClient
        
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            client._engine = MagicMock()
            
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0
            mock_conn.execute.return_value = mock_result
            client._engine.connect.return_value.__enter__.return_value = mock_conn
            
            result = client._needs_null_constraint_migration(
                "test_table", "col1",
                current_nullable=False,
                expected_nullable=True
            )
            assert result == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
