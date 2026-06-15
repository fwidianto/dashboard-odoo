"""Configuration models for YAML-based model definitions."""

from typing import Optional
from pydantic import BaseModel, Field


class FieldConfig(BaseModel):
    """Configuration for a single field mapping."""

    odoo_field: str = Field(..., description="Odoo field name")
    postgres_column: str = Field(..., description="PostgreSQL column name")
    postgres_type: str = Field(..., description="PostgreSQL data type")
    primary_key: bool = Field(default=False, description="Is this the primary key")
    nullable: bool = Field(default=True, description="Can the column be NULL")
    default_value: Optional[str] = Field(default=None, description="Default value for column")
    is_sync_date: bool = Field(default=False, description="Use this field for incremental sync")
    description: Optional[str] = Field(default=None, description="Field description")


class ModelConfig(BaseModel):
    """Configuration for an Odoo model synchronization."""

    odoo_model: str = Field(..., description="Odoo model technical name")
    postgres_table: str = Field(..., description="PostgreSQL table name")
    description: Optional[str] = Field(default=None, description="Model description")
    fields: list[FieldConfig] = Field(default_factory=list, description="Field mappings")

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


class SyncConfig(BaseModel):
    """Root configuration containing all model definitions."""

    models: list[ModelConfig] = Field(default_factory=list, description="All model configurations")

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