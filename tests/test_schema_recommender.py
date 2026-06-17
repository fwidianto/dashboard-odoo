"""Tests for the schema recommender module."""

import pytest
import os
import tempfile
import shutil

from src.reporting.error_enums import ErrorCategory
from src.reporting.schema_recommender import SchemaRecommender, ColumnRecommendation, ModelRecommendation
from src.reporting.error_reporter import BatchErrorSummary, DataProfile


class TestColumnRecommendation:
    """Tests for ColumnRecommendation dataclass."""
    
    def test_create_column_recommendation(self):
        """Test creating a column recommendation."""
        rec = ColumnRecommendation(
            column_name="name",
            current_type="VARCHAR(255)",
            recommended_type="TEXT",
            reason="712 DATA_TOO_LONG failures",
            estimated_impact=712,
        )
        
        assert rec.column_name == "name"
        assert rec.current_type == "VARCHAR(255)"
        assert rec.recommended_type == "TEXT"
        assert rec.reason == "712 DATA_TOO_LONG failures"
        assert rec.estimated_impact == 712


class TestModelRecommendation:
    """Tests for ModelRecommendation dataclass."""
    
    def test_create_model_recommendation(self):
        """Test creating a model recommendation."""
        rec = ModelRecommendation(
            model_name="product.template",
            table_name="product_template",
        )
        
        assert rec.model_name == "product.template"
        assert rec.table_name == "product_template"
        assert len(rec.column_recommendations) == 0


class TestSchemaRecommender:
    """Tests for SchemaRecommender class."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init_default_dir(self):
        """Test initialization with default directory."""
        recommender = SchemaRecommender()
        assert recommender.reports_dir.name == "schema_recommendations"
    
    def test_init_custom_dir(self):
        """Test initialization with custom directory."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        expected_path = os.path.join(self.temp_dir, "schema_recommendations")
        assert str(recommender.reports_dir) == expected_path
    
    def test_add_batch_summary_data_too_long(self):
        """Test adding batch summary with DATA_TOO_LONG errors."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        # Create batch summary with DATA_TOO_LONG errors
        summary = BatchErrorSummary(model="product.template", table_name="product_template")
        summary.processed = 1000
        summary.success = 300
        summary.failed = 700
        summary.errors_by_category[ErrorCategory.DATA_TOO_LONG] = 700
        summary.errors_by_column["name"] = 500
        summary.errors_by_column["description"] = 200
        
        # Add data profiles
        profile_name = DataProfile(column_name="name", current_type="VARCHAR(255)")
        profile_name.max_length_observed = 834
        summary.data_profiles["name"] = profile_name
        
        recommender.add_batch_summary(summary)
        
        assert "product.template" in recommender._recommendations
        model_rec = recommender._recommendations["product.template"]
        assert model_rec.table_name == "product_template"
        assert len(model_rec.column_recommendations) > 0
    
    def test_add_batch_summary_numeric_overflow(self):
        """Test adding batch summary with NUMERIC_OVERFLOW errors."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        summary = BatchErrorSummary(model="sale.order", table_name="sale_order")
        summary.processed = 100
        summary.success = 80
        summary.failed = 20
        summary.errors_by_category[ErrorCategory.NUMERIC_OVERFLOW] = 20
        summary.errors_by_column["amount_total"] = 20
        
        # Add data profile with max value
        profile = DataProfile(column_name="amount_total", current_type="NUMERIC(12,2)")
        profile.max_value_observed = 17762630700.0
        summary.data_profiles["amount_total"] = profile
        
        recommender.add_batch_summary(summary)
        
        assert "sale.order" in recommender._recommendations
    
    def test_generate_recommendations(self):
        """Test generating recommendations dictionary."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        summary = BatchErrorSummary(model="product.template", table_name="product_template")
        summary.errors_by_category[ErrorCategory.DATA_TOO_LONG] = 100
        summary.errors_by_column["name"] = 100
        
        recommender.add_batch_summary(summary)
        
        recommendations = recommender.generate_recommendations()
        
        assert "product.template" in recommendations
        assert "table" in recommendations["product.template"]
        assert "columns" in recommendations["product.template"]
    
    def test_generate_migration_sql(self):
        """Test generating SQL migration script."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        summary = BatchErrorSummary(model="product.template", table_name="product_template")
        summary.errors_by_category[ErrorCategory.DATA_TOO_LONG] = 100
        summary.errors_by_column["name"] = 100
        
        recommender.add_batch_summary(summary)
        
        sql = recommender.generate_migration_sql()
        
        assert "BEGIN" in sql
        assert "COMMIT" in sql
        assert "product_template" in sql
        assert "ALTER TABLE" in sql
        assert "name" in sql
    
    def test_export(self):
        """Test exporting recommendations to files."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        summary = BatchErrorSummary(model="product.template", table_name="product_template")
        summary.errors_by_category[ErrorCategory.DATA_TOO_LONG] = 100
        summary.errors_by_column["name"] = 100
        
        recommender.add_batch_summary(summary)
        
        paths = recommender.export()
        
        assert "recommendations" in paths
        assert "migration_sql" in paths
        assert os.path.exists(paths["recommendations"])
        assert os.path.exists(paths["migration_sql"])
    
    def test_suggest_numeric_type_small(self):
        """Test suggesting numeric type for small values."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        suggested = recommender._suggest_numeric_type(1234.56)
        assert suggested == "NUMERIC(14,4)"
    
    def test_suggest_numeric_type_medium(self):
        """Test suggesting numeric type for medium values."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        suggested = recommender._suggest_numeric_type(1234567890.0)
        assert suggested == "NUMERIC(20,6)"
    
    def test_suggest_numeric_type_large(self):
        """Test suggesting numeric type for large values."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        # Test with value > 1e18
        suggested = recommender._suggest_numeric_type(17762630700.0)
        assert suggested in ["NUMERIC(20,6)", "NUMERIC(25,6)", "NUMERIC(30,6)"]


class TestDataProfile:
    """Tests for DataProfile dataclass."""
    
    def test_create_data_profile(self):
        """Test creating a data profile."""
        profile = DataProfile(
            column_name="name",
            current_type="VARCHAR(255)",
        )
        
        assert profile.column_name == "name"
        assert profile.current_type == "VARCHAR(255)"
        assert profile.max_length_observed == 0
        assert profile.max_value_observed is None
        assert profile.total_values == 0
    
    def test_update_with_string(self):
        """Test updating profile with string value."""
        profile = DataProfile(
            column_name="name",
            current_type="VARCHAR(255)",
        )
        
        profile.update_with_value("Hello")
        assert profile.max_length_observed == 5
        assert profile.total_values == 1
        
        profile.update_with_value("World!")
        assert profile.max_length_observed == 6
        
        # Create a string longer than 255 characters
        long_string = "A very long string that exceeds 255 characters" + "x" * 250
        profile.update_with_value(long_string)
        assert profile.max_length_observed > 255
    
    def test_update_with_numeric(self):
        """Test updating profile with numeric value."""
        profile = DataProfile(
            column_name="amount",
            current_type="NUMERIC(12,2)",
        )
        
        profile.update_with_value(1234.56)
        assert profile.max_value_observed == 1234.56
        assert profile.total_values == 1
        
        profile.update_with_value(9999.99)
        assert profile.max_value_observed == 9999.99
    
    def test_update_with_none(self):
        """Test updating profile with None value."""
        profile = DataProfile(
            column_name="name",
            current_type="VARCHAR(255)",
        )
        
        profile.update_with_value(None)
        assert profile.null_count == 1
        assert profile.total_values == 1
        assert profile.max_length_observed == 0
    
    def test_to_dict(self):
        """Test converting profile to dictionary."""
        profile = DataProfile(
            column_name="name",
            current_type="VARCHAR(255)",
        )
        profile.max_length_observed = 500
        profile.total_values = 100
        profile.null_count = 5
        
        data = profile.to_dict()
        
        assert data["current_type"] == "VARCHAR(255)"
        assert data["max_length_observed"] == 500
        assert data["total_values"] == 100
        assert data["null_count"] == 5


class TestSchemaRecommenderIntegration:
    """Integration tests for schema recommender with real data."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_workflow(self):
        """Test complete workflow from errors to recommendations."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        # Product template with name issues
        product_summary = BatchErrorSummary(model="product.template", table_name="product_template")
        product_summary.processed = 1000
        product_summary.success = 700
        product_summary.failed = 300
        product_summary.errors_by_category[ErrorCategory.DATA_TOO_LONG] = 250
        product_summary.errors_by_category[ErrorCategory.NUMERIC_OVERFLOW] = 50
        product_summary.errors_by_column["name"] = 200
        product_summary.errors_by_column["description"] = 50
        product_summary.errors_by_column["list_price"] = 50
        
        # Add data profiles
        profile_name = DataProfile(column_name="name", current_type="VARCHAR(255)")
        profile_name.max_length_observed = 834
        product_summary.data_profiles["name"] = profile_name
        
        profile_price = DataProfile(column_name="list_price", current_type="NUMERIC(12,2)")
        profile_price.max_value_observed = 17762630700.0
        product_summary.data_profiles["list_price"] = profile_price
        
        recommender.add_batch_summary(product_summary)
        
        # Sale order with total issues
        sale_summary = BatchErrorSummary(model="sale.order", table_name="sale_order")
        sale_summary.processed = 500
        sale_summary.success = 480
        sale_summary.failed = 20
        sale_summary.errors_by_category[ErrorCategory.NUMERIC_OVERFLOW] = 20
        sale_summary.errors_by_column["amount_total"] = 20
        
        profile_amount = DataProfile(column_name="amount_total", current_type="NUMERIC(14,2)")
        profile_amount.max_value_observed = 999999999.99
        sale_summary.data_profiles["amount_total"] = profile_amount
        
        recommender.add_batch_summary(sale_summary)
        
        # Generate and export
        recommendations = recommender.generate_recommendations()
        sql = recommender.generate_migration_sql()
        paths = recommender.export()
        
        # Verify recommendations
        assert "product.template" in recommendations
        assert "sale.order" in recommendations
        
        # Verify SQL
        assert "ALTER TABLE product_template" in sql
        assert "ALTER TABLE sale_order" in sql
        assert "TYPE TEXT" in sql
        assert "TYPE NUMERIC" in sql
        
        # Verify files exported
        assert os.path.exists(paths["recommendations"])
        assert os.path.exists(paths["migration_sql"])
    
    def test_empty_summary(self):
        """Test with summary that has no errors."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        summary = BatchErrorSummary(model="res.partner", table_name="res_partner")
        summary.processed = 1000
        summary.success = 1000
        summary.failed = 0
        
        recommender.add_batch_summary(summary)
        
        recommendations = recommender.generate_recommendations()
        assert "res.partner" in recommendations
        assert len(recommendations["res.partner"]["columns"]) == 0
