"""Configuration loader for YAML-based model definitions."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from src.models.config import SyncConfig, ModelConfig, FieldConfig


class ConfigLoader:
    """Loads and validates configuration from YAML files."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration loader.

        Args:
            config_path: Path to the models.yaml file. If None, uses default location.
        """
        if config_path is None:
            # Default to config/models.yaml in project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "models.yaml"
        
        self.config_path = Path(config_path)

    def load(self) -> SyncConfig:
        """
        Load and validate configuration from YAML file.

        Returns:
            SyncConfig: Validated configuration object.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValidationError: If configuration is invalid.
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            raw_config = yaml.safe_load(f)

        if raw_config is None:
            raise ValueError("Configuration file is empty")

        # Extract global settings
        global_settings = {
            "default_batch_size": raw_config.get("default_batch_size", 1000),
            "max_retries": raw_config.get("max_retries", 3),
            "retry_delay_seconds": raw_config.get("retry_delay_seconds", 5),
            "default_deletion_strategy": raw_config.get("default_deletion_strategy", "ignore"),
        }

        # Extract models
        models_data = raw_config.get("models", [])

        # Build configuration
        config_dict = {
            **global_settings,
            "models": models_data,
        }

        config = SyncConfig(**config_dict)
        self._validate_config(config)
        
        return config

    def _validate_config(self, config: SyncConfig) -> None:
        """
        Validate configuration consistency.

        Args:
            config: Configuration to validate.

        Raises:
            ValueError: If configuration has issues.
        """
        table_names = set()
        model_names = set()

        for model in config.models:
            # Check for duplicate table names
            if model.postgres_table in table_names:
                raise ValueError(
                    f"Duplicate table name '{model.postgres_table}' in models"
                )
            table_names.add(model.postgres_table)

            # Check for duplicate model names
            if model.odoo_model in model_names:
                raise ValueError(
                    f"Duplicate model name '{model.odoo_model}' in models"
                )
            model_names.add(model.odoo_model)

            # Check that each model has exactly one primary key
            pk_count = sum(1 for f in model.fields if f.primary_key)
            if pk_count != 1:
                raise ValueError(
                    f"Model '{model.odoo_model}' must have exactly one primary key, "
                    f"found {pk_count}"
                )

            # Check for duplicate column names
            column_names = set()
            for field in model.fields:
                if field.postgres_column in column_names:
                    raise ValueError(
                        f"Duplicate column name '{field.postgres_column}' in model "
                        f"'{model.odoo_model}'"
                    )
                column_names.add(field.postgres_column)

    def reload(self) -> SyncConfig:
        """
        Reload configuration from disk.

        Returns:
            SyncConfig: Newly loaded configuration.
        """
        return self.load()


class ValidatedModelConfig:
    """
    Model configuration with Odoo field validation.
    
    This class wraps ModelConfig and validates fields against actual Odoo fields
    at initialization time. Invalid fields are skipped with warnings.
    """

    def __init__(self, model_config: ModelConfig, odoo_fields: dict):
        """
        Initialize validated model config.

        Args:
            model_config: The original model configuration.
            odoo_fields: Dictionary of actual Odoo field definitions from fields_get().
        """
        self._original_config = model_config
        self._odoo_fields = odoo_fields
        self._skipped_fields: list[str] = []
        self._valid_fields: list[FieldConfig] = []
        
        self._validate_and_filter_fields()

    def _validate_and_filter_fields(self) -> None:
        """Validate fields against Odoo and filter out invalid ones."""
        from src.utils.logging import get_logger
        logger = get_logger("config_validation")

        for field in self._original_config.fields:
            if field.odoo_field in self._odoo_fields:
                self._valid_fields.append(field)
            else:
                # Field not found in Odoo - skip it gracefully
                self._skipped_fields.append(field.odoo_field)
                logger.warning(
                    f"Field '{field.odoo_field}' not found on model '{self._original_config.odoo_model}'. "
                    f"Skipping field and continuing sync.",
                    field=field.odoo_field,
                    model=self._original_config.odoo_model,
                    postgres_column=field.postgres_column,
                )

    @property
    def odoo_model(self) -> str:
        """Get the Odoo model name."""
        return self._original_config.odoo_model

    @property
    def postgres_table(self) -> str:
        """Get the PostgreSQL table name."""
        return self._original_config.postgres_table

    @property
    def description(self) -> Optional[str]:
        """Get the model description."""
        return self._original_config.description

    @property
    def fields(self) -> list[FieldConfig]:
        """Get the validated fields (excluding invalid ones)."""
        return self._valid_fields

    @property
    def skipped_fields(self) -> list[str]:
        """Get list of fields that were skipped."""
        return self._skipped_fields

    @property
    def has_valid_primary_key(self) -> bool:
        """Check if there's a valid primary key field."""
        return any(f.primary_key for f in self._valid_fields)

    @property
    def has_sync_date_field(self) -> bool:
        """Check if there's a sync date field."""
        return any(f.is_sync_date for f in self._valid_fields)

    def get_primary_key_field(self) -> Optional[FieldConfig]:
        """Get the primary key field configuration."""
        for field in self._valid_fields:
            if field.primary_key:
                return field
        return None

    def get_sync_date_field(self) -> Optional[FieldConfig]:
        """Get the sync date field for incremental sync."""
        for field in self._valid_fields:
            if field.is_sync_date:
                return field
        return None

    def get_data_fields(self) -> list[FieldConfig]:
        """Get all non-primary key fields for data synchronization."""
        return [f for f in self._valid_fields if not f.primary_key]
    
    def get_foreign_key_fields(self) -> list[FieldConfig]:
        """Get all foreign key fields."""
        return [f for f in self._valid_fields if f.is_foreign_key]
    
    def get_indexed_fields(self) -> list[FieldConfig]:
        """Get all fields that should be indexed."""
        return [f for f in self._valid_fields 
                if f.indexed or f.is_sync_date or f.primary_key or f.is_foreign_key]

    def deletion_strategy(self) -> str:
        """Get the deletion strategy."""
        return self._original_config.deletion_strategy

    @property
    def soft_delete_field(self) -> Optional[str]:
        """Get the soft delete field name."""
        return self._original_config.soft_delete_field

    @property
    def batch_size(self) -> Optional[int]:
        """Get the batch size override."""
        return self._original_config.batch_size


def get_config(config_path: Optional[str] = None) -> SyncConfig:
    """
    Convenience function to load configuration.

    Args:
        config_path: Optional path to configuration file.

    Returns:
        SyncConfig: Loaded configuration.
    """
    loader = ConfigLoader(config_path)
    return loader.load()