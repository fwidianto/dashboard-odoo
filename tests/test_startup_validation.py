"""Integration tests for startup validation.

These tests verify:
- Settings load successfully
- .env is parsed correctly
- models.yaml is valid
- Logger initializes correctly
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from src.utils.settings import get_settings, Settings
from src.utils.config_loader import ConfigLoader, get_config
from src.utils.logging import setup_logging, get_logger
from src.utils.validation import Validator, validate, ValidationResult
from src.models.config import FieldConfig, ModelConfig, SyncConfig


class TestSettingsLoading:
    """Tests for settings loading."""

    def test_default_settings_load(self):
        """Test that default settings load successfully."""
        # Clear any cached settings
        get_settings.cache_clear()
        
        settings = get_settings()
        
        assert settings is not None
        assert settings.odoo_url == "http://localhost:8069"
        assert settings.odoo_db == "odoo_db"
        assert settings.postgres_host == "localhost"
        assert settings.postgres_port == 5432

    def test_settings_with_env_vars(self):
        """Test settings load from environment variables."""
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {
            "ODOO_URL": "http://test-odoo:8069",
            "ODOO_DB": "test_db",
            "ODOO_USERNAME": "test_user",
            "ODOO_API_KEY": "test_key",
            "POSTGRES_HOST": "test-pg",
            "POSTGRES_DB": "test_sync_db",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_pass",
        }):
            settings = get_settings()
            
            assert settings.odoo_url == "http://test-odoo:8069"
            assert settings.odoo_db == "test_db"
            assert settings.odoo_username == "test_user"
            assert settings.odoo_api_key == "test_key"
            assert settings.postgres_host == "test-pg"
            assert settings.postgres_db == "test_sync_db"

    def test_odoo_nested_settings(self):
        """Test Odoo settings property returns proper object."""
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {
            "ODOO_URL": "http://test:8069",
            "ODOO_DB": "test",
            "ODOO_USERNAME": "admin",
            "ODOO_API_KEY": "key123",
        }):
            settings = get_settings()
            odoo = settings.odoo
            
            assert odoo.url == "http://test:8069"
            assert odoo.db == "test"
            assert odoo.username == "admin"
            assert odoo.api_key == "key123"
            assert odoo.has_credentials() is True

    def test_postgres_nested_settings(self):
        """Test PostgreSQL settings property returns proper object."""
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {
            "POSTGRES_HOST": "pg.example.com",
            "POSTGRES_PORT": "5433",
            "POSTGRES_DB": "mydb",
            "POSTGRES_USER": "myuser",
            "POSTGRES_PASSWORD": "mypass",
        }):
            settings = get_settings()
            pg = settings.postgres
            
            assert pg.host == "pg.example.com"
            assert pg.port == 5433
            assert pg.db == "mydb"
            assert pg.user == "myuser"
            assert pg.has_credentials() is True
            
            # Check connection URL
            assert "pg.example.com" in pg.connection_url
            assert "mydb" in pg.connection_url


class TestConfigLoader:
    """Tests for configuration loader."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file."""
        config = {
            "default_batch_size": 500,
            "models": [
                {
                    "odoo_model": "res.partner",
                    "postgres_table": "res_partner",
                    "fields": [
                        {
                            "odoo_field": "id",
                            "postgres_column": "id",
                            "postgres_type": "INTEGER",
                            "primary_key": True,
                            "nullable": False,
                        },
                        {
                            "odoo_field": "name",
                            "postgres_column": "name",
                            "postgres_type": "VARCHAR(255)",
                        },
                        {
                            "odoo_field": "active",
                            "postgres_column": "active",
                            "postgres_type": "BOOLEAN",
                            "default_value": True,  # Boolean
                        },
                        {
                            "odoo_field": "write_date",
                            "postgres_column": "write_date",
                            "postgres_type": "TIMESTAMP",
                            "is_sync_date": True,
                        },
                    ],
                },
            ],
        }
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False
        ) as f:
            yaml.dump(config, f)
            yield f.name
        
        os.unlink(f.name)

    def test_load_valid_config(self, temp_config_file):
        """Test loading a valid configuration."""
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config is not None
        assert len(config.models) == 1
        assert config.models[0].odoo_model == "res.partner"
        assert config.default_batch_size == 500

    def test_default_value_types(self, temp_config_file):
        """Test that default_value supports different types."""
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        # Find the active field
        active_field = None
        for field in config.models[0].fields:
            if field.odoo_field == "active":
                active_field = field
                break
        
        assert active_field is not None
        assert active_field.default_value is True  # Boolean from YAML
        assert isinstance(active_field.default_value, bool)

    def test_load_missing_file(self):
        """Test that missing file raises FileNotFoundError."""
        loader = ConfigLoader("/nonexistent/path/config.yaml")
        
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_simple_string_fields(self):
        """Test simple format with just field names as strings."""
        config_data = {
            "models": [
                {
                    "odoo_model": "res.partner",
                    "postgres_table": "res_partner",
                    "fields": ["id", "name", "email", "write_date"],
                },
            ],
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            loader = ConfigLoader(temp_path)
            config = loader.load()
            
            assert len(config.models) == 1
            model = config.models[0]
            assert model.odoo_model == "res.partner"
            
            # Check field expansion
            field_names = [f.odoo_field for f in model.fields]
            assert "id" in field_names
            assert "name" in field_names
            assert "email" in field_names
            assert "write_date" in field_names
            
            # Check auto-detection
            id_field = next(f for f in model.fields if f.odoo_field == "id")
            assert id_field.primary_key is True
            assert id_field.postgres_type == "INTEGER"
            
            write_field = next(f for f in model.fields if f.odoo_field == "write_date")
            assert write_field.is_sync_date is True
            assert write_field.postgres_type == "TIMESTAMP"
            
        finally:
            os.unlink(temp_path)

    def test_simple_dict_fields(self):
        """Test simple format with dict containing odoo_field name."""
        config_data = {
            "models": [
                {
                    "odoo_model": "res.partner",
                    "postgres_table": "res_partner",
                    "fields": [
                        {"odoo_field": "id"},
                        {"odoo_field": "name"},
                        {"odoo_field": "partner_id", "indexed": True},
                    ],
                },
            ],
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            loader = ConfigLoader(temp_path)
            config = loader.load()
            
            model = config.models[0]
            
            # Check partner_id has correct auto-detections
            partner_id_field = next(f for f in model.fields if f.odoo_field == "partner_id")
            assert partner_id_field.is_foreign_key is True
            assert partner_id_field.indexed is True
            assert partner_id_field.postgres_type == "INTEGER"
            
        finally:
            os.unlink(temp_path)

    def test_mixed_format_fields(self):
        """Test mixing simple and verbose field definitions."""
        config_data = {
            "models": [
                {
                    "odoo_model": "res.partner",
                    "postgres_table": "res_partner",
                    "fields": [
                        "id",  # Simple string
                        {"odoo_field": "name", "indexed": True},  # Simple dict with override
                        {
                            "odoo_field": "email",
                            "postgres_column": "email_address",
                            "postgres_type": "VARCHAR(255)",  # Full definition
                        },
                    ],
                },
            ],
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name
        
        try:
            loader = ConfigLoader(temp_path)
            config = loader.load()
            
            model = config.models[0]
            
            # id should be auto-detected as primary key
            id_field = next(f for f in model.fields if f.odoo_field == "id")
            assert id_field.primary_key is True
            
            # name should have indexed=True from override
            name_field = next(f for f in model.fields if f.odoo_field == "name")
            assert name_field.indexed is True
            
            # email should have custom column name and type from full definition
            email_field = next(f for f in model.fields if f.odoo_field == "email")
            assert email_field.postgres_column == "email_address"
            assert email_field.postgres_type == "VARCHAR(255)"
            
        finally:
            os.unlink(temp_path)


class TestConfigModels:
    """Tests for configuration models."""

    def test_field_config_typed_defaults(self):
        """Test FieldConfig with different default_value types."""
        # Boolean
        field_bool = FieldConfig(
            odoo_field="active",
            postgres_column="active",
            postgres_type="BOOLEAN",
            default_value=True,
        )
        assert field_bool.default_value is True
        assert isinstance(field_bool.default_value, bool)
        
        # Integer
        field_int = FieldConfig(
            odoo_field="sequence",
            postgres_column="sequence",
            postgres_type="INTEGER",
            default_value=42,
        )
        assert field_int.default_value == 42
        assert isinstance(field_int.default_value, int)
        
        # Float
        field_float = FieldConfig(
            odoo_field="amount",
            postgres_column="amount",
            postgres_type="NUMERIC(10,2)",
            default_value=15.5,
        )
        assert field_float.default_value == 15.5
        assert isinstance(field_float.default_value, float)
        
        # String
        field_str = FieldConfig(
            odoo_field="state",
            postgres_column="state",
            postgres_type="VARCHAR(32)",
            default_value="active",
        )
        assert field_str.default_value == "active"
        assert isinstance(field_str.default_value, str)

    def test_get_typed_default_value(self):
        """Test get_typed_default_value method."""
        # Test boolean parsing
        field = FieldConfig(
            odoo_field="test",
            postgres_column="test",
            postgres_type="BOOLEAN",
            default_value=True,
        )
        assert field.get_typed_default_value() is True
        
        # Test integer parsing from string
        field = FieldConfig(
            odoo_field="test",
            postgres_column="test",
            postgres_type="INTEGER",
            default_value="0",
        )
        assert field.get_typed_default_value() == 0
        
        # Test float parsing from string
        field = FieldConfig(
            odoo_field="test",
            postgres_column="test",
            postgres_type="NUMERIC(10,2)",
            default_value="15.5",
        )
        assert field.get_typed_default_value() == 15.5
        
        # Test None
        field = FieldConfig(
            odoo_field="test",
            postgres_column="test",
            postgres_type="VARCHAR(255)",
        )
        assert field.get_typed_default_value() is None


class TestLogging:
    """Tests for logging configuration."""

    def test_setup_logging(self):
        """Test logging setup doesn't crash."""
        logger = setup_logging(log_level="INFO")
        assert logger is not None

    def test_get_logger(self):
        """Test getting a logger."""
        # Setup first
        setup_logging(log_level="DEBUG")
        
        logger = get_logger("test")
        assert logger is not None
        
        # Named logger should have correct name
        named_logger = get_logger("sync")
        assert named_logger is not None

    def test_logging_with_exception(self):
        """Test that logging exceptions doesn't crash."""
        setup_logging(log_level="DEBUG")
        logger = get_logger("test")
        
        # Should not raise
        try:
            raise ValueError("Test error")
        except ValueError:
            logger.exception("An error occurred")


class TestValidation:
    """Tests for validation module."""

    def test_validation_result_str(self):
        """Test ValidationResult string representation."""
        from src.utils.validation import ValidationError, ValidationResult
        
        # Valid result
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        assert "passed" in str(result)
        
        # Invalid result
        result = ValidationResult(
            is_valid=False,
            errors=[
                ValidationError(
                    category="env",
                    message="Missing credentials",
                    hint="Set ODOO_API_KEY",
                )
            ],
            warnings=[],
        )
        result_str = str(result)
        assert "failed" in result_str
        assert "ENV" in result_str  # Uppercase in output
        assert "Missing credentials" in result_str

    def test_validator_environment_check(self):
        """Test validator checks environment."""
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {
            "ODOO_API_KEY": "test_key",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_DB": "testdb",
            "POSTGRES_USER": "user",
            "POSTGRES_PASSWORD": "pass",
        }):
            validator = Validator()
            errors, warnings = validator.validate_environment()
            
            # Should have no errors with valid credentials
            assert len(errors) == 0 or all(e.category == "config" for e in errors)

    def test_validation_result_formats_warnings(self):
        """Test that validation result formats warnings."""
        from src.utils.validation import ValidationError, ValidationResult
        
        # Create result with warnings - needs to be invalid to show in __str__
        result = ValidationResult(
            is_valid=False,  # Invalid result
            errors=[
                ValidationError(
                    category="config",
                    message="Test error",
                    hint=None,
                )
            ],
            warnings=["Consider using API keys"],
        )
        
        result_str = str(result)
        # Warnings section should be included
        assert "Warning" in result_str
        assert "API keys" in result_str


class TestStartupValidation:
    """Integration tests for complete startup validation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear settings cache before each test."""
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_full_validation_flow(self):
        """Test complete validation flow."""
        with patch.dict(os.environ, {
            "ODOO_URL": "http://localhost:8069",
            "ODOO_DB": "test",
            "ODOO_USERNAME": "admin",
            "ODOO_API_KEY": "test_key",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_DB": "testdb",
            "POSTGRES_USER": "user",
            "POSTGRES_PASSWORD": "pass",
        }):
            # Should not raise
            result = validate()
            assert isinstance(result, ValidationResult)

    def test_validation_without_credentials(self):
        """Test validation handles missing credentials gracefully."""
        # Clear all credentials
        with patch.dict(os.environ, {}, clear=True):
            result = validate()
            
            # Should return result, not raise
            assert isinstance(result, ValidationResult)
            
            # Should have errors about missing credentials
            env_errors = [e for e in result.errors if e.category == "env"]
            assert len(env_errors) > 0


class TestReadOnlyMode:
    """Tests for read-only mode enforcement."""

    def test_read_only_mode_defaults_true(self):
        """Test that read_only_mode defaults to True."""
        get_settings.cache_clear()
        
        settings = get_settings()
        assert settings.read_only_mode is True
        assert settings.sync.read_only_mode is True

    def test_read_only_mode_from_env(self):
        """Test read_only_mode can be set from environment."""
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {"READ_ONLY_MODE": "true"}):
            settings = get_settings()
            assert settings.read_only_mode is True
        
        get_settings.cache_clear()
        
        with patch.dict(os.environ, {"READ_ONLY_MODE": "false"}):
            settings = get_settings()
            assert settings.read_only_mode is False
