"""Enhanced configuration models with advanced sync options."""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class FieldConfig(BaseModel):
    """Configuration for a single field mapping."""

    odoo_field: str = Field(..., description="Odoo field name")
    postgres_column: str = Field(..., description="PostgreSQL column name")
    postgres_type: str = Field(..., description="PostgreSQL data type")
    primary_key: bool = Field(default=False, description="Is this the primary key")
    nullable: bool = Field(default=True, description="Can the column be NULL")
    default_value: Optional[str] = Field(default=None, description="Default value for column")
    is_sync_date: bool = Field(default=False, description="Use this field for incremental sync")
    is_foreign_key: bool = Field(default=False, description="Is this a foreign key column")
    indexed: bool = Field(default=False, description="Create index on this column")
    description: Optional[str] = Field(default=None, description="Field description")
    field_type: Literal["many2one", "one2many", "many2many", "basic"] = Field(
        default="basic", description="Odoo field type for proper handling"
    )
    related_model: Optional[str] = Field(default=None, description="Related Odoo model for relational fields")


class ModelConfig(BaseModel):
    """Configuration for an Odoo model synchronization."""

    odoo_model: str = Field(..., description="Odoo model technical name")
    postgres_table: str = Field(..., description="PostgreSQL table name")
    description: Optional[str] = Field(default=None, description="Model description")
    fields: list[FieldConfig] = Field(default_factory=list, description="Field mappings")
    
    # Deletion strategy
    deletion_strategy: Literal["ignore", "soft_delete", "reconcile"] = Field(
        default="ignore", 
        description="How to handle records deleted in Odoo"
    )
    soft_delete_field: Optional[str] = Field(
        default=None, 
        description="Field name for soft delete (e.g., 'active')"
    )
    
    # Batch configuration
    batch_size: Optional[int] = Field(
        default=None, 
        description="Override default batch size for this model"
    )

    def get_primary_key_field(self) -> Optional[FieldConfig]:
        """Get the primary key field configuration."""
        for field in self.fields:
            if field.primary_key:
                return field
        return None

    def get_sync_date_field(self) -> Optional[FieldConfig]:
        """Get the sync date field for incremental sync."""
        for field in self.fields:
            if field.is_sync_date:
                return field
        return None

    def get_data_fields(self) -> list[FieldConfig]:
        """Get all non-primary key fields for data synchronization."""
        return [f for f in self.fields if not f.primary_key]
    
    def get_foreign_key_fields(self) -> list[FieldConfig]:
        """Get all foreign key fields."""
        return [f for f in self.fields if f.is_foreign_key]
    
    def get_indexed_fields(self) -> list[FieldConfig]:
        """Get all fields that should be indexed."""
        return [f for f in self.fields if f.indexed or f.is_sync_date or f.primary_key or f.is_foreign_key]


class SyncConfig(BaseModel):
    """Root configuration containing all model definitions."""

    models: list[ModelConfig] = Field(default_factory=list, description="All model configurations")
    
    # Global settings
    default_batch_size: int = Field(default=1000, description="Default batch size for all models")
    max_retries: int = Field(default=3, description="Maximum retry attempts for API failures")
    retry_delay_seconds: int = Field(default=5, description="Delay between retry attempts")
    
    # Global deletion strategy (can be overridden per model)
    default_deletion_strategy: Literal["ignore", "soft_delete", "reconcile"] = Field(
        default="ignore",
        description="Default deletion strategy if not specified per model"
    )

    def get_model_config(self, odoo_model: str) -> Optional[ModelConfig]:
        """Get configuration for a specific Odoo model."""
        for model in self.models:
            if model.odoo_model == odoo_model:
                return model
        return None

    def get_table_model(self, postgres_table: str) -> Optional[ModelConfig]:
        """Get configuration for a specific PostgreSQL table."""
        for model in self.models:
            if model.postgres_table == postgres_table:
                return model
        return None
    
    def get_effective_batch_size(self, model_config: ModelConfig) -> int:
        """Get the effective batch size for a model (model override or global default)."""
        return model_config.batch_size or self.default_batch_size