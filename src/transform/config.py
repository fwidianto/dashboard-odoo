"""Configuration models for the transformation engine.

This module defines the YAML schema for defining dashboard datasets.
The key concept is that YAML defines the OUTPUT schema (not Odoo fields),
and the engine handles translating these definitions into actual Odoo queries.
"""

from typing import Optional, Literal, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class FieldDefinition(BaseModel):
    """
    Definition of a single output field in a dataset.
    
    The 'path' is the most important concept - it defines how to extract
    data from Odoo records. It can be:
    - Simple: "product_uom_qty" (direct field)
    - Nested: "order_id.name" (follows relationship to get related field)
    - Computed: A Python expression using other field values
    
    Example YAML:
    
    ```yaml
    columns:
      order_reference:
        path: order_id.name  # Navigates to sale.order, then gets 'name'
      
      product_name:
        path: product_id.name  # Navigates to product.product, then gets 'name'
      
      revenue:
        compute: quantity * price_unit  # Computed from other fields
    ```
    """
    
    # The path to extract value from Odoo record (e.g., "order_id.name")
    # This supports dot notation for traversing relationships
    path: Optional[str] = Field(
        default=None,
        description="Dot-notation path to extract from Odoo record (e.g., 'order_id.name')"
    )
    
    # Python expression to compute value from other fields
    # Variables available: all field names defined in the same dataset
    compute: Optional[str] = Field(
        default=None,
        description="Python expression to compute value (e.g., 'quantity * price_unit')"
    )
    
    # Default value if path doesn't resolve (field is null/missing)
    default: Optional[Any] = Field(
        default=None,
        description="Default value if path resolves to null/missing"
    )
    
    # Human-readable label for dashboard display
    label: Optional[str] = Field(
        default=None,
        description="Display label for this field in dashboards"
    )
    
    # Data type hint (used for type conversion in output)
    type: Optional[Literal["string", "number", "boolean", "date", "datetime", "integer"]] = Field(
        default=None,
        description="Expected output data type"
    )
    
    # Whether this field is required (will raise error if missing)
    required: bool = Field(
        default=False,
        description="Whether this field is required (raises error if missing)"
    )
    
    # Format string for date/datetime fields
    format: Optional[str] = Field(
        default=None,
        description="Format string for date/datetime output (e.g., '%Y-%m-%d')"
    )
    
    # Round numeric values to N decimal places
    round: Optional[int] = Field(
        default=None,
        description="Round numeric output to N decimal places"
    )
    
    @model_validator(mode="after")
    def validate_path_or_compute(self) -> "FieldDefinition":
        """Ensure either path or compute is specified, but not both."""
        if self.path and self.compute:
            raise ValueError(
                f"Field cannot have both 'path' and 'compute'. "
                f"Use 'path' for direct extraction or 'compute' for calculations."
            )
        if not self.path and not self.compute:
            raise ValueError(
                "Field must specify either 'path' or 'compute'."
            )
        return self
    
    @property
    def is_path_based(self) -> bool:
        """Check if this field uses path-based extraction."""
        return self.path is not None
    
    @property
    def is_computed(self) -> bool:
        """Check if this field is computed."""
        return self.compute is not None
    
    def get_odoo_fields(self) -> list[str]:
        """
        Get list of Odoo field names that this definition uses.
        
        For path-based fields: returns the base field(s) needed
        For computed fields: parses the expression to find variable names
        """
        if self.path:
            # For "order_id.name", we need both "order_id" and "order_id.name"
            # The resolver will handle fetching related records
            return [self.path]
        elif self.compute:
            # Parse compute expression to find field references
            return self._parse_compute_expression()
        return []
    
    def _parse_compute_expression(self) -> list[str]:
        """Parse compute expression to extract field names."""
        if not self.compute:
            return []
        
        import re
        # Match field names (alphanumeric + underscore, not followed by parenthesis)
        # This is a simple parser - doesn't handle all edge cases
        pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b'
        matches = re.findall(pattern, self.compute)
        
        # Filter out Python keywords and common functions
        python_keywords = {
            'if', 'else', 'elif', 'for', 'while', 'def', 'class', 'return',
            'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None',
            'abs', 'round', 'min', 'max', 'sum', 'len', 'str', 'int', 'float',
        }
        
        return [m for m in matches if m not in python_keywords]


class DatasetConfig(BaseModel):
    """
    Configuration for a single dataset (report/endpoint).
    
    A dataset defines which Odoo model to query and how to transform
    the output fields for dashboard consumption.
    
    Example YAML:
    
    ```yaml
    datasets:
      sales_order_lines:
        model: sale.order.line
        description: "Sales order line items with order and product details"
        
        columns:
          order_reference:
            path: order_id.name
            label: "Order Reference"
          
          product_name:
            path: product_id.name
            label: "Product"
          
          quantity:
            path: product_uom_qty
            type: number
          
          revenue:
            compute: quantity * price_unit
            type: number
            round: 2
    ```
    """
    
    # Dataset identifier (used in API endpoints)
    name: str = Field(
        ...,
        description="Unique identifier for this dataset"
    )
    
    # Odoo model technical name
    model: str = Field(
        ...,
        description="Odoo model technical name (e.g., 'sale.order.line')"
    )
    
    # Human-readable description
    description: Optional[str] = Field(
        default=None,
        description="Description of this dataset for documentation"
    )
    
    # Column/field definitions
    columns: dict[str, FieldDefinition] = Field(
        default_factory=dict,
        description="Mapping of output column names to their definitions"
    )
    
    # Domain filter (Odoo domain syntax)
    domain: Optional[list] = Field(
        default=None,
        description="Odoo domain filter to apply to the query"
    )
    
    # Order by clause
    order: Optional[str] = Field(
        default=None,
        description="Odoo order clause (e.g., 'date_order desc, id')"
    )
    
    # Maximum records to return (0 = unlimited)
    limit: int = Field(
        default=0,
        description="Maximum number of records to return (0 = unlimited)"
    )
    
    # Batch size for reading records
    batch_size: int = Field(
        default=1000,
        description="Batch size for reading records from Odoo"
    )
    
    # Include only active records
    active_only: bool = Field(
        default=False,
        description="Only include active records (adds 'active = True' filter)"
    )
    
    @property
    def column_names(self) -> list[str]:
        """Get list of output column names."""
        return list(self.columns.keys())
    
    @property
    def path_based_fields(self) -> list[str]:
        """Get list of path-based field names."""
        return [name for name, col in self.columns.items() if col.is_path_based]
    
    @property
    def computed_fields(self) -> list[str]:
        """Get list of computed field names."""
        return [name for name, col in self.columns.items() if col.is_computed]
    
    def get_odoo_fields_to_fetch(self) -> list[str]:
        """
        Get the list of Odoo fields that need to be fetched.
        
        This includes:
        - All base fields from path definitions (e.g., "order_id" from "order_id.name")
        - All fields referenced in compute expressions
        """
        fields = set()
        
        for col_name, col_def in self.columns.items():
            if col_def.is_path_based:
                # Add the base field (first part of path)
                base_field = col_def.path.split('.')[0]
                fields.add(base_field)
            elif col_def.is_computed:
                # Add all fields referenced in compute expression
                fields.update(col_def.get_odoo_fields())
        
        return sorted(list(fields))


class TransformConfig(BaseModel):
    """
    Root configuration containing all dataset definitions.
    
    Example YAML:
    
    ```yaml
    config:
      version: "1.0"
      odoo:
        url: "https://odoo.example.com"
        db: "production"
        username: "api_user"
    
    datasets:
      sales_summary:
        model: sale.order
        columns:
          # ... columns ...
    ```
    """
    
    # Configuration version
    version: str = Field(
        default="1.0",
        description="Configuration version for compatibility"
    )
    
    # Dataset definitions
    datasets: dict[str, DatasetConfig] = Field(
        default_factory=dict,
        description="All dataset configurations"
    )
    
    def get_dataset(self, name: str) -> Optional[DatasetConfig]:
        """Get a specific dataset by name."""
        return self.datasets.get(name)
    
    def dataset_names(self) -> list[str]:
        """Get list of all dataset names."""
        return list(self.datasets.keys())


# =============================================================================
# YAML Loading Utilities
# =============================================================================

def load_transform_config(yaml_content: str) -> TransformConfig:
    """
    Load transform configuration from YAML content.
    
    Args:
        yaml_content: YAML string containing configuration
        
    Returns:
        Parsed TransformConfig object
    """
    import yaml
    
    data = yaml.safe_load(yaml_content)
    if not data:
        return TransformConfig()
    
    # Handle both direct config and wrapped config formats
    if "config" in data:
        # Wrapped format with 'config' key
        config_data = data["config"]
        config_data["datasets"] = data.get("datasets", {})
    else:
        # Direct format
        config_data = data.copy()
    
    # Inject dataset names from dictionary keys
    # YAML format: "sales_order_lines:\n  model: sale.order"
    # should become DatasetConfig with name="sales_order_lines"
    if "datasets" in config_data:
        for key, dataset_data in config_data["datasets"].items():
            if isinstance(dataset_data, dict):
                # Add the name from the YAML key if not already present
                if "name" not in dataset_data:
                    dataset_data["name"] = key
    
    return TransformConfig(**config_data)


def load_transform_config_from_file(filepath: str) -> TransformConfig:
    """
    Load transform configuration from a YAML file.
    
    Args:
        filepath: Path to YAML file
        
    Returns:
        Parsed TransformConfig object
    """
    with open(filepath, 'r') as f:
        content = f.read()
    return load_transform_config(content)