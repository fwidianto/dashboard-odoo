"""Tests for the metadata discovery module."""

import pytest
import json
import tempfile
import os

from src.odoo.metadata_discovery import (
    OdooField,
    OdooModelMetadata,
    SchemaCache,
    OdooMetadataDiscovery,
    generate_field_configs,
)


class TestOdooField:
    """Tests for OdooField dataclass."""
    
    def test_create_field(self):
        """Test creating an OdooField."""
        field = OdooField(
            name="list_price",
            field_type="monetary",
            string="Sale Price",
            required=False,
            store=True,
            index=False,
            relation="product.pricelist",
        )
        
        assert field.name == "list_price"
        assert field.field_type == "monetary"
        assert field.required is False
        assert field.store is True
        assert field.relation == "product.pricelist"
    
    def test_to_dict(self):
        """Test converting field to dictionary."""
        field = OdooField(
            name="name",
            field_type="char",
            string="Name",
            required=True,
            store=True,
            index=True,
        )
        
        data = field.to_dict()
        
        assert data["name"] == "name"
        assert data["field_type"] == "char"
        assert data["required"] is True
        assert data["index"] is True


class TestOdooModelMetadata:
    """Tests for OdooModelMetadata dataclass."""
    
    def test_create_metadata(self):
        """Test creating model metadata."""
        metadata = OdooModelMetadata(
            model="product.template",
            table="product_template",
        )
        
        assert metadata.model == "product.template"
        assert metadata.table == "product_template"
        assert len(metadata.fields) == 0
    
    def test_get_stored_fields(self):
        """Test getting only stored fields."""
        metadata = OdooModelMetadata(model="test.model", table="test_model")
        
        # Add stored and non-stored fields
        metadata.fields["name"] = OdooField(
            name="name",
            field_type="char",
            string="Name",
            store=True,
        )
        metadata.fields["computed"] = OdooField(
            name="computed",
            field_type="char",
            string="Computed",
            store=False,
        )
        
        stored = metadata.get_stored_fields()
        assert len(stored) == 1
        assert "name" in stored
        assert "computed" not in stored
    
    def test_compute_hash(self):
        """Test computing metadata hash."""
        metadata = OdooModelMetadata(model="test.model", table="test_model")
        metadata.fields["name"] = OdooField(
            name="name",
            field_type="char",
            string="Name",
            store=True,
        )
        
        hash1 = metadata.compute_hash()
        hash2 = metadata.compute_hash()
        
        assert hash1 == hash2
        assert len(hash1) == 16


class TestSchemaCache:
    """Tests for SchemaCache."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            delete=False,
        )
        self.temp_path = self.temp_file.name
        self.temp_file.close()
    
    def teardown_method(self):
        """Clean up temp files."""
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)
    
    def test_load_missing_file(self):
        """Test loading from non-existent file."""
        cache = SchemaCache(cache_file="/nonexistent/file.json")
        assert cache.load() is False
    
    def test_save_and_load(self):
        """Test saving and loading cache."""
        cache = SchemaCache(cache_file=self.temp_path)
        
        metadata = OdooModelMetadata(model="test.model", table="test_model")
        metadata.fields["name"] = OdooField(
            name="name",
            field_type="char",
            string="Name",
            store=True,
        )
        metadata.metadata_hash = metadata.compute_hash()
        
        cache.set("test.model", metadata)
        cache.save()
        
        # Load in new instance
        cache2 = SchemaCache(cache_file=self.temp_path)
        assert cache2.load() is True
        entry = cache2.get("test.model")
        assert entry["model"] == "test.model"
        assert entry["table"] == "test_model"
    
    def test_needs_update(self):
        """Test checking if update is needed."""
        cache = SchemaCache(cache_file=self.temp_path)
        
        # No entry
        assert cache.needs_update("test.model", "abc123") is True
        
        # Add entry
        metadata = OdooModelMetadata(model="test.model", table="test_model")
        metadata.metadata_hash = "abc123"
        cache.set("test.model", metadata)
        
        # Same hash
        assert cache.needs_update("test.model", "abc123") is False
        
        # Different hash
        assert cache.needs_update("test.model", "xyz789") is True


class TestOdooMetadataDiscovery:
    """Tests for OdooMetadataDiscovery."""
    
    def test_type_mapping(self):
        """Test type mapping."""
        discovery = OdooMetadataDiscovery(odoo_client=None)
        
        # Numeric types -> NUMERIC(30,10)
        assert discovery.get_postgres_type("float") == "NUMERIC(30,10)"
        assert discovery.get_postgres_type("monetary") == "NUMERIC(30,10)"
        
        # Text types -> TEXT
        assert discovery.get_postgres_type("char") == "TEXT"
        assert discovery.get_postgres_type("text") == "TEXT"
        assert discovery.get_postgres_type("html") == "TEXT"
        assert discovery.get_postgres_type("selection") == "TEXT"
        
        # Integer types -> BIGINT
        assert discovery.get_postgres_type("integer") == "BIGINT"
        assert discovery.get_postgres_type("bigint") == "BIGINT"
        
        # Relational types
        assert discovery.get_postgres_type("many2one") == "BIGINT"
        assert discovery.get_postgres_type("one2many") == "JSONB"
        assert discovery.get_postgres_type("many2many") == "JSONB"
    
    def test_is_relational_type(self):
        """Test relational type detection."""
        discovery = OdooMetadataDiscovery(odoo_client=None)
        
        assert discovery.is_relational_type("one2many") is True
        assert discovery.is_relational_type("many2many") is True
        assert discovery.is_relational_type("char") is False
        assert discovery.is_relational_type("integer") is False
    
    def test_model_to_table(self):
        """Test model to table name conversion."""
        discovery = OdooMetadataDiscovery(odoo_client=None)
        
        assert discovery._model_to_table("product.template") == "product_template"
        assert discovery._model_to_table("sale.order.line") == "sale_order_line"
        assert discovery._model_to_table("res.partner") == "res_partner"


class TestGenerateFieldConfigs:
    """Tests for generate_field_configs function."""
    
    def test_basic_field(self):
        """Test generating config for basic field."""
        metadata = OdooModelMetadata(model="test.model", table="test_model")
        metadata.fields["name"] = OdooField(
            name="name",
            field_type="char",
            string="Name",
            required=True,
            store=True,
            index=True,
        )
        
        configs = generate_field_configs(metadata)
        
        assert len(configs) == 1
        assert configs[0]["odoo_field"] == "name"
        assert configs[0]["postgres_type"] == "TEXT"
        assert configs[0]["required"] is True
        assert configs[0]["indexed"] is True
    
    def test_relational_field(self):
        """Test generating config for relational field."""
        metadata = OdooModelMetadata(model="test.model", table="test_model")
        metadata.fields["partner_id"] = OdooField(
            name="partner_id",
            field_type="many2one",
            string="Partner",
            store=True,
            relation="res.partner",
        )
        
        configs = generate_field_configs(metadata)
        
        assert len(configs) == 1
        assert configs[0]["odoo_field"] == "partner_id"
        assert configs[0]["postgres_type"] == "BIGINT"
        assert configs[0]["field_type"] == "many2one"
        assert configs[0]["related_model"] == "res.partner"
    
    def test_numeric_field(self):
        """Test generating config for numeric field."""
        metadata = OdooModelMetadata(model="test.model", table="test_model")
        metadata.fields["amount"] = OdooField(
            name="amount",
            field_type="monetary",
            string="Amount",
            store=True,
        )
        
        configs = generate_field_configs(metadata)
        
        assert len(configs) == 1
        assert configs[0]["postgres_type"] == "NUMERIC(30,10)"
    
    def test_skips_non_stored(self):
        """Test that non-stored fields are skipped."""
        metadata = OdooModelMetadata(model="test.model", table="test_model")
        metadata.fields["stored"] = OdooField(
            name="stored",
            field_type="char",
            string="Stored",
            store=True,
        )
        metadata.fields["computed"] = OdooField(
            name="computed",
            field_type="char",
            string="Computed",
            store=False,
        )
        
        configs = generate_field_configs(metadata)
        
        assert len(configs) == 1
        assert configs[0]["odoo_field"] == "stored"


class TestTypeMappingCompliance:
    """Tests for type mapping compliance with requirements."""
    
    def test_no_varchar_in_mapping(self):
        """Test that no VARCHAR types are used."""
        discovery = OdooMetadataDiscovery(odoo_client=None)
        
        for odoo_type, pg_type in discovery.ODOO_TO_POSTGRES_TYPE.items():
            if odoo_type not in ['one2many', 'many2many']:  # These are SKIP
                assert "VARCHAR" not in pg_type, f"VARCHAR found in {odoo_type} -> {pg_type}"
    
    def test_numeric_uses_30_10(self):
        """Test that numeric types use 30,10 precision."""
        discovery = OdooMetadataDiscovery(odoo_client=None)
        
        assert discovery.get_postgres_type("float") == "NUMERIC(30,10)"
        assert discovery.get_postgres_type("monetary") == "NUMERIC(30,10)"
    
    def test_bigint_for_integers(self):
        """Test that integer types use BIGINT."""
        discovery = OdooMetadataDiscovery(odoo_client=None)
        
        assert discovery.get_postgres_type("integer") == "BIGINT"
        assert discovery.get_postgres_type("bigint") == "BIGINT"
        assert discovery.get_postgres_type("many2one") == "BIGINT"
    
    def test_jsonb_for_relational(self):
        """Test that relational types use JSONB."""
        discovery = OdooMetadataDiscovery(odoo_client=None)
        
        assert discovery.get_postgres_type("one2many") == "JSONB"
        assert discovery.get_postgres_type("many2many") == "JSONB"
