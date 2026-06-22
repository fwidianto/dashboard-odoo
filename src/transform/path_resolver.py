"""Path resolver for extracting nested values from Odoo records.

This module solves the critical issue with Odoo relational fields:
- `.read()` does NOT support nested dot notation (e.g., "order_id.name")
- Many2one fields return only IDs, not related values

The PathResolver handles:
1. Extracting direct fields from Odoo records
2. Resolving nested paths like "order_id.name" by fetching related records
3. Caching related records to avoid redundant API calls
4. Graceful handling of missing/null relationships
"""

from typing import Any, Optional
from dataclasses import dataclass, field
from src.utils.logging import get_logger


@dataclass
class ResolutionResult:
    """Result of resolving a path against an Odoo record."""
    
    # The resolved value
    value: Any
    
    # Whether the resolution was successful
    success: bool
    
    # Error message if resolution failed
    error: Optional[str] = None
    
    # Whether the value was null/missing
    was_null: bool = False
    
    # Number of related records fetched during resolution
    related_fetches: int = 0


class RelatedRecordCache:
    """
    Cache for related records to avoid redundant API calls.
    
    When resolving paths like "order_id.name", we need to fetch
    the related order record. This cache stores fetched records
    by their model and ID to avoid fetching the same record multiple times.
    """
    
    def __init__(self):
        self._cache: dict[tuple[str, int], dict] = {}
        self._logger = get_logger("path_resolver.cache")
    
    def get(self, model: str, record_id: int) -> Optional[dict]:
        """Get a cached related record."""
        key = (model, record_id)
        return self._cache.get(key)
    
    def set(self, model: str, record_id: int, record: dict) -> None:
        """Cache a related record."""
        key = (model, record_id)
        self._cache[key] = record
    
    def set_batch(self, model: str, records: list[dict]) -> None:
        """Cache multiple records of the same model."""
        for record in records:
            record_id = record.get('id')
            if record_id:
                self.set(model, record_id, record)
    
    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
    
    @property
    def size(self) -> int:
        """Number of cached records."""
        return len(self._cache)
    
    def stats(self) -> dict[str, int]:
        """Get cache statistics by model."""
        stats: dict[str, int] = {}
        for (model, _), _ in self._cache.items():
            stats[model] = stats.get(model, 0) + 1
        return stats


class PathResolver:
    """
    Resolves dot-notation paths against Odoo records.
    
    This resolver handles paths like:
    - "product_uom_qty" - Direct field
    - "order_id" - Many2one field (returns ID)
    - "order_id.name" - Nested: fetches related order, returns its name
    - "order_id.partner_id.name" - Double nested
    
    Key features:
    - Caches related records to minimize API calls
    - Handles missing/null relationships gracefully
    - Supports batch fetching of related records
    - Tracks fetch statistics for debugging
    """
    
    def __init__(self, odoo_client=None):
        """
        Initialize the path resolver.
        
        Args:
            odoo_client: OdooClient instance for fetching related records.
                        If None, path resolution will return None for nested paths.
        """
        self._client = odoo_client
        self._cache = RelatedRecordCache()
        self._logger = get_logger("path_resolver")
        self._fetch_count = 0
    
    @property
    def cache(self) -> RelatedRecordCache:
        """Access the related record cache."""
        return self._cache
    
    def resolve(
        self, 
        record: dict, 
        path: str, 
        default: Any = None,
        required: bool = False
    ) -> ResolutionResult:
        """
        Resolve a dot-notation path against an Odoo record.
        
        Args:
            record: The source Odoo record (from search_read or read)
            path: Dot-notation path (e.g., "order_id.name", "product_id.product_tmpl_id.name")
            default: Default value if path doesn't resolve
            required: If True, log warning when value is missing
            
        Returns:
            ResolutionResult containing the resolved value and metadata
        """
        if not path:
            return ResolutionResult(
                value=default,
                success=False,
                error="Empty path provided",
                was_null=True
            )
        
        # Split path into parts
        parts = path.split('.')
        
        # Start with the base record
        current_value = record
        
        for i, part in enumerate(parts):
            if current_value is None:
                # Can't traverse further - path doesn't exist
                return self._create_null_result(
                    path, default, required, 
                    error=f"Path truncated at '{part}' - parent is null"
                )
            
            if isinstance(current_value, dict):
                # Get value from current dict
                current_value = current_value.get(part)
            else:
                # Current value is not a dict - can't continue
                return self._create_null_result(
                    path, default, required,
                    error=f"Cannot traverse non-dict value at '{part}'"
                )
        
        # Handle the final value
        if current_value is None:
            return self._create_null_result(path, default, required)
        
        # Check if it's a many2one ID that needs resolution
        if isinstance(current_value, int):
            # This is a raw ID - we can't resolve it without context
            # Return the ID as-is
            return ResolutionResult(
                value=current_value,
                success=True,
                was_null=False
            )
        
        return ResolutionResult(
            value=current_value,
            success=True,
            was_null=False
        )
    
    def resolve_with_related(
        self,
        record: dict,
        path: str,
        field_metadata: dict[str, dict],
        model: str,
        default: Any = None,
        required: bool = False
    ) -> ResolutionResult:
        """
        Resolve a path, fetching related records when needed.
        
        This is the main entry point for resolving paths that may involve
        nested relationships. It will:
        1. Check if the path involves a many2one field
        2. Fetch the related record(s) if needed
        3. Extract the nested value
        
        Args:
            record: The source Odoo record
            path: Dot-notation path (e.g., "order_id.name")
            field_metadata: Field definitions from fields_get()
            model: The current model name
            default: Default value if path doesn't resolve
            required: If True, log warning when value is missing
            
        Returns:
            ResolutionResult with the resolved value
        """
        parts = path.split('.')
        
        if len(parts) == 1:
            # Simple field - no relationship traversal needed
            return self.resolve(record, path, default, required)
        
        # Multi-part path - need to traverse relationships
        return self._resolve_nested_path(
            record, parts, field_metadata, model, default, required
        )
    
    def _resolve_nested_path(
        self,
        record: dict,
        parts: list[str],
        field_metadata: dict[str, dict],
        model: str,
        default: Any,
        required: bool
    ) -> ResolutionResult:
        """
        Resolve a nested path by traversing relationships.
        
        For path "order_id.name":
        1. Get order_id from record (it's an ID like 1234)
        2. Fetch the sale.order record with id=1234, requesting 'name' field
        3. Return the 'name' value from that record
        """
        base_field = parts[0]
        rest_path = '.'.join(parts[1:])
        
        # Get the base value (should be an ID for many2one)
        base_value = record.get(base_field)
        
        if base_value is None:
            return self._create_null_result(
                '.'.join(parts), default, required,
                error=f"Base field '{base_field}' is null"
            )
        
        if isinstance(base_value, int):
            # It's a raw ID - need to fetch the related record
            related_model = self._get_related_model(base_field, field_metadata, model)
            
            if related_model and self._client:
                # Fetch the related record
                related_record = self._fetch_related_record(
                    related_model, base_value, [rest_path]
                )
                
                if related_record:
                    # Now resolve the rest of the path against the related record
                    return self.resolve(related_record, rest_path, default, required)
                else:
                    return self._create_null_result(
                        '.'.join(parts), default, required,
                        error=f"Related record not found: {related_model}/{base_value}"
                    )
            else:
                # Can't fetch - return the ID
                return ResolutionResult(
                    value=base_value,
                    success=True,
                    was_null=False,
                    related_fetches=0
                )
        elif isinstance(base_value, dict):
            # The value is already a related record dict (expanded in read)
            return self.resolve(base_value, rest_path, default, required)
        else:
            # Unexpected type
            return self._create_null_result(
                '.'.join(parts), default, required,
                error=f"Unexpected type for '{base_field}': {type(base_value)}"
            )
    
    def _get_related_model(
        self, 
        field_name: str, 
        field_metadata: dict[str, dict],
        current_model: str
    ) -> Optional[str]:
        """Get the related model for a field."""
        field_def = field_metadata.get(field_name, {})
        return field_def.get('relation')
    
    def _fetch_related_record(
        self,
        model: str,
        record_id: int,
        fields: list[str]
    ) -> Optional[dict]:
        """
        Fetch a single related record from Odoo.
        
        Uses the cache when possible to avoid redundant API calls.
        """
        # Check cache first
        cached = self._cache.get(model, record_id)
        if cached:
            self._logger.debug(
                "Using cached related record",
                model=model,
                id=record_id
            )
            return cached
        
        # Fetch from Odoo
        if not self._client:
            self._logger.warning(
                "No Odoo client available for fetching related record",
                model=model,
                id=record_id
            )
            return None
        
        try:
            records = self._client.read([record_id], model, fields)
            if records:
                record = records[0]
                self._cache.set(model, record_id, record)
                self._fetch_count += 1
                return record
        except Exception as e:
            self._logger.error(
                "Failed to fetch related record",
                model=model,
                id=record_id,
                error=str(e)
            )
        
        return None
    
    def fetch_related_records_batch(
        self,
        model: str,
        record_ids: list[int],
        fields: list[str]
    ) -> list[dict]:
        """
        Fetch multiple related records in a single batch.
        
        This is more efficient than fetching one at a time when
        resolving paths for multiple records.
        
        Args:
            model: The Odoo model to fetch from
            record_ids: List of record IDs to fetch
            fields: Fields to include in the response
            
        Returns:
            List of record dictionaries
        """
        if not record_ids:
            return []
        
        # Filter out IDs we already have cached
        uncached_ids = [
            rid for rid in record_ids 
            if not self._cache.get(model, rid)
        ]
        
        if not uncached_ids:
            self._logger.debug(
                "All records found in cache",
                model=model,
                count=len(record_ids)
            )
            return [self._cache.get(model, rid) for rid in record_ids]
        
        self._logger.debug(
            "Batch fetching related records",
            model=model,
            total=len(record_ids),
            cached=len(record_ids) - len(uncached_ids),
            fetching=len(uncached_ids)
        )
        
        if not self._client:
            return []
        
        try:
            # Fetch uncached records
            records = self._client.read(uncached_ids, model, fields)
            
            # Cache them
            self._cache.set_batch(model, records)
            self._fetch_count += 1
            
            # Return all records in original order
            result_map = {r['id']: r for r in records}
            return [result_map.get(rid) for rid in record_ids if rid in result_map]
            
        except Exception as e:
            self._logger.error(
                "Batch fetch failed",
                model=model,
                error=str(e)
            )
            return []
    
    def _create_null_result(
        self,
        path: str,
        default: Any,
        required: bool,
        error: Optional[str] = None
    ) -> ResolutionResult:
        """Create a result for when path resolution returns null."""
        if required:
            self._logger.warning(
                "Required field not found",
                path=path,
                error=error
            )
        
        return ResolutionResult(
            value=default,
            success=error is None,
            error=error,
            was_null=True
        )
    
    def clear_cache(self) -> None:
        """Clear the related record cache."""
        self._cache.clear()
        self._logger.debug("Path resolver cache cleared")
    
    @property
    def total_fetches(self) -> int:
        """Total number of fetch operations performed."""
        return self._fetch_count
    
    def reset_stats(self) -> None:
        """Reset fetch statistics."""
        self._fetch_count = 0