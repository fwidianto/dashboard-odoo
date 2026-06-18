"""Tests for the schema recommender module."""

import pytest
import os
import tempfile
import shutil
from decimal import Decimal

from src.reporting.error_enums import ErrorCategory
from src.reporting.schema_recommender import SchemaRecommender, ColumnRecommendation, ModelRecommendation
from src.reporting.error_reporter import BatchSummary, DataProfile, ModelErrorStats


class TestColumnRecommendation:
    """Tests for ColumnRecommendation dataclass."""

    def test_create_column_recommendation(self):
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
        assert rec.estimated_impact == 712


class TestSchemaRecommender:
    """Tests for SchemaRecommender class."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init(self):
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        assert recommender.reports_dir.name == "schema_recommendations"

    def test_add_batch_summary(self):
        """Test adding batch summary with errors."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        stats = ModelErrorStats(model="product.template", table_name="product_template")
        stats.errors_by_column["name"] = 100
        stats.data_profiles["name"] = DataProfile(column_name="name", current_type="VARCHAR(255)")
        
        summary = BatchSummary(model="product.template", table_name="product_template", stats=stats)
        recommender.add_batch_summary(summary)
        
        assert "product.template" in recommender._recommendations

    def test_generate_recommendations(self):
        """Test generating recommendations."""
        recommender = SchemaRecommender(reports_dir=self.temp_dir)
        
        stats = ModelErrorStats(model="test.model", table_name="test_table")
        stats.errors_by_column["name"] = 100
        summary = BatchSummary(model="test.model", table_name="test_table", stats=stats)
        recommender.add_batch_summary(summary)
        
        recommendations = recommender.generate_recommendations()
        assert "test.model" in recommendations

    def test_suggest_numeric_type(self):
        """Test numeric type suggestion."""
        recommender = SchemaRecommender()
        assert recommender._suggest_numeric_type(100.0) == "NUMERIC(14,4)"
        assert recommender._suggest_numeric_type(1e10) == "NUMERIC(20,6)"
        assert recommender._suggest_numeric_type(1e20) == "NUMERIC(30,6)"


class TestDataProfile:
    """Tests for DataProfile dataclass."""

    def test_create(self):
        profile = DataProfile(column_name="name", current_type="VARCHAR(255)")
        assert profile.column_name == "name"
        assert profile.current_type == "VARCHAR(255)"
        assert profile.max_length_observed is None

    def test_to_dict(self):
        profile = DataProfile(column_name="name", current_type="VARCHAR(255)")
        profile.max_length_observed = 100
        result = profile.to_dict()
        assert result["column_name"] == "name"
        assert result["max_length_observed"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
