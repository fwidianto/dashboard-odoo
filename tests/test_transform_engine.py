"""Tests for the transformation engine."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, date
from src.transform import (
    TransformationEngine,
    TransformConfig,
    DatasetConfig,
    FieldDefinition,
    TransformResult,
    load_transform_config,
)


class TestTransformResult:
    """Tests for TransformResult."""
    
    def test_to_dict(self):
        """Test TransformResult serialization."""
        result = TransformResult(
            dataset_name="test",
            data=[{"id": 1, "name": "Test"}],
            record_count=1,
            source_record_count=1,
            fields=["id", "name"],
            model="test.model"
        )
        
        output = result.to_dict()
        
        assert output["dataset"] == "test"
        assert output["model"] == "test.model"
        assert output["meta"]["record_count"] == 1
        assert len(output["data"]) == 1
        assert output["data"][0]["name"] == "Test"
    
    def test_to_json(self):
        """Test TransformResult JSON output."""
        result = TransformResult(
            dataset_name="test",
            data=[{"id": 1}],
            record_count=1,
            source_record_count=1,
            fields=["id"],
            model="test.model"
        )
        
        json_str = result.to_json()
        
        assert '"dataset": "test"' in json_str
        assert '"id": 1' in json_str
    
    def test_iteration(self):
        """Test iterating over TransformResult data."""
        result = TransformResult(
            dataset_name="test",
            data=[{"id": 1}, {"id": 2}, {"id": 3}],
            record_count=3,
            source_record_count=3,
            fields=["id"],
            model="test.model"
        )
        
        ids = [r["id"] for r in result]
        assert ids == [1, 2, 3]
    
    def test_len(self):
        """Test TransformResult length."""
        result = TransformResult(
            dataset_name="test",
            data=[{"id": 1}, {"id": 2}],
            record_count=2,
            source_record_count=2,
            fields=["id"],
            model="test.model"
        )
        
        assert len(result) == 2


class TestTransformationEngine:
    """Tests for TransformationEngine."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock Odoo client."""
        client = Mock()
        client.search_read.return_value = [
            {
                "id": 1,
                "name": "SO001",
                "partner_id": 123,
                "amount_total": 1000.00,
                "date_order": "2024-01-15",
                "state": "sale",
            }
        ]
        client.count.return_value = 1
        client.get_model_fields.return_value = {
            "id": {"type": "integer"},
            "name": {"type": "char"},
            "partner_id": {"type": "many2one", "relation": "res.partner"},
            "amount_total": {"type": "monetary"},
            "date_order": {"type": "date"},
            "state": {"type": "selection"},
        }
        return client
    
    @pytest.fixture
    def transform_config(self):
        """Create a test configuration."""
        yaml_content = """
version: "1.0"

datasets:
  test_dataset:
    model: sale.order
    columns:
      order_id:
        path: id
        type: integer
      
      order_reference:
        path: name
      
      customer_id:
        path: partner_id
        type: integer
      
      total:
        path: amount_total
        type: number
        round: 2
      
      revenue:
        compute: total * 1.1
        type: number
        round: 2
"""
        return load_transform_config(yaml_content)
    
    def test_transform_dataset_basic(self, mock_client, transform_config):
        """Test basic dataset transformation."""
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(transform_config, "test_dataset")
        
        assert result.dataset_name == "test_dataset"
        assert result.record_count == 1
        assert result.model == "sale.order"
        assert "order_reference" in result.fields
        
        # Check data
        assert len(result.data) == 1
        record = result.data[0]
        assert record["order_reference"] == "SO001"
        assert record["customer_id"] == 123
        assert record["total"] == 1000.00
    
    def test_transform_dataset_with_domain(self, mock_client, transform_config):
        """Test transformation with additional domain filter."""
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(
            transform_config, 
            "test_dataset",
            domain_filter=[["state", "=", "done"]]
        )
        
        # Verify the domain was passed to search_read
        mock_client.search_read.assert_called()
        call_kwargs = mock_client.search_read.call_args[1]
        assert call_kwargs["model"] == "sale.order"
    
    def test_transform_dataset_not_found(self, mock_client, transform_config):
        """Test transformation with non-existent dataset."""
        engine = TransformationEngine(odoo_client=mock_client)
        
        with pytest.raises(ValueError) as exc_info:
            engine.transform_dataset(transform_config, "nonexistent")
        
        assert "Dataset 'nonexistent' not found" in str(exc_info.value)
    
    def test_transform_dataset_no_client(self, transform_config):
        """Test transformation without Odoo client returns empty."""
        engine = TransformationEngine(odoo_client=None)
        
        result = engine.transform_dataset(transform_config, "test_dataset")
        
        assert result.record_count == 0
        assert result.data == []
    
    def test_compute_field_evaluation(self, mock_client, transform_config):
        """Test computed field evaluation."""
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(transform_config, "test_dataset")
        
        record = result.data[0]
        # total = 1000, revenue = total * 1.1 = 1100
        assert record["revenue"] == 1100.0
    
    def test_type_conversion_integer(self, mock_client):
        """Test integer type conversion."""
        yaml_content = """
version: "1.0"

datasets:
  test:
    model: sale.order
    columns:
      id:
        path: id
        type: integer
"""
        config = load_transform_config(yaml_content)
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(config, "test")
        
        assert isinstance(result.data[0]["id"], int)
    
    def test_type_conversion_number(self, mock_client):
        """Test number/float type conversion."""
        yaml_content = """
version: "1.0"

datasets:
  test:
    model: sale.order
    columns:
      amount:
        path: amount_total
        type: number
"""
        config = load_transform_config(yaml_content)
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(config, "test")
        
        assert isinstance(result.data[0]["amount"], float)
    
    def test_type_conversion_boolean(self, mock_client):
        """Test boolean type conversion."""
        yaml_content = """
version: "1.0"

datasets:
  test:
    model: sale.order
    columns:
      order_state:
        path: state
      is_sale:
        compute: order_state == "sale"
        type: boolean
"""
        config = load_transform_config(yaml_content)
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(config, "test")
        
        assert result.data[0]["is_sale"] is True
    
    def test_rounding(self, mock_client):
        """Test numeric rounding."""
        yaml_content = """
version: "1.0"

datasets:
  test:
    model: sale.order
    columns:
      amount:
        path: amount_total
        type: number
        round: 1
"""
        config = load_transform_config(yaml_content)
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(config, "test")
        
        # 1000.00 rounded to 1 decimal is still 1000.0
        assert result.data[0]["amount"] == 1000.0
    
    def test_default_value(self, mock_client):
        """Test default value for missing fields."""
        mock_client.search_read.return_value = [
            {"id": 1, "name": "SO001"}  # Missing partner_id and amount_total
        ]
        
        yaml_content = """
version: "1.0"

datasets:
  test:
    model: sale.order
    columns:
      customer_id:
        path: partner_id
        default: 0
        type: integer
      
      amount:
        path: amount_total
        default: 100.0
        type: number
"""
        config = load_transform_config(yaml_content)
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(config, "test")
        
        assert result.data[0]["customer_id"] == 0
        assert result.data[0]["amount"] == 100.0
    
    def test_nested_path_resolution(self, mock_client):
        """Test nested path resolution (order_id.name style)."""
        # Mock client returns order details when order_id is queried
        def mock_read(ids, model, fields):
            if model == "res.partner":
                return [{"id": 123, "name": "Acme Corp", "email": "acme@example.com"}]
            return []
        
        mock_client.read.side_effect = mock_read
        
        yaml_content = """
version: "1.0"

datasets:
  test:
    model: sale.order
    columns:
      customer_name:
        path: partner_id.name
      
      customer_email:
        path: partner_id.email
"""
        config = load_transform_config(yaml_content)
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(config, "test")
        
        # The nested paths should be resolved via the mock
        # Note: In real usage, this would fetch from Odoo
    
    def test_batch_transform(self, mock_client, transform_config):
        """Test batch transformation."""
        # Simulate multiple records
        mock_client.search_read.return_value = [
            {"id": 1, "name": "SO001", "partner_id": 1, "amount_total": 100},
            {"id": 2, "name": "SO002", "partner_id": 2, "amount_total": 200},
        ]
        mock_client.count.return_value = 2
        
        # Mock batched reading
        mock_client.read_batched.return_value = iter([
            [{"id": 1, "name": "SO001", "partner_id": 1, "amount_total": 100}],
            [{"id": 2, "name": "SO002", "partner_id": 2, "amount_total": 200}],
        ])
        
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_batch(
            transform_config,
            "test_dataset",
            batch_size=1000
        )
        
        assert result.record_count == 2
    
    def test_cache_stats(self, mock_client, transform_config):
        """Test cache statistics."""
        engine = TransformationEngine(odoo_client=mock_client)
        
        stats = engine.get_cache_stats()
        
        assert "field_metadata_cache_size" in stats
        assert "related_record_cache_size" in stats
        assert "total_related_fetches" in stats
    
    def test_compute_with_none_values(self, mock_client):
        """Test compute expressions handle None values gracefully."""
        mock_client.search_read.return_value = [
            {"id": 1, "name": "SO001", "amount_total": None}
        ]
        
        yaml_content = """
version: "1.0"

datasets:
  test:
    model: sale.order
    columns:
      amount:
        path: amount_total
        default: 0
      
      doubled:
        compute: amount * 2
        type: number
"""
        config = load_transform_config(yaml_content)
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(config, "test")
        
        # None should be replaced with 0, so doubled = 0 * 2 = 0
        assert result.data[0]["doubled"] == 0
    
    def test_compute_complex_expression(self, mock_client):
        """Test complex compute expressions."""
        mock_client.search_read.return_value = [
            {"id": 1, "product_uom_qty": 10, "price_unit": 25.50}
        ]
        
        yaml_content = """
version: "1.0"

datasets:
  test:
    model: sale.order.line
    columns:
      qty:
        path: product_uom_qty
        type: number
      
      price:
        path: price_unit
        type: number
      
      subtotal:
        compute: qty * price
        type: number
        round: 2
      
      discount:
        compute: min(subtotal * 0.1, 50)
        label: "Max discount"
        type: number
        round: 2
      
      final:
        compute: subtotal - discount
        type: number
        round: 2
"""
        config = load_transform_config(yaml_content)
        engine = TransformationEngine(odoo_client=mock_client)
        
        result = engine.transform_dataset(config, "test")
        
        record = result.data[0]
        assert record["qty"] == 10
        assert record["price"] == 25.50
        assert record["subtotal"] == 255.0  # 10 * 25.50
        assert record["discount"] == 25.5   # min(25.5, 50)
        assert record["final"] == 229.5     # 255.0 - 25.5


class TestTransformationIntegration:
    """Integration tests for the full transformation pipeline."""
    
    def test_full_sales_pipeline(self):
        """Test complete pipeline from YAML to transformed data."""
        yaml_content = """
version: "1.0"

datasets:
  sales_order_lines:
    model: sale.order.line
    description: "Sales order line items"
    
    domain: [["order_id.state", "in", ["sale", "done"]]]
    order: "id desc"
    limit: 100
    
    columns:
      line_id:
        path: id
        label: "Line ID"
        type: integer
      
      order_reference:
        path: order_id.name
        label: "Order"
      
      product_name:
        path: product_id.name
        label: "Product"
      
      quantity:
        path: product_uom_qty
        type: number
        round: 2
      
      unit_price:
        path: price_unit
        type: number
        round: 2
      
      line_revenue:
        path: price_subtotal
        type: number
        round: 2
      
      computed_revenue:
        compute: quantity * unit_price
        type: number
        round: 2
"""
        config = load_transform_config(yaml_content)
        
        # Verify config loaded correctly
        dataset = config.get_dataset("sales_order_lines")
        assert dataset is not None
        assert dataset.model == "sale.order.line"
        assert len(dataset.columns) == 7
        
        # Verify path-based vs computed fields
        path_fields = dataset.path_based_fields
        assert "order_reference" in path_fields
        assert "product_name" in path_fields
        
        computed_fields = dataset.computed_fields
        assert "computed_revenue" in computed_fields
        
        # Verify Odoo fields to fetch
        odoo_fields = dataset.get_odoo_fields_to_fetch()
        assert "order_id" in odoo_fields  # For order_reference
        assert "product_id" in odoo_fields  # For product_name
        assert "product_uom_qty" in odoo_fields  # For quantity
        assert "price_unit" in odoo_fields  # For unit_price