"""Transformation engine for YAML-defined dashboard datasets.

This module provides a robust solution for converting Odoo models into
clean JSON datasets for dashboards. It handles the critical issue where
Odoo relational fields like `order_id.name` are NOT real database fields
and `.read()` does not support nested dot notation reliably.

Key features:
- YAML defines OUTPUT schema (NOT Odoo fields)
- Path-based extraction with dot notation support
- Automatic related record fetching with caching
- Computed fields with Python expressions
- Type conversion and formatting
- Batch processing for large datasets

Example usage:

```python
from src.transform import (
    TransformationEngine,
    load_transform_config_from_file,
)

# Load YAML configuration
config = load_transform_config_from_file("datasets.yaml")

# Create engine with Odoo client
engine = TransformationEngine(odoo_client)

# Transform a dataset
result = engine.transform_dataset(config, "sales_order_lines")

# Get JSON output
print(result.to_json(indent=2))
```

Example YAML configuration:

```yaml
version: "1.0"

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

from src.transform.config import (
    FieldDefinition,
    DatasetConfig,
    TransformConfig,
    load_transform_config,
    load_transform_config_from_file,
)
from src.transform.path_resolver import (
    PathResolver,
    ResolutionResult,
    RelatedRecordCache,
)
from src.transform.engine import (
    TransformationEngine,
    TransformResult,
)

__all__ = [
    # Config
    "FieldDefinition",
    "DatasetConfig",
    "TransformConfig",
    "load_transform_config",
    "load_transform_config_from_file",
    # Path resolution
    "PathResolver",
    "ResolutionResult",
    "RelatedRecordCache",
    # Engine
    "TransformationEngine",
    "TransformResult",
]