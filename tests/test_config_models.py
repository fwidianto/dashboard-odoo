"""Unit tests for configuration models."""

import pytest
from pydantic import ValidationError

from src.models.config import FieldConfig, ModelConfig, SyncConfig


class TestFieldConfig:
    """Tests for FieldConfig model."""

    def test_valid_field_config(self):
        """Test creating a valid field configuration."""
        field = FieldConfig(
            odoo_field="name",
            postgres_column="name",
            postgres_type="VARCHAR(255)",
        )
        assert field.odoo_field == "name"
        assert field.postgres_column == "name"
        assert field.postgres_type == "VARCHAR(255)"
        assert field.primary_key is False
        assert field.nullable is True

    def test_field_with_all_options(self):
        """Test field with all options specified."""
        field = FieldConfig(
            odoo_field="id",
            postgres_column="id",
            postgres_type="INTEGER",
            primary_key=True,
            nullable=False,
            default_value="0",
            is_sync_date=True,
            description="Primary key field",
        )
        assert field.primary_key is True
        assert field.nullable is False
        assert field.default_value == "0"
        assert field.is_sync_date is True
        assert field.description == "Primary key field"

    def test_field_missing_required_fields(self):
        """Test that missing required fields raises error."""
        with pytest.raises(ValidationError):
            FieldConfig(odoo_field="name")


class TestModelConfig:
    """Tests for ModelConfig model."""

    def test_valid_model_config(self, sample_field_configs):
        """Test creating a valid model configuration."""
        model = ModelConfig(
            odoo_model="res.partner",
            postgres_table="res_partner",
            fields=sample_field_configs,
        )
        assert model.odoo_model == "res.partner"
        assert model.postgres_table == "res_partner"
        assert len(model.fields) == 4

    def test_get_primary_key_field(self, sample_model_config):
        """Test getting the primary key field."""
        pk = sample_model_config.get_primary_key_field()
        assert pk is not None
        assert pk.odoo_field == "id"
        assert pk.primary_key is True

    def test_get_sync_date_field(self, sample_model_config):
        """Test getting the sync date field."""
        sync_date = sample_model_config.get_sync_date_field()
        assert sync_date is not None
        assert sync_date.odoo_field == "write_date"
        assert sync_date.is_sync_date is True

    def test_get_data_fields(self, sample_model_config):
        """Test getting non-primary key fields."""
        data_fields = sample_model_config.get_data_fields()
        assert len(data_fields) == 3
        assert all(not f.primary_key for f in data_fields)

    def test_model_without_pk(self):
        """Test model without primary key field."""
        model = ModelConfig(
            odoo_model="test.model",
            postgres_table="test_table",
            fields=[
                FieldConfig(
                    odoo_field="name",
                    postgres_column="name",
                    postgres_type="VARCHAR(255)",
                ),
            ],
        )
        pk = model.get_primary_key_field()
        assert pk is None


class TestSyncConfig:
    """Tests for SyncConfig model."""

    def test_valid_sync_config(self, sample_model_config):
        """Test creating a valid sync configuration."""
        config = SyncConfig(models=[sample_model_config])
        assert len(config.models) == 1

    def test_get_model_config(self, sample_sync_config):
        """Test getting a model configuration by name."""
        model = sample_sync_config.get_model_config("res.partner")
        assert model is not None
        assert model.odoo_model == "res.partner"

    def test_get_nonexistent_model(self, sample_sync_config):
        """Test getting a non-existent model returns None."""
        model = sample_sync_config.get_model_config("nonexistent.model")
        assert model is None

    def test_get_table_model(self, sample_sync_config):
        """Test getting a model configuration by table name."""
        model = sample_sync_config.get_table_model("res_partner")
        assert model is not None
        assert model.postgres_table == "res_partner"