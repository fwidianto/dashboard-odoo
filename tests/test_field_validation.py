"""Tests for ValidatedModelConfig - Odoo field validation against models.yaml."""

import pytest
from unittest.mock import MagicMock, patch
from src.models.config import FieldConfig, ModelConfig
from src.utils.config_loader import ValidatedModelConfig


class TestValidatedModelConfig:
    """Test ValidatedModelConfig field validation functionality."""

    @pytest.fixture
    def sample_odoo_fields(self):
        """Sample Odoo fields from fields_get()."""
        return {
            "id": {"type": "integer", "string": "ID"},
            "name": {"type": "char", "string": "Name"},
            "email": {"type": "char", "string": "Email"},
            "phone": {"type": "char", "string": "Phone"},
            "active": {"type": "boolean", "string": "Active"},
            "write_date": {"type": "datetime", "string": "Last Updated"},
        }

    @pytest.fixture
    def model_config_with_valid_fields(self):
        """Model config with fields that exist in Odoo."""
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
                ),
                FieldConfig(
                    odoo_field="email",
                    postgres_column="email",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
            ],
        )

    @pytest.fixture
    def model_config_with_invalid_fields(self):
        """Model config with some fields that DON'T exist in Odoo."""
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
                ),
                FieldConfig(
                    odoo_field="nonexistent_field",  # This doesn't exist in Odoo
                    postgres_column="nonexistent",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
                FieldConfig(
                    odoo_field="another_missing",  # This also doesn't exist
                    postgres_column="missing",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
            ],
        )

    def test_valid_fields_all_included(self, model_config_with_valid_fields, sample_odoo_fields):
        """Test that valid fields are all included in validated config."""
        validated = ValidatedModelConfig(model_config_with_valid_fields, sample_odoo_fields)
        
        assert len(validated.fields) == 3
        assert len(validated.skipped_fields) == 0
        field_names = [f.odoo_field for f in validated.fields]
        assert "id" in field_names
        assert "name" in field_names
        assert "email" in field_names

    def test_invalid_fields_are_skipped(self, model_config_with_invalid_fields, sample_odoo_fields):
        """Test that fields not in Odoo are skipped with warnings."""
        with patch("src.utils.logging.get_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            
            validated = ValidatedModelConfig(model_config_with_invalid_fields, sample_odoo_fields)
            
            # Should have only 2 valid fields (id, name)
            assert len(validated.fields) == 2
            # Should have 2 skipped fields
            assert len(validated.skipped_fields) == 2
            assert "nonexistent_field" in validated.skipped_fields
            assert "another_missing" in validated.skipped_fields
            
            # Warning should have been logged
            mock_logger.return_value.warning.assert_called()

    def test_primary_key_validation(self, model_config_with_invalid_fields, sample_odoo_fields):
        """Test that primary key validation works correctly."""
        validated = ValidatedModelConfig(model_config_with_invalid_fields, sample_odoo_fields)
        
        # Primary key 'id' exists in Odoo, so should be valid
        assert validated.has_valid_primary_key
        assert validated.get_primary_key_field() is not None
        assert validated.get_primary_key_field().odoo_field == "id"

    def test_sync_date_field_validation(self, sample_odoo_fields):
        """Test sync date field validation."""
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
                    indexed=True,
                ),
                FieldConfig(
                    odoo_field="write_date",
                    postgres_column="write_date",
                    postgres_type="TIMESTAMP",
                    nullable=True,
                    is_sync_date=True,
                ),
            ],
        )
        
        validated = ValidatedModelConfig(config, sample_odoo_fields)
        
        assert validated.has_sync_date_field
        assert validated.get_sync_date_field() is not None
        assert validated.get_sync_date_field().odoo_field == "write_date"

    def test_all_fields_invalid(self, sample_odoo_fields):
        """Test behavior when ALL fields are invalid."""
        config = ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=[
                FieldConfig(
                    odoo_field="invalid_field_1",
                    postgres_column="col1",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
                FieldConfig(
                    odoo_field="invalid_field_2",
                    postgres_column="col2",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
            ],
        )
        
        validated = ValidatedModelConfig(config, sample_odoo_fields)
        
        assert len(validated.fields) == 0
        assert len(validated.skipped_fields) == 2
        assert not validated.has_valid_primary_key
        assert validated.get_primary_key_field() is None

    def test_get_data_fields_excludes_primary_key(self, sample_odoo_fields):
        """Test that get_data_fields excludes primary key."""
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
                    indexed=True,
                ),
                FieldConfig(
                    odoo_field="name",
                    postgres_column="name",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
                FieldConfig(
                    odoo_field="email",
                    postgres_column="email",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
            ],
        )
        
        validated = ValidatedModelConfig(config, sample_odoo_fields)
        data_fields = validated.get_data_fields()
        
        assert len(data_fields) == 2
        assert all(not f.primary_key for f in data_fields)

    def test_get_foreign_key_fields(self, sample_odoo_fields):
        """Test getting foreign key fields."""
        # Add the foreign key field to Odoo fields
        odoo_fields_with_fk = {**sample_odoo_fields, "partner_category_id": {"type": "many2one"}}
        
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
                    odoo_field="partner_category_id",
                    postgres_column="category_id",
                    postgres_type="INTEGER",
                    nullable=True,
                    is_foreign_key=True,
                    field_type="many2one",
                    related_model="res.partner.category",
                ),
            ],
        )
        
        validated = ValidatedModelConfig(config, odoo_fields_with_fk)
        fk_fields = validated.get_foreign_key_fields()
        
        assert len(fk_fields) == 1
        assert fk_fields[0].odoo_field == "partner_category_id"

    def test_property_accessors(self, model_config_with_valid_fields, sample_odoo_fields):
        """Test property accessors delegate to original config."""
        validated = ValidatedModelConfig(model_config_with_valid_fields, sample_odoo_fields)
        
        assert validated.odoo_model == "res.partner"
        assert validated.postgres_table == "res_partner"
        assert validated.deletion_strategy() == "ignore"  # default

    def test_skipped_field_warning_message(self, model_config_with_invalid_fields, sample_odoo_fields):
        """Test that warning messages contain field and model info."""
        with patch("src.utils.logging.get_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            
            ValidatedModelConfig(model_config_with_invalid_fields, sample_odoo_fields)
            
            # Verify warning was called
            mock_logger.return_value.warning.assert_called()
            call_args = mock_logger.return_value.warning.call_args
            # Check that the warning mentions the model and skipped fields
            # Note: The mock captures the LAST warning (another_missing)
            warning_str = str(call_args)
            assert "res.partner" in warning_str
            assert "Skipping field" in warning_str


class TestFieldValidationResilience:
    """Test that field validation makes the sync resilient to Odoo changes."""

    def test_missing_field_does_not_crash_sync(self):
        """Simulate a missing field and verify sync continues."""
        # Odoo after upgrade doesn't have 'partner_category_id'
        odoo_fields = {
            "id": {"type": "integer"},
            "name": {"type": "char"},
            "email": {"type": "char"},
            "phone": {"type": "char"},
            "active": {"type": "boolean"},
        }
        
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
                    odoo_field="name",
                    postgres_column="name",
                    postgres_type="VARCHAR(255)",
                    nullable=True,
                ),
                FieldConfig(
                    odoo_field="partner_category_id",  # Doesn't exist in new Odoo
                    postgres_column="category_id",
                    postgres_type="INTEGER",
                    nullable=True,
                    is_foreign_key=True,
                ),
            ],
        )
        
        validated = ValidatedModelConfig(config, odoo_fields)
        
        # Sync should continue with just id and name
        assert len(validated.fields) == 2
        assert validated.has_valid_primary_key
        assert "partner_category_id" in validated.skipped_fields