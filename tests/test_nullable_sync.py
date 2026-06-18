"""Regression tests for nullable field sync from Odoo to PostgreSQL."""
import pytest
from unittest.mock import MagicMock, patch


class TestNullableFieldSync:
    """Test that nullable fields are synced correctly from Odoo metadata."""

    def test_nullable_field_in_odoo_syncs_to_nullable_in_postgres(self):
        """
        Regression test: Odoo field with required=False should be nullable=True in PostgreSQL.
        
        This test verifies the fix for the account.move.line/move_id bug where
        move_id was marked as nullable=False in PostgreSQL despite being nullable in Odoo.
        """
        from src.models.config import FieldConfig, ModelConfig
        from src.utils.config_loader import ValidatedModelConfig

        # Create a field config that was created without Odoo metadata (nullable=True by default)
        field_config = FieldConfig(
            odoo_field="move_id",
            postgres_column="move_id",
            postgres_type="INTEGER",
            nullable=True,  # Config default
            primary_key=False,
        )

        model_config = ModelConfig(
            odoo_model="account.move.line",
            postgres_table="account_move_line",
            fields=[field_config],
        )

        # Simulate Odoo metadata where move_id is NOT required (nullable in Odoo)
        odoo_fields = {
            "move_id": {
                "type": "many2one",
                "required": False,  # Odoo says nullable
                "readonly": False,
                "store": True,
            },
            "id": {
                "type": "integer",
                "required": True,
                "readonly": True,
                "store": True,
            },
        }

        # Create validated config
        validated = ValidatedModelConfig(model_config, odoo_fields)

        # The field should be marked as nullable=True (synced from Odoo's required=False)
        move_id_field = next(f for f in validated.fields if f.odoo_field == "move_id")
        assert move_id_field.nullable == True, (
            f"Expected move_id.nullable=True (from Odoo required=False), "
            f"got nullable={move_id_field.nullable}"
        )

    def test_required_field_in_odoo_syncs_to_not_nullable_in_postgres(self):
        """
        Test that required=True in Odoo stays as nullable=False in PostgreSQL.
        """
        from src.models.config import FieldConfig, ModelConfig
        from src.utils.config_loader import ValidatedModelConfig

        # Create a field config
        field_config = FieldConfig(
            odoo_field="partner_id",
            postgres_column="partner_id",
            postgres_type="INTEGER",
            nullable=True,  # Config default
            primary_key=False,
        )

        model_config = ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=[field_config],
        )

        # Simulate Odoo metadata where partner_id IS required
        odoo_fields = {
            "partner_id": {
                "type": "many2one",
                "required": True,  # Odoo says required
                "readonly": False,
                "store": True,
            },
            "id": {
                "type": "integer",
                "required": True,
                "readonly": True,
                "store": True,
            },
        }

        # Create validated config
        validated = ValidatedModelConfig(model_config, odoo_fields)

        # The field should be marked as nullable=False (Odoo's required=True)
        partner_id_field = next(f for f in validated.fields if f.odoo_field == "partner_id")
        assert partner_id_field.nullable == False, (
            f"Expected partner_id.nullable=False (from Odoo required=True), "
            f"got nullable={partner_id_field.nullable}"
        )

    def test_no_change_when_nullable_matches(self):
        """
        Test that field config is not unnecessarily modified when nullable already matches.
        """
        from src.models.config import FieldConfig, ModelConfig
        from src.utils.config_loader import ValidatedModelConfig

        field_config = FieldConfig(
            odoo_field="amount",
            postgres_column="amount",
            postgres_type="NUMERIC(20,4)",
            nullable=True,
            primary_key=False,
        )

        model_config = ModelConfig(
            odoo_model="account.move.line",
            postgres_table="account_move_line",
            fields=[field_config],
        )

        # Odoo metadata matches config
        odoo_fields = {
            "amount": {
                "type": "float",
                "required": False,  # nullable=True expected
                "readonly": False,
                "store": True,
            },
        }

        validated = ValidatedModelConfig(model_config, odoo_fields)

        # Field should be the same object (not copied)
        amount_field = next(f for f in validated.fields if f.odoo_field == "amount")
        assert amount_field.nullable == True
        # Object identity check - should be the same object, not a copy
        assert amount_field is field_config, "Field should not be copied when no change needed"

    def test_primary_key_always_not_null(self):
        """
        Test that id field stays nullable=False even if Odoo metadata says something else.
        """
        from src.models.config import FieldConfig, ModelConfig
        from src.utils.config_loader import ValidatedModelConfig

        field_config = FieldConfig(
            odoo_field="id",
            postgres_column="id",
            postgres_type="INTEGER",
            nullable=False,  # Explicitly False for primary key
            primary_key=True,
        )

        model_config = ModelConfig(
            odoo_model="account.move.line",
            postgres_table="account_move_line",
            fields=[field_config],
        )

        # Odoo metadata for id
        odoo_fields = {
            "id": {
                "type": "integer",
                "required": True,
                "readonly": True,
                "store": True,
            },
        }

        validated = ValidatedModelConfig(model_config, odoo_fields)

        id_field = next(f for f in validated.fields if f.odoo_field == "id")
        assert id_field.nullable == False, "Primary key should always be nullable=False"
        assert id_field.primary_key == True


class TestMigrationReport:
    """Test schema validation report generation."""

    def test_schema_mismatch_detection(self):
        """
        Test that schema mismatches are detected and logged.
        """
        from src.models.config import FieldConfig, ModelConfig
        from src.utils.config_loader import ValidatedModelConfig

        field_config = FieldConfig(
            odoo_field="move_id",
            postgres_column="move_id",
            postgres_type="INTEGER",
            nullable=False,  # Wrong! PostgreSQL has NOT NULL
            primary_key=False,
        )

        model_config = ModelConfig(
            odoo_model="account.move.line",
            postgres_table="account_move_line",
            fields=[field_config],
        )

        # Odoo metadata says move_id is optional
        odoo_fields = {
            "move_id": {
                "type": "many2one",
                "required": False,  # Odoo says nullable
                "readonly": False,
                "store": True,
            },
        }

        # Capture log output
        with patch('src.utils.logging.get_logger') as mock_logger:
            validated = ValidatedModelConfig(model_config, odoo_fields)
            
            # Check that info was logged about the mismatch
            assert mock_logger.return_value.info.called, "Should log info about nullable sync"
            log_call_args = str(mock_logger.return_value.info.call_args)
            assert "move_id" in log_call_args
            assert "was_nullable" in log_call_args or "now_nullable" in log_call_args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
