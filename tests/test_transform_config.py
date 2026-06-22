"""Tests for the transformation engine configuration models."""

import pytest
from pydantic import ValidationError
from src.transform.config import (
    FieldDefinition,
    DatasetConfig,
    TransformConfig,
    load_transform_config,
)


class TestFieldDefinition:
    """Tests for FieldDefinition model."""
    
    def test_path_based_field(self):
        """Test creating a path-based field definition."""
        field = FieldDefinition(
            path="order_id.name",
            label="Order Reference"
        )
        
        assert field.path == "order_id.name"
        assert field.label == "Order Reference"
        assert field.is_path_based
        assert not field.is_computed
    
    def test_computed_field(self):
        """Test creating a computed field definition."""
        field = FieldDefinition(
            compute="quantity * price_unit",
            label="Total"
        )
        
        assert field.compute == "quantity * price_unit"
        assert field.is_computed
        assert not field.is_path_based
    
    def test_field_with_options(self):
        """Test field with all options."""
        field = FieldDefinition(
            path="amount",
            label="Amount",
            type="number",
            round=2,
            default=0,
            required=True,
            format="%Y-%m-%d"
        )
        
        assert field.type == "number"
        assert field.round == 2
        assert field.default == 0
        assert field.required is True
        assert field.format == "%Y-%m-%d"
    
    def test_both_path_and_compute_raises(self):
        """Test that specifying both path and compute raises error."""
        with pytest.raises(ValidationError) as exc_info:
            FieldDefinition(
                path="order_id.name",
                compute="quantity * price"
            )
        
        assert "cannot have both 'path' and 'compute'" in str(exc_info.value)
    
    def test_neither_path_nor_compute_raises(self):
        """Test that specifying neither path nor compute raises error."""
        with pytest.raises(ValidationError) as exc_info:
            FieldDefinition(
                label="Test Field"
            )
        
        assert "must specify either 'path' or 'compute'" in str(exc_info.value)
    
    def test_get_odoo_fields_path(self):
        """Test getting Odoo fields from path definition."""
        field = FieldDefinition(path="order_id.name")
        fields = field.get_odoo_fields()
        
        assert "order_id.name" in fields
    
    def test_get_odoo_fields_compute(self):
        """Test getting Odoo fields from compute expression."""
        field = FieldDefinition(
            compute="quantity * price_unit + discount"
        )
        fields = field.get_odoo_fields()
        
        # Should include field names, excluding Python keywords
        assert "quantity" in fields
        assert "price_unit" in fields
        assert "discount" in fields


class TestDatasetConfig:
    """Tests for DatasetConfig model."""
    
    def test_basic_dataset(self):
        """Test creating a basic dataset configuration."""
        config = DatasetConfig(
            name="sales_lines",
            model="sale.order.line",
            columns={
                "order_ref": FieldDefinition(path="order_id.name"),
                "product": FieldDefinition(path="product_id.name"),
                "qty": FieldDefinition(path="product_uom_qty"),
            }
        )
        
        assert config.name == "sales_lines"
        assert config.model == "sale.order.line"
        assert len(config.columns) == 3
    
    def test_dataset_properties(self):
        """Test dataset computed properties."""
        config = DatasetConfig(
            name="test",
            model="test.model",
            columns={
                "field1": FieldDefinition(path="field1"),
                "field2": FieldDefinition(path="field2.name"),
                "computed": FieldDefinition(compute="field1 * 2"),
            }
        )
        
        assert set(config.column_names) == {"field1", "field2", "computed"}
        assert set(config.path_based_fields) == {"field1", "field2"}
        assert config.computed_fields == ["computed"]
    
    def test_get_odoo_fields_to_fetch(self):
        """Test getting list of Odoo fields to fetch."""
        config = DatasetConfig(
            name="test",
            model="test.model",
            columns={
                "order_ref": FieldDefinition(path="order_id.name"),
                "product_name": FieldDefinition(path="product_id.name"),
                "total": FieldDefinition(compute="qty * price"),
            }
        )
        
        fields = config.get_odoo_fields_to_fetch()
        
        # Should include base fields from paths
        assert "order_id" in fields
        assert "product_id" in fields
        # Should include fields from compute expression
        assert "qty" in fields
        assert "price" in fields
    
    def test_domain_and_order(self):
        """Test domain and order settings."""
        config = DatasetConfig(
            name="test",
            model="test.model",
            domain=[["state", "=", "sale"]],
            order="date_order desc",
            limit=100,
            active_only=True
        )
        
        assert config.domain == [["state", "=", "sale"]]
        assert config.order == "date_order desc"
        assert config.limit == 100
        assert config.active_only is True


class TestTransformConfig:
    """Tests for TransformConfig model."""
    
    def test_empty_config(self):
        """Test creating empty configuration."""
        config = TransformConfig()
        
        assert config.datasets == {}
        assert config.get_dataset("nonexistent") is None
    
    def test_multiple_datasets(self):
        """Test configuration with multiple datasets."""
        config = TransformConfig(
            datasets={
                "sales": DatasetConfig(
                    name="sales",
                    model="sale.order"
                ),
                "purchases": DatasetConfig(
                    name="purchases",
                    model="purchase.order"
                ),
            }
        )
        
        assert len(config.datasets) == 2
        assert config.get_dataset("sales") is not None
        assert config.get_dataset("purchases") is not None
        assert "sales" in config.dataset_names()


class TestLoadTransformConfig:
    """Tests for YAML loading functionality."""
    
    def test_load_simple_config(self):
        """Test loading a simple YAML configuration."""
        yaml_content = """
version: "1.0"

datasets:
  test_dataset:
    model: test.model
    columns:
      field1:
        path: field1
      field2:
        path: field2.name
"""
        config = load_transform_config(yaml_content)
        
        assert config.version == "1.0"
        assert "test_dataset" in config.datasets
        dataset = config.get_dataset("test_dataset")
        assert dataset.model == "test.model"
        assert "field1" in dataset.columns
    
    def test_load_wrapped_config(self):
        """Test loading a YAML configuration with 'config' wrapper."""
        yaml_content = """
config:
  version: "2.0"

datasets:
  wrapped_dataset:
    model: wrapped.model
    columns:
      col1:
        path: col1
"""
        config = load_transform_config(yaml_content)
        
        assert config.version == "2.0"
        assert "wrapped_dataset" in config.datasets
    
    def test_load_full_example(self):
        """Test loading a complete dataset configuration."""
        yaml_content = """
version: "1.0"

datasets:
  sales_order_lines:
    model: sale.order.line
    description: "Test dataset"
    domain: [["state", "=", "sale"]]
    order: "date_order desc"
    limit: 100
    
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
        round: 2
      
      revenue:
        compute: quantity * price_unit
        type: number
        round: 2
"""
        config = load_transform_config(yaml_content)
        
        dataset = config.get_dataset("sales_order_lines")
        assert dataset is not None
        assert dataset.model == "sale.order.line"
        assert dataset.description == "Test dataset"
        assert dataset.domain == [["state", "=", "sale"]]
        assert dataset.order == "date_order desc"
        assert dataset.limit == 100
        
        # Check columns
        assert "order_reference" in dataset.columns
        assert "product_name" in dataset.columns
        assert "quantity" in dataset.columns
        assert "revenue" in dataset.columns
        
        # Check column properties
        order_col = dataset.columns["order_reference"]
        assert order_col.path == "order_id.name"
        assert order_col.label == "Order Reference"
        
        revenue_col = dataset.columns["revenue"]
        assert revenue_col.compute == "quantity * price_unit"
        assert revenue_col.type == "number"
        assert revenue_col.round == 2