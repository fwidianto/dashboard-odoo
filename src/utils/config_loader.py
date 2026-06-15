"""Configuration loader for YAML-based model definitions.

Supports three formats:
1. Auto-detect format: Just model name (fetch all fields from Odoo)
   models:
     - odoo_model: purchase.order  # Auto-detects all fields!

2. Simple format: Just list field names
   models:
     - odoo_model: res.partner
       postgres_table: res_partner
       fields:
         - id
         - name
         - email

3. Verbose format: Full field definitions
   models:
     - odoo_model: res.partner
       postgres_table: res_partner
       fields:
         - odoo_field: id
           postgres_column: id
           postgres_type: INTEGER
           primary_key: true
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from src.models.config import SyncConfig, ModelConfig, FieldConfig


class ConfigLoader:
    """Loads and validates configuration from YAML files.
    
    Supports both simple and verbose field formats.
    """

    # Default type mappings from Odoo field types to PostgreSQL
    ODOO_TYPE_TO_POSTGRES = {
        'integer': 'INTEGER',
        'float': 'NUMERIC(20,4)',
        'monetary': 'NUMERIC(20,4)',
        'boolean': 'BOOLEAN',
        'char': 'TEXT',
        'text': 'TEXT',
        'selection': 'VARCHAR(255)',
        'date': 'DATE',
        'datetime': 'TIMESTAMP',
        'many2one': 'INTEGER',
        'one2many': 'SKIP',  # Not synced directly
        'many2many': 'SKIP',  # Not synced directly
        'binary': 'BYTEA',
        'html': 'TEXT',
        'reference': 'VARCHAR(255)',
    }

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
        
        # Auto-detect fields from Odoo if no fields specified
        models_data = self._auto_detect_fields_from_odoo(models_data)
        
        # Expand simple field formats (just field names) to full field definitions
        models_data = self._expand_simple_fields(models_data)

        # Build configuration
        config_dict = {
            **global_settings,
            "models": models_data,
        }

        config = SyncConfig(**config_dict)
        self._validate_config(config)
        
        return config
    
    def _expand_simple_fields(self, models_data: list) -> list:
        """
        Expand simple field formats to full field definitions.
        
        Supports:
        - Simple string: fields: [id, name, email]
        - Dict with just odoo_field: fields: [{odoo_field: id}, {odoo_field: name}]
        
        For odoo_field only:
        - postgres_column defaults to odoo_field name
        - postgres_type defaults to TEXT (can be overridden)
        - primary_key is auto-detected for 'id'
        - other flags default to false
        """
        expanded_models = []
        
        for model_data in models_data:
            model_data = model_data.copy()  # Don't mutate original
            fields = model_data.get("fields", [])
            
            if not fields:
                expanded_models.append(model_data)
                continue
            
            # Check if fields are in simple format (strings or single-key dicts)
            expanded_fields = []
            for field in fields:
                expanded = self._expand_single_field(field)
                if expanded:
                    expanded_fields.append(expanded)
            
            model_data["fields"] = expanded_fields
            expanded_models.append(model_data)
        
        return expanded_models
    
    def _expand_single_field(self, field) -> Optional[dict]:
        """
        Expand a single field definition.
        
        Formats supported:
        - String: "id" -> {odoo_field: id, postgres_column: id, ...}
        - Dict with just odoo_field: {odoo_field: "id"} -> full field def
        - Full dict: {odoo_field: "id", primary_key: true} -> unchanged
        """
        # String format: just field name
        if isinstance(field, str):
            field_name = field.strip()
            if not field_name:
                return None
            
            return self._create_field_config(field_name, field_name)
        
        # Dict format
        if isinstance(field, dict):
            # Full definition: has odoo_field AND postgres_type
            if field.get("odoo_field") and field.get("postgres_type"):
                return field
            
            # Partial or simple definition: expand it
            odoo_field = field.get("odoo_field")
            if odoo_field:
                # Extract known keys to pass as overrides, excluding odoo_field
                overrides = {k: v for k, v in field.items() if k != "odoo_field"}
                postgres_column = overrides.pop("postgres_column", odoo_field)
                return self._create_field_config(odoo_field, postgres_column, **overrides)
            
            return field
        
        return None
    
    def _create_field_config(
        self, 
        odoo_field: str, 
        postgres_column: str,
        **overrides
    ) -> dict:
        """
        Create a full field configuration from a field name.
        
        Auto-detects:
        - primary_key: True if field is 'id'
        - is_sync_date: True if field is 'write_date' or 'create_date'
        """
        config = {
            "odoo_field": odoo_field,
            "postgres_column": postgres_column,
            # postgres_type will be inferred from Odoo's fields_get() at runtime
            # For now, use TEXT as safe default (schema migration will fix types)
            "postgres_type": "TEXT",
            "nullable": True,
            "primary_key": False,
            "indexed": False,
            "is_sync_date": False,
            "is_foreign_key": False,
        }
        
        # Auto-detect primary key
        if odoo_field == "id":
            config["primary_key"] = True
            config["nullable"] = False
            config["indexed"] = True
            config["postgres_type"] = "INTEGER"
        
        # Auto-detect sync date fields
        if odoo_field in ("write_date", "create_date", "date"):
            config["is_sync_date"] = True
            config["indexed"] = True
            config["postgres_type"] = "TIMESTAMP"
        
        # Auto-detect many2one fields (end with _id)
        if odoo_field.endswith("_id") and odoo_field != "id":
            config["is_foreign_key"] = True
            config["indexed"] = True
            config["field_type"] = "many2one"
            # Extract related model from field name (e.g., partner_id -> res.partner)
            config["postgres_type"] = "INTEGER"
        
        # Auto-detect boolean fields
        if odoo_field in ("active", "is_active", "is_company"):
            config["postgres_type"] = "BOOLEAN"
        
        # Apply any overrides from YAML
        config.update(overrides)
        
        # Remove internal keys that shouldn't be in the config
        config.pop("odoo_field", None)  # Keep for reference
        # Actually keep it
        config["odoo_field"] = odoo_field
        
        return config

    def _auto_detect_fields_from_odoo(self, models_data: list) -> list:
        """
        Auto-detect fields from Odoo for models without fields specified.
        
        If a model has no 'fields' key, this will:
        1. Connect to Odoo using settings
        2. Call fields_get() on the model
        3. Generate field configs from Odoo's field definitions
        
        Supports:
        - Empty fields: fields: [] or fields: null
        - No fields key at all
        """
        from src.clients.odoo_client import OdooClient
        from src.utils.settings import get_settings
        from src.utils.logging import get_logger
        
        logger = get_logger(__name__)
        expanded_models = []
        
        for model_data in models_data:
            model_data = model_data.copy()
            
            # Check if fields need to be auto-detected
            if 'fields' not in model_data or not model_data['fields']:
                odoo_model = model_data.get('odoo_model')
                if not odoo_model:
                    expanded_models.append(model_data)
                    continue
                
                try:
                    # Connect to Odoo
                    settings = get_settings()
                    client = OdooClient(
                        url=settings.odoo_url,
                        db=settings.odoo_db,
                        username=settings.odoo_username,
                        api_key=settings.odoo_api_key,
                    )
                    
                    # Get fields from Odoo
                    logger.info("Auto-detecting fields from Odoo", model=odoo_model)
                    odoo_fields = client.get_model_fields(odoo_model)
                    
                    # Generate field configs
                    fields = self._generate_fields_from_odoo(odoo_model, odoo_fields)
                    model_data['fields'] = fields
                    
                    # Auto-generate table name if not specified
                    if 'postgres_table' not in model_data:
                        model_data['postgres_table'] = odoo_model.replace('.', '_')
                    
                    logger.info(
                        "Auto-detected fields",
                        model=odoo_model,
                        field_count=len(fields),
                    )
                    
                except Exception as e:
                    logger.warning(
                        "Failed to auto-detect fields from Odoo, using empty config",
                        model=odoo_model,
                        error=str(e),
                    )
                    model_data['fields'] = []
            
            expanded_models.append(model_data)
        
        return expanded_models
    
    def _generate_fields_from_odoo(self, model: str, fields_def: dict) -> list:
        """
        Generate field configs from Odoo fields_get() response.
        
        Args:
            model: Model name (for logging)
            fields_def: Dictionary from fields_get()
            
        Returns:
            List of field config dicts
        """
        fields = []
        
        for field_name, field_def in fields_def.items():
            config = self._create_field_from_odoo(field_name, field_def)
            if config:
                fields.append(config)
        
        return fields
    
    def _create_field_from_odoo(self, field_name: str, field_def: dict) -> Optional[dict]:
        """
        Create a field config from Odoo field definition.
        
        Args:
            field_name: Field technical name
            field_def: Field definition from fields_get()
            
        Returns:
            Field config dict or None if field should be skipped
        """
        odoo_type = field_def.get('type', 'char')
        
        # Skip one2many and many2many
        if odoo_type in ('one2many', 'many2many'):
            return None
        
        # Skip binary by default
        if odoo_type == 'binary':
            return None
        
        # Skip internal fields
        if field_name.startswith('__') or field_name in ('__last_update',):
            return None
        
        # Map Odoo type to PostgreSQL
        pg_type = self._map_odoo_type_to_postgres(odoo_type)
        
        config = {
            'odoo_field': field_name,
            'postgres_column': field_name,
            'postgres_type': pg_type,
            'nullable': not field_def.get('required', False),
        }
        
        # Primary key
        if field_name == 'id':
            config['primary_key'] = True
            config['nullable'] = False
            config['indexed'] = True
        
        # Foreign key (many2one)
        elif odoo_type == 'many2one':
            config['is_foreign_key'] = True
            config['indexed'] = True
            config['field_type'] = 'many2one'
            if 'relation' in field_def:
                config['related_model'] = field_def['relation']
        
        # Sync date fields
        elif field_name in ('write_date', 'create_date'):
            config['is_sync_date'] = True
            config['indexed'] = True
        
        return config
    
    def _map_odoo_type_to_postgres(self, odoo_type: str) -> str:
        """Map Odoo field type to PostgreSQL type."""
        type_map = {
            'integer': 'INTEGER',
            'bigint': 'BIGINT',
            'float': 'NUMERIC(20,4)',
            'monetary': 'NUMERIC(20,4)',
            'boolean': 'BOOLEAN',
            'char': 'TEXT',
            'text': 'TEXT',
            'selection': 'VARCHAR(255)',
            'date': 'DATE',
            'datetime': 'TIMESTAMP',
            'many2one': 'INTEGER',
            'binary': 'BYTEA',
            'html': 'TEXT',
            'reference': 'VARCHAR(255)',
        }
        return type_map.get(odoo_type, 'TEXT')

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
        """Get all fields that should be indexed (excluding primary keys)."""
        # Primary keys have their own constraint/index and don't need separate indexes
        # Even if primary_key field has indexed=True, we don't create a separate index
        return [f for f in self._valid_fields 
                if (f.indexed and not f.primary_key) or f.is_sync_date or f.is_foreign_key]

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