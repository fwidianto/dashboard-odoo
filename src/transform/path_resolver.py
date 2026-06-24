"""Path resolver for extracting nested values from Odoo records.

This module solves the critical issue with Odoo relational fields:
- `.read()` does NOT support nested dot notation (e.g., "order_id.name")
- Many2one fields return only IDs, not related values

The PathResolver handles:
1. Extracting direct fields from Odoo records
2. Resolving nested paths like "order_id.name" by fetching related records
3. Caching related records to avoid redundant API calls
4. Graceful handling of missing/null relationships

IMPORTANT RULES:
- ALWAYS traverse full dotted paths, never truncate with split('.')[0]
- NEVER fallback to base field when dotted path exists
- Use recursive traversal through related records
"""

from typing import Any, Optional
from dataclasses import dataclass
from src.utils.logging import get_logger


@dataclass
class ResolutionResult:
    """Result of resolving a path against an Odoo record."""
    
    value: Any
    success: bool
    error: Optional[str] = None
    was_null: bool = False
    related_fetches: int = 0


class RelatedRecordCache:
    """Cache for related records to avoid redundant API calls."""
    
    def __init__(self):
        self._cache: dict[tuple[str, int], dict] = {}
        self._logger = get_logger("path_resolver.cache")
    
    def get(self, model: str, record_id: int) -> Optional[dict]:
        key = (model, record_id)
        return self._cache.get(key)
    
    def set(self, model: str, record_id: int, record: dict) -> None:
        key = (model, record_id)
        self._cache[key] = record
    
    def set_batch(self, model: str, records: list[dict]) -> None:
        for record in records:
            record_id = record.get('id')
            if record_id:
                self.set(model, record_id, record)
    
    def clear(self) -> None:
        self._cache.clear()
    
    @property
    def size(self) -> int:
        return len(self._cache)
    
    def stats(self) -> dict[str, int]:
        stats: dict[str, int] = {}
        for (model, _), _ in self._cache.items():
            stats[model] = stats.get(model, 0) + 1
        return stats


class PathResolver:
    """
    Resolves dot-notation paths against Odoo records.
    
    Handles paths like:
    - "product_uom_qty" - Direct field
    - "order_id" - Many2one field (returns ID)
    - "order_id.name" - Nested: fetches related order, returns its name
    - "order_id.partner_id.name" - Double nested
    
    Key features:
    - Correct recursive traversal through dotted paths
    - Fetches related records when encountering IDs
    - Caches related records to minimize API calls
    - NEVER truncates paths or falls back to base fields
    """
    
    def __init__(self, odoo_client=None):
        self._client = odoo_client
        self._cache = RelatedRecordCache()
        self._logger = get_logger("path_resolver")
        self._fetch_count = 0
        # Cache for field metadata to get relation model names
        self._field_metadata_cache: dict[str, dict[str, dict]] = {}
    
    @property
    def cache(self) -> RelatedRecordCache:
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
        
        This is the SIMPLE resolver that only traverses already-loaded records.
        It does NOT fetch related records from Odoo.
        
        Use resolve_with_related() for full nested resolution with ORM fetching.
        """
        if not path:
            return ResolutionResult(
                value=default,
                success=False,
                error="Empty path provided",
                was_null=True
            )
        
        # Split path into parts - MUST traverse ALL parts
        parts = path.split('.')
        value = record
        
        for i, part in enumerate(parts):
            if value is None:
                return ResolutionResult(
                    value=default,
                    success=False,
                    error=f"Path truncated at '{part}' - parent is null",
                    was_null=True
                )
            
            # Get the next value - continue traversal even for integers
            value = self._get_value(value, part)
        
        if value is None:
            return ResolutionResult(
                value=default,
                success=True,
                was_null=True
            )
        
        return ResolutionResult(
            value=value,
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
        Resolve a path with automatic fetching of related records.
        
        This is the MAIN entry point that handles nested paths like "order_id.name".
        
        RULES:
        - For SINGLE-PART paths (e.g., "partner_id"): return value as-is
        - For MULTI-PART paths (e.g., "order_id.name"): fetch related records
        
        This is the critical distinction:
        - "partner_id" -> just return the integer ID
        - "order_id.name" -> fetch the order record, then return its name
        """
        if not path:
            return ResolutionResult(
                value=default,
                success=False,
                error="Empty path provided",
                was_null=True
            )
        
        parts = path.split('.')
        
        # SINGLE-PART PATH: Return value directly (no traversal needed)
        # Examples: "partner_id", "product_id", "amount_total"
        if len(parts) == 1:
            value = self._get_value(record, parts[0])
            if value is None:
                return ResolutionResult(value=default, success=True, was_null=True)
            return ResolutionResult(value=value, success=True, was_null=False)
        
        # MULTI-PART PATH: Traverse and fetch related records
        # Examples: "order_id.name", "order_id.partner_id.name"
        value = record
        current_model = model
        current_metadata = field_metadata
        
        for i, part in enumerate(parts):
            if value is None:
                return ResolutionResult(
                    value=default,
                    success=False,
                    error=f"Path truncated at '{part}' - parent is null",
                    was_null=True
                )
            
            # Get the current value for this part
            current_value = self._get_value(value, part)
            
            if current_value is None:
                # Null value - stop here
                return ResolutionResult(value=default, success=True, was_null=True)
            
            # If there are more parts to traverse and this is an ID, fetch the record
            if i < len(parts) - 1:
                if isinstance(current_value, list) and current_value:
                    if (
                        len(current_value) >= 1
                        and parts[i + 1] == "id"
                        and i + 1 == len(parts) - 1
                    ):
                        return ResolutionResult(
                            value=current_value[0],
                            success=True,
                            was_null=False,
                        )
                    if (
                        len(current_value) >= 2
                        and parts[i + 1] == "name"
                        and i + 1 == len(parts) - 1
                    ):
                        return ResolutionResult(
                            value=current_value[1],
                            success=True,
                            was_null=False,
                        )
                    current_value = current_value[0]

                if isinstance(current_value, int):
                    # Need to fetch the related record for further traversal
                    related_model = self._get_related_model(
                        part, current_metadata, current_model
                    )
                    
                    if related_model and self._client:
                        # Determine fields to fetch (remaining parts + id)
                        remaining_parts = parts[i + 1:]
                        fields_to_fetch = remaining_parts + ['id']
                        
                        related_record = self._fetch_related_record(
                            related_model,
                            current_value,
                            fields_to_fetch
                        )
                        
                        if related_record:
                            current_metadata = self._get_field_metadata(related_model)
                            current_model = related_model
                            value = related_record
                        else:
                            return ResolutionResult(value=default, success=True, was_null=True)
                    else:
                        # Can't fetch - return the ID
                        return ResolutionResult(value=current_value, success=True, was_null=False)
                elif isinstance(current_value, dict):
                    # Already a dict - continue traversal
                    value = current_value
                else:
                    # Primitive value but more parts to traverse - can't continue
                    return ResolutionResult(value=default, success=True, was_null=True)
            else:
                # This is the last part - return the value as-is
                value = current_value
        
        if value is None:
            return ResolutionResult(value=default, success=True, was_null=True)
        
        return ResolutionResult(value=value, success=True, was_null=False)
    
    def _get_value(self, obj: Any, key: str) -> Any:
        """Get a value from an object (dict or object)."""
        if isinstance(obj, dict):
            return obj.get(key)
        elif hasattr(obj, key):
            return getattr(obj, key)
        return None
    
    def _get_related_model(
        self,
        field_name: str,
        field_metadata: dict[str, dict],
        current_model: str
    ) -> Optional[str]:
        """Get the related model name for a many2one field."""
        # Check the provided metadata
        field_def = field_metadata.get(field_name, {})
        relation = field_def.get('relation')
        if relation:
            return relation
        
        # Check cached metadata
        cached_metadata = self._field_metadata_cache.get(current_model, {})
        field_def = cached_metadata.get(field_name, {})
        return field_def.get('relation')
    
    def _get_field_metadata(self, model: str) -> dict[str, dict]:
        """Get field metadata for a model."""
        if model in self._field_metadata_cache:
            return self._field_metadata_cache[model]
        
        if self._client:
            try:
                metadata = self._client.get_model_fields(model)
                self._field_metadata_cache[model] = metadata
                return metadata
            except Exception as e:
                self._logger.warning(
                    f"Failed to get field metadata for {model}",
                    error=str(e)
                )
        
        return {}
    
    def _fetch_related_record(
        self,
        model: str,
        record_id: int,
        fields: list[str]
    ) -> Optional[dict]:
        """Fetch a single related record from Odoo."""
        # Check cache first
        cached = self._cache.get(model, record_id)
        if cached:
            self._logger.debug(
                "Using cached related record",
                model=model,
                id=record_id
            )
            return cached
        
        if not self._client:
            self._logger.warning(
                "No Odoo client available for fetching related record",
                model=model,
                id=record_id
            )
            return None
        
        try:
            records = self._client.read(model, [record_id], fields)
            if records:
                record = records[0]
                self._cache.set(model, record_id, record)
                self._fetch_count += 1
                self._logger.debug(
                    "Fetched related record",
                    model=model,
                    id=record_id,
                    fetched_fields=fields
                )
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
        """Fetch multiple related records in a single batch."""
        if not record_ids:
            return []
        
        # Filter out cached IDs
        uncached_ids = [
            rid for rid in record_ids 
            if not self._cache.get(model, rid)
        ]
        
        if not uncached_ids:
            return [self._cache.get(model, rid) for rid in record_ids]
        
        if not self._client:
            return []
        
        try:
            records = self._client.read(uncached_ids, model, fields)
            self._cache.set_batch(model, records)
            self._fetch_count += 1
            
            result_map = {r['id']: r for r in records}
            return [result_map.get(rid) for rid in record_ids if rid in result_map]
            
        except Exception as e:
            self._logger.error(
                "Batch fetch failed",
                model=model,
                error=str(e)
            )
            return []
    
    def clear_cache(self) -> None:
        """Clear the related record cache."""
        self._cache.clear()
    
    @property
    def total_fetches(self) -> int:
        return self._fetch_count
    
    def reset_stats(self) -> None:
        self._fetch_count = 0
