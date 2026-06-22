"""Tests for the path resolver module."""

import pytest
from unittest.mock import Mock, MagicMock
from src.transform.path_resolver import (
    PathResolver,
    RelatedRecordCache,
    ResolutionResult,
)


class TestRelatedRecordCache:
    """Tests for RelatedRecordCache."""
    
    def test_cache_operations(self):
        """Test basic cache get/set operations."""
        cache = RelatedRecordCache()
        
        # Set a record
        record = {"id": 123, "name": "Test Order"}
        cache.set("sale.order", 123, record)
        
        # Get it back
        result = cache.get("sale.order", 123)
        assert result == record
    
    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = RelatedRecordCache()
        result = cache.get("sale.order", 999)
        assert result is None
    
    def test_cache_batch(self):
        """Test batch caching."""
        cache = RelatedRecordCache()
        records = [
            {"id": 1, "name": "Order 1"},
            {"id": 2, "name": "Order 2"},
            {"id": 3, "name": "Order 3"},
        ]
        cache.set_batch("sale.order", records)
        
        assert cache.size == 3
        assert cache.get("sale.order", 1) == {"id": 1, "name": "Order 1"}
        assert cache.get("sale.order", 2) == {"id": 2, "name": "Order 2"}
    
    def test_cache_clear(self):
        """Test cache clearing."""
        cache = RelatedRecordCache()
        cache.set("sale.order", 1, {"id": 1})
        cache.set("purchase.order", 1, {"id": 1})
        
        assert cache.size == 2
        
        cache.clear()
        assert cache.size == 0
    
    def test_cache_stats(self):
        """Test cache statistics."""
        cache = RelatedRecordCache()
        cache.set("sale.order", 1, {"id": 1})
        cache.set("sale.order", 2, {"id": 2})
        cache.set("purchase.order", 1, {"id": 1})
        
        stats = cache.stats()
        assert stats["sale.order"] == 2
        assert stats["purchase.order"] == 1


class TestResolutionResult:
    """Tests for ResolutionResult."""
    
    def test_successful_resolution(self):
        """Test successful resolution result."""
        result = ResolutionResult(
            value="Test Value",
            success=True,
            was_null=False
        )
        
        assert result.value == "Test Value"
        assert result.success is True
        assert result.was_null is False
        assert result.error is None
    
    def test_null_resolution(self):
        """Test null resolution result."""
        result = ResolutionResult(
            value=None,
            success=True,
            was_null=True
        )
        
        assert result.value is None
        assert result.success is True
        assert result.was_null is True
    
    def test_failed_resolution(self):
        """Test failed resolution result."""
        result = ResolutionResult(
            value="default",
            success=False,
            error="Path not found",
            was_null=True
        )
        
        assert result.value == "default"
        assert result.success is False
        assert result.error == "Path not found"
        assert result.was_null is True


class TestPathResolver:
    """Tests for PathResolver."""
    
    def test_resolve_simple_field(self):
        """Test resolving a simple (non-nested) field."""
        resolver = PathResolver()
        record = {"id": 1, "name": "Test", "amount": 100.50}
        
        result = resolver.resolve(record, "name")
        
        assert result.success is True
        assert result.value == "Test"
    
    def test_resolve_nested_path_without_client(self):
        """Test resolving nested path without Odoo client returns None."""
        resolver = PathResolver(odoo_client=None)
        record = {"order_id": 123, "product_uom_qty": 5}
        
        result = resolver.resolve(record, "order_id.name")
        
        # Without client, nested paths return None
        assert result.value is None
        assert result.was_null is True
    
    def test_resolve_with_related_record(self):
        """Test resolving path with actual related record."""
        # Create mock Odoo client
        mock_client = Mock()
        mock_client.read.return_value = [
            {"id": 123, "name": "SO001", "partner_id": 456}
        ]
        
        resolver = PathResolver(odoo_client=mock_client)
        
        # Field metadata
        field_metadata = {
            "order_id": {"type": "many2one", "relation": "sale.order"},
        }
        
        record = {"order_id": 123, "product_uom_qty": 5}
        
        result = resolver.resolve_with_related(
            record,
            "order_id.name",
            field_metadata,
            "sale.order.line"
        )
        
        assert result.success is True
        assert result.value == "SO001"
    
    def test_resolve_empty_path(self):
        """Test resolving empty path returns error."""
        resolver = PathResolver()
        record = {"id": 1}
        
        result = resolver.resolve(record, "")
        
        assert result.success is False
        assert result.error == "Empty path provided"
    
    def test_resolve_nonexistent_field(self):
        """Test resolving non-existent field."""
        resolver = PathResolver()
        record = {"id": 1, "name": "Test"}
        
        result = resolver.resolve(record, "nonexistent")
        
        assert result.value is None
        assert result.was_null is True
    
    def test_resolve_with_default(self):
        """Test resolving with default value."""
        resolver = PathResolver()
        record = {"id": 1}
        
        result = resolver.resolve(record, "missing", default="default_value")
        
        assert result.value == "default_value"
        assert result.was_null is True
    
    def test_resolve_required_field_missing(self):
        """Test resolving required field that is missing."""
        resolver = PathResolver()
        record = {"id": 1}
        
        result = resolver.resolve(
            record, 
            "missing", 
            required=True
        )
        
        assert result.value is None
        assert result.was_null is True
    
    def test_resolve_integer_id(self):
        """Test that raw integer IDs are returned as-is."""
        resolver = PathResolver()
        record = {"order_id": 12345, "product_uom_qty": 5}
        
        result = resolver.resolve(record, "order_id")
        
        assert result.success is True
        assert result.value == 12345
        assert isinstance(result.value, int)
    
    def test_resolve_already_expanded_record(self):
        """Test resolving when related record is already expanded."""
        resolver = PathResolver()
        record = {
            "order_id": {"id": 123, "name": "SO001", "partner_id": {"id": 456, "name": "Acme"}},
            "product_uom_qty": 5
        }
        
        # First level - should get the dict
        result = resolver.resolve(record, "order_id")
        assert result.value == {"id": 123, "name": "SO001", "partner_id": {"id": 456, "name": "Acme"}}
        
        # Second level - should get the name
        result = resolver.resolve(record, "order_id.name")
        assert result.value == "SO001"
        
        # Third level - should get partner name
        result = resolver.resolve(record, "order_id.partner_id.name")
        assert result.value == "Acme"
    
    def test_cache_usage(self):
        """Test that cache is used for subsequent resolutions."""
        mock_client = Mock()
        # Only return once - subsequent calls should use cache
        mock_client.read.return_value = [{"id": 123, "name": "SO001"}]
        
        resolver = PathResolver(odoo_client=mock_client)
        field_metadata = {"order_id": {"type": "many2one", "relation": "sale.order"}}
        
        record1 = {"order_id": 123, "product_uom_qty": 5}
        record2 = {"order_id": 123, "product_uom_qty": 10}
        
        # First resolution - should fetch
        resolver.resolve_with_related(record1, "order_id.name", field_metadata, "sale.order.line")
        
        # Second resolution - should use cache
        resolver.resolve_with_related(record2, "order_id.name", field_metadata, "sale.order.line")
        
        # Should only have called read once
        assert mock_client.read.call_count == 1
    
    def test_batch_fetch_related_records(self):
        """Test batch fetching of related records."""
        mock_client = Mock()
        mock_client.read.return_value = [
            {"id": 1, "name": "Order 1"},
            {"id": 2, "name": "Order 2"},
        ]
        
        resolver = PathResolver(odoo_client=mock_client)
        
        records = resolver.fetch_related_records_batch(
            "sale.order",
            [1, 2],
            ["name"]
        )
        
        assert len(records) == 2
        assert records[0]["name"] == "Order 1"
        assert records[1]["name"] == "Order 2"
    
    def test_clear_cache(self):
        """Test clearing the cache."""
        mock_client = Mock()
        mock_client.read.return_value = [{"id": 123, "name": "SO001"}]
        
        resolver = PathResolver(odoo_client=mock_client)
        field_metadata = {"order_id": {"type": "many2one", "relation": "sale.order"}}
        
        record = {"order_id": 123, "product_uom_qty": 5}
        resolver.resolve_with_related(record, "order_id.name", field_metadata, "sale.order.line")
        
        assert resolver.cache.size == 1
        
        resolver.clear_cache()
        assert resolver.cache.size == 0
    
    def test_total_fetches_counter(self):
        """Test that total fetches counter works."""
        mock_client = Mock()
        mock_client.read.return_value = [{"id": 123, "name": "SO001"}]
        
        resolver = PathResolver(odoo_client=mock_client)
        
        assert resolver.total_fetches == 0
        
        resolver.fetch_related_records_batch("sale.order", [123], ["name"])
        assert resolver.total_fetches == 1
        
        resolver.fetch_related_records_batch("sale.order", [124], ["name"])
        assert resolver.total_fetches == 2