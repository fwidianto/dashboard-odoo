"""Transformation engine for converting Odoo records to dashboard datasets.

This engine takes YAML-defined dataset configurations and transforms
Odoo records into clean JSON datasets suitable for dashboard consumption.

Key features:
- YAML-defined output schema (not Odoo fields)
- Nested relationship resolution (order_id.name, etc.)
- Computed fields with Python expressions
- Batch processing for efficiency
- Type conversion and formatting
- Comprehensive error handling
"""

from typing import Any, Optional, Callable
from datetime import datetime, date
import re

from src.utils.logging import get_logger
from src.transform.config import (
    DatasetConfig,
    FieldDefinition,
    TransformConfig,
)
from src.transform.path_resolver import PathResolver, ResolutionResult


class TransformationEngine:
    """
    Main engine for transforming Odoo records to dashboard datasets.
    
    This engine:
    1. Reads records from Odoo based on dataset configuration
    2. Resolves nested paths using PathResolver
    3. Computes derived fields
    4. Applies type conversions and formatting
    5. Returns clean JSON datasets
    
    Example usage:
    
    ```python
    from src.transform import TransformationEngine, load_transform_config
    
    # Load configuration
    config = load_transform_config_from_file("datasets.yaml")
    
    # Create engine
    engine = TransformationEngine(odoo_client)
    
    # Transform records
    result = engine.transform_dataset(config, "sales_order_lines")
    
    print(result.to_dict())  # {"data": [...], "meta": {...}}
    ```
    """
    
    def __init__(
        self,
        odoo_client=None,
        field_metadata_cache: Optional[dict[str, dict[str, dict]]] = None
    ):
        """
        Initialize the transformation engine.
        
        Args:
            odoo_client: OdooClient instance for fetching data
            field_metadata_cache: Pre-loaded field metadata cache.
                                  Format: {model_name: {field_name: field_def}}
        """
        self._client = odoo_client
        self._logger = get_logger("transformation_engine")
        self._field_metadata_cache = field_metadata_cache or {}
        self._path_resolver = PathResolver(odoo_client)
    
    def transform_dataset(
        self,
        config: TransformConfig,
        dataset_name: str,
        domain_filter: Optional[list] = None,
        **options
    ) -> "TransformResult":
        """
        Transform a dataset based on configuration.
        
        Args:
            config: Transform configuration containing dataset definitions
            dataset_name: Name of the dataset to transform
            domain_filter: Additional Odoo domain filter (merged with config)
            **options: Additional options (limit, offset, etc.)
            
        Returns:
            TransformResult containing transformed data and metadata
            
        Raises:
            ValueError: If dataset_name not found in config
        """
        dataset = config.get_dataset(dataset_name)
        if not dataset:
            raise ValueError(f"Dataset '{dataset_name}' not found in configuration")
        
        self._logger.info(
            "Transforming dataset",
            dataset=dataset_name,
            model=dataset.model,
            columns=len(dataset.columns)
        )
        
        # Merge domain filters
        final_domain = self._merge_domains(dataset, domain_filter)
        
        # Build Odoo fields list
        odoo_fields = self._build_odoo_fields(dataset)
        
        # Read records from Odoo
        records = self._read_odoo_records(
            dataset,
            final_domain,
            odoo_fields,
            **options
        )
        
        # Transform records
        transformed = self._transform_records(
            records,
            dataset,
            odoo_fields
        )
        
        return TransformResult(
            dataset_name=dataset_name,
            data=transformed,
            record_count=len(transformed),
            source_record_count=len(records),
            fields=list(dataset.columns.keys()),
            model=dataset.model,
        )
    
    def transform_batch(
        self,
        config: TransformConfig,
        dataset_name: str,
        batch_size: int = 1000,
        domain_filter: Optional[list] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **options
    ) -> "TransformResult":
        """
        Transform a dataset in batches for large datasets.
        
        Args:
            config: Transform configuration
            dataset_name: Name of the dataset to transform
            batch_size: Number of records per batch
            domain_filter: Additional Odoo domain filter
            progress_callback: Optional callback(processed, total) for progress
            **options: Additional options
            
        Returns:
            TransformResult containing all transformed data
        """
        dataset = config.get_dataset(dataset_name)
        if not dataset:
            raise ValueError(f"Dataset '{dataset_name}' not found in configuration")
        
        self._logger.info(
            "Batch transforming dataset",
            dataset=dataset_name,
            model=dataset.model,
            batch_size=batch_size
        )
        
        # Get total count
        final_domain = self._merge_domains(dataset, domain_filter)
        total_count = self._client.count(dataset.model, final_domain) if self._client else 0
        
        # Read fields
        odoo_fields = self._build_odoo_fields(dataset)
        
        # Collect all transformed records
        all_transformed = []
        total_fetched = 0
        
        if self._client:
            for batch in self._client.read_batched(
                dataset.model,
                final_domain,
                fields=odoo_fields,
                batch_size=batch_size,
                order=dataset.order or "id",
                **options
            ):
                transformed = self._transform_records(
                    batch,
                    dataset,
                    odoo_fields
                )
                all_transformed.extend(transformed)
                total_fetched += len(batch)
                
                if progress_callback:
                    progress_callback(total_fetched, total_count)
        
        return TransformResult(
            dataset_name=dataset_name,
            data=all_transformed,
            record_count=len(all_transformed),
            source_record_count=total_fetched,
            fields=list(dataset.columns.keys()),
            model=dataset.model,
        )
    
    def _merge_domains(
        self,
        dataset: DatasetConfig,
        additional_domain: Optional[list] = None
    ) -> list:
        """Merge dataset domain with additional filter."""
        domain = dataset.domain or []
        
        if additional_domain:
            # Combine domains with AND
            if domain:
                domain = [domain, additional_domain]
            else:
                domain = additional_domain
        
        if dataset.active_only:
            # Add active filter
            if domain:
                domain = [domain, ['active', '=', True]]
            else:
                domain = [['active', '=', True]]
        
        return domain
    
    def _build_odoo_fields(self, dataset: DatasetConfig) -> list[str]:
        """
        Build the list of Odoo fields to fetch.
        
        This includes:
        - All base fields from path definitions
        - All fields referenced in compute expressions
        """
        return dataset.get_odoo_fields_to_fetch()
    
    def _read_odoo_records(
        self,
        dataset: DatasetConfig,
        domain: list,
        fields: list[str],
        **options
    ) -> list[dict]:
        """Read records from Odoo."""
        if not self._client:
            self._logger.warning(
                "No Odoo client - returning empty records",
                dataset=dataset.name
            )
            return []
        
        try:
            limit = options.get('limit', dataset.limit) or None
            
            records = self._client.search_read(
                model=dataset.model,
                domain=domain,
                fields=fields,
                offset=options.get('offset', 0),
                limit=limit,
                order=dataset.order,
            )
            
            self._logger.debug(
                "Read records from Odoo",
                dataset=dataset.name,
                count=len(records)
            )
            
            return records
            
        except Exception as e:
            self._logger.error(
                "Failed to read records from Odoo",
                dataset=dataset.name,
                error=str(e)
            )
            raise
    
    def _transform_records(
        self,
        records: list[dict],
        dataset: DatasetConfig,
        odoo_fields: list[str]
    ) -> list[dict]:
        """
        Transform a batch of Odoo records to output format.
        
        This is the core transformation logic that:
        1. Resolves paths for each record
        2. Computes derived fields
        3. Applies type conversions and formatting
        """
        if not records:
            return []
        
        # Get field metadata for path resolution
        field_metadata = self._get_field_metadata(dataset.model)
        
        # Clear cache for fresh batch
        self._path_resolver.clear_cache()
        
        # First pass: resolve all nested paths and collect IDs for batch fetching
        resolved_data = []
        for record in records:
            resolved_record = self._resolve_record_paths(
                record,
                dataset,
                field_metadata
            )
            resolved_data.append(resolved_record)
        
        # Second pass: compute derived fields
        for resolved_record in resolved_data:
            self._compute_record_fields(resolved_record, dataset)
        
        # Third pass: apply type conversions and formatting
        transformed = []
        for resolved_record in resolved_data:
            transformed_record = self._apply_transformations(
                resolved_record,
                dataset
            )
            transformed.append(transformed_record)
        
        return transformed
    
    def _resolve_record_paths(
        self,
        record: dict,
        dataset: DatasetConfig,
        field_metadata: dict[str, dict]
    ) -> dict:
        """Resolve all path-based fields for a single record."""
        resolved = {}
        
        for col_name, col_def in dataset.columns.items():
            if col_def.is_path_based:
                result = self._path_resolver.resolve_with_related(
                    record,
                    col_def.path,
                    field_metadata,
                    dataset.model,
                    default=col_def.default,
                    required=col_def.required
                )
                resolved[col_name] = result.value
            else:
                # Computed fields handled separately
                resolved[col_name] = None
        
        return resolved
    
    def _compute_record_fields(
        self,
        resolved_record: dict,
        dataset: DatasetConfig
    ) -> None:
        """Compute derived fields for a record."""
        for col_name, col_def in dataset.columns.items():
            if col_def.is_computed:
                try:
                    value = self._evaluate_compute_expression(
                        col_def.compute,
                        resolved_record,
                        dataset
                    )
                    resolved_record[col_name] = value
                except Exception as e:
                    self._logger.warning(
                        "Failed to compute field",
                        field=col_name,
                        expression=col_def.compute,
                        error=str(e)
                    )
                    resolved_record[col_name] = col_def.default
    
    def _evaluate_compute_expression(
        self,
        expression: str,
        record: dict,
        dataset: DatasetConfig
    ) -> Any:
        """
        Evaluate a compute expression against a record.
        
        The expression can reference:
        - Other column names from the same dataset
        - Python built-in functions (abs, round, min, max, etc.)
        
        Example: "quantity * price_unit"
        """
        # Build the evaluation namespace
        namespace = dict(record)
        
        # Add some useful functions
        namespace['abs'] = abs
        namespace['round'] = round
        namespace['min'] = min
        namespace['max'] = max
        namespace['sum'] = sum
        namespace['len'] = len
        namespace['str'] = str
        namespace['int'] = int
        namespace['float'] = float
        
        # Handle None values - replace with 0 for arithmetic
        # This allows "quantity * price_unit" to work even if one is None
        for key, value in list(namespace.items()):
            if value is None:
                namespace[key] = 0
        
        # Evaluate the expression
        result = eval(expression, {"__builtins__": {}}, namespace)
        return result
    
    def _apply_transformations(
        self,
        resolved_record: dict,
        dataset: DatasetConfig
    ) -> dict:
        """Apply type conversions and formatting to a record."""
        transformed = {}
        
        for col_name, col_def in dataset.columns.items():
            value = resolved_record.get(col_name)
            
            # Apply type conversion
            if col_def.type and value is not None:
                value = self._convert_type(value, col_def.type)
            
            # Apply rounding
            if col_def.round is not None and isinstance(value, (int, float)):
                value = round(value, col_def.round)
            
            # Apply date formatting
            if col_def.format and isinstance(value, (datetime, date)):
                value = value.strftime(col_def.format)
            
            # Handle null values
            if value is None:
                value = col_def.default
            
            transformed[col_name] = value
        
        return transformed
    
    def _convert_type(self, value: Any, target_type: str) -> Any:
        """Convert a value to the target type."""
        if value is None:
            return None
        
        try:
            if target_type == "integer":
                return int(value)
            elif target_type == "number":
                return float(value)
            elif target_type == "boolean":
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 'on')
                return bool(value)
            elif target_type == "string":
                return str(value)
            elif target_type == "date":
                if isinstance(value, str):
                    return value[:10]  # Just date part
                if isinstance(value, datetime):
                    return value.date().isoformat()
                return str(value)
            elif target_type == "datetime":
                if isinstance(value, str):
                    return value
                if isinstance(value, datetime):
                    return value.isoformat()
                if isinstance(value, date):
                    return datetime.combine(value, datetime.min.time()).isoformat()
                return str(value)
        except (ValueError, TypeError) as e:
            self._logger.warning(
                "Type conversion failed",
                value=value,
                target_type=target_type,
                error=str(e)
            )
            return value
        
        return value
    
    def _get_field_metadata(self, model: str) -> dict[str, dict]:
        """
        Get field metadata for a model.
        
        Uses cached metadata when available, fetches from Odoo if needed.
        """
        if model not in self._field_metadata_cache:
            if self._client:
                try:
                    fields_def = self._client.get_model_fields(model)
                    self._field_metadata_cache[model] = fields_def
                except Exception as e:
                    self._logger.warning(
                        "Failed to get field metadata",
                        model=model,
                        error=str(e)
                    )
                    self._field_metadata_cache[model] = {}
            else:
                self._field_metadata_cache[model] = {}
        
        return self._field_metadata_cache[model]
    
    def clear_metadata_cache(self) -> None:
        """Clear the field metadata cache."""
        self._field_metadata_cache.clear()
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "field_metadata_cache_size": len(self._field_metadata_cache),
            "related_record_cache_size": self._path_resolver.cache.size,
            "related_record_cache_stats": self._path_resolver.cache.stats(),
            "total_related_fetches": self._path_resolver.total_fetches,
        }


class TransformResult:
    """Result of a dataset transformation."""
    
    def __init__(
        self,
        dataset_name: str,
        data: list[dict],
        record_count: int,
        source_record_count: int,
        fields: list[str],
        model: str,
        errors: Optional[list[dict]] = None,
        execution_time_ms: Optional[float] = None,
    ):
        self.dataset_name = dataset_name
        self.data = data
        self.record_count = record_count
        self.source_record_count = source_record_count
        self.fields = fields
        self.model = model
        self.errors = errors or []
        self.execution_time_ms = execution_time_ms
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "dataset": self.dataset_name,
            "model": self.model,
            "meta": {
                "record_count": self.record_count,
                "source_record_count": self.source_record_count,
                "fields": self.fields,
                "execution_time_ms": self.execution_time_ms,
                "has_errors": len(self.errors) > 0,
            },
            "errors": self.errors if self.errors else None,
            "data": self.data,
        }
    
    def to_json(self, **kwargs) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.to_dict(), **kwargs)
    
    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    def __len__(self) -> int:
        """Return the number of records."""
        return self.record_count
    
    def __iter__(self):
        """Iterate over the data records."""
        return iter(self.data)