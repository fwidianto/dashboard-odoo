"""Configuration loader for YAML-based model definitions."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from src.models.config import SyncConfig


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