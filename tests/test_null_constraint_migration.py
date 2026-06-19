"""Test NULL constraint migration logic.

These tests verify the fix for the account.move.line/move_id bug where:
- PostgreSQL had NOT NULL constraint on move_id column
- Odoo marked move_id as optional (required=False)
- This caused NULL_CONSTRAINT errors when syncing records without move_id

The fix ensures that when Odoo says a field is optional (nullable), PostgreSQL
automatically migrates the column to be nullable, even if there are no NULLs yet.
"""

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


class TestNullConstraintMigrationBugFix:
    """
    Tests for the account.move.line/move_id bug fix.
    
    The root cause: _needs_null_constraint_migration only returned True if there
    were existing NULLs in the data. This was wrong because:
    1. If Odoo says a field is optional, PostgreSQL should allow NULLs
    2. Even if no NULLs exist yet, future syncs may have NULLs
    3. The NOT NULL constraint was blocking valid data from syncing
    
    The fix: Always migrate NOT NULL -> NULL when Odoo says field is optional.
    """

    def test_move_id_migration_from_not_null_to_nullable(self):
        """
        Regression test for account.move.line/move_id bug.
        
        Scenario:
        - PostgreSQL has move_id as NOT NULL
        - Odoo says move_id is optional (required=False)
        
        Expected: Migration is needed and should be triggered.
        """
        from src.clients.postgres_client import PostgresClient
        
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            
            # PostgreSQL has NOT NULL, Odoo says nullable
            result = client._needs_null_constraint_migration(
                "account_move_line", "move_id",
                current_nullable=False,  # PostgreSQL has NOT NULL
                expected_nullable=True   # Odoo says optional
            )
            
            # FIXED: Should return True because Odoo says field is optional
            assert result == True, (
                "move_id should migrate from NOT NULL to NULL because "
                "Odoo says the field is optional (required=False)"
            )

    def test_required_field_no_migration_needed(self):
        """
        Test that required fields don't trigger unnecessary migration.
        
        Scenario:
        - PostgreSQL has partner_id as NOT NULL
        - Odoo says partner_id is required (required=True)
        
        Expected: No migration needed (PostgreSQL is correctly NOT NULL).
        """
        from src.clients.postgres_client import PostgresClient
        
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            
            result = client._needs_null_constraint_migration(
                "res_partner", "partner_id",
                current_nullable=False,  # PostgreSQL has NOT NULL
                expected_nullable=False  # Odoo says required
            )
            
            # No migration needed - both agree on NOT NULL
            assert result == False

    def test_nullable_field_already_nullable(self):
        """
        Test that already nullable fields don't trigger migration.
        
        Scenario:
        - PostgreSQL has description as NULL
        - Odoo says description is optional (required=False)
        
        Expected: No migration needed (already correct).
        """
        from src.clients.postgres_client import PostgresClient
        
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            
            result = client._needs_null_constraint_migration(
                "product_template", "description",
                current_nullable=True,   # PostgreSQL is nullable
                expected_nullable=True   # Odoo says optional
            )
            
            # No migration needed - already correct
            assert result == False


class TestValidateSchemaAgainstOdoo:
    """Test schema validation against Odoo metadata."""

    def test_detect_move_id_mismatch(self):
        """
        Test that validate_schema_against_odoo detects the move_id mismatch.
        
        Scenario:
        - PostgreSQL has move_id as NOT NULL
        - Odoo says move_id is optional (required=False)
        
        Expected: Validation report shows mismatch with fix.
        """
        from src.clients.postgres_client import PostgresClient
        from src.models.config import ModelConfig, FieldConfig
        
        # Mock the PostgresClient
        with patch.object(PostgresClient, '__init__', lambda x: None):
            client = PostgresClient()
            client._logger = MagicMock()
            client._engine = MagicMock()
            
            # Mock inspector
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = ["account_move_line"]
            mock_inspector.get_columns.return_value = [
                {
                    "name": "id",
                    "type": MagicMock(),
                    "nullable": False,  # Primary key is NOT NULL
                },
                {
                    "name": "move_id",
                    "type": MagicMock(),
                    "nullable": False,  # BUG: Should be nullable but is NOT NULL
                },
            ]
            
            # Patch inspect to return our mock
            with patch('src.clients.postgres_client.inspect', return_value=mock_inspector):
                model_config = ModelConfig(
                    odoo_model="account.move.line",
                    postgres_table="account_move_line",
                    fields=[
                        FieldConfig(
                            odoo_field="id",
                            postgres_column="id",
                            postgres_type="BIGINT",
                            nullable=False,
                            primary_key=True,
                        ),
                        FieldConfig(
                            odoo_field="move_id",
                            postgres_column="move_id",
                            postgres_type="BIGINT",
                            nullable=True,  # Odoo says this is nullable
                            primary_key=False,
                        ),
                    ],
                )
                
                # Odoo metadata says move_id is optional
                odoo_fields = {
                    "id": {"required": True},
                    "move_id": {"required": False},  # Odoo says optional
                }
                
                report = client.validate_schema_against_odoo(model_config, odoo_fields)
                
                # Should detect mismatch
                assert report['mismatch_count'] == 1, "Should detect move_id mismatch"
                assert report['mismatches'][0]['column'] == 'move_id'
                assert report['mismatches'][0]['issue'] == 'MISMATCH'
                assert 'DROP NOT NULL' in report['mismatches'][0]['fix']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
