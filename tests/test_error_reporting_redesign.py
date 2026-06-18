"""Tests for error reporting and root cause detection."""

import pytest
import tempfile
import os
from datetime import datetime

from src.reporting.error_enums import ErrorCategory
from src.reporting.error_reporter import ErrorReporter


class TestErrorClassification:
    """Test error classification."""
    
    def test_null_constraint_classification(self):
        """NULL_CONSTRAINT should be detected."""
        msg = "null value in column move_id violates not-null constraint"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.NULL_CONSTRAINT
    
    def test_data_too_long_classification(self):
        """DATA_TOO_LONG should be detected."""
        msg = "value too long for type character varying(255)"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.DATA_TOO_LONG
    
    def test_numeric_overflow_classification(self):
        """NUMERIC_OVERFLOW should be detected."""
        msg = "numeric field overflow"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.NUMERIC_OVERFLOW
    
    def test_foreign_key_classification(self):
        """FOREIGN_KEY should be detected."""
        msg = "insert or update violates foreign key constraint"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.FOREIGN_KEY
    
    def test_unique_constraint_classification(self):
        """UNIQUE_CONSTRAINT should be detected."""
        msg = "duplicate key value violates unique constraint"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.UNIQUE_CONSTRAINT
    
    def test_transaction_aborted_classification(self):
        """TRANSACTION_ABORTED should be detected."""
        msg = "current transaction is aborted"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.TRANSACTION_ABORTED
    
    def test_unknown_classification(self):
        """Unknown errors should return UNKNOWN."""
        msg = "some random error that we cannot classify"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.UNKNOWN


class TestErrorReporter:
    """Test ErrorReporter with root cause detection."""
    
    def test_record_success(self):
        """Test recording successful operations."""
        reporter = ErrorReporter()
        reporter.start_batch(model="product.template"); reporter.record_success(count=100)
        
        stats = reporter.model_stats["product.template"]
        assert stats.success == 100
        assert stats.processed == 100
        assert stats.failed == 0
    
    def test_record_single_error(self):
        """Test recording a single error."""
        reporter = ErrorReporter()
        
        reporter.record_error(
            model="account.move.line",
            table_name="account_move_line",
            category=ErrorCategory.NULL_CONSTRAINT,
            record_id=1335,
            error_message="null value violates not-null constraint",
            column_name="move_id",
            value=None,
        )
        
        stats = reporter.model_stats["account.move.line"]
        assert stats.failed == 1
        assert stats.cascade_failures == 0
        assert stats.first_root_cause is not None
        assert stats.first_root_cause.error_category == ErrorCategory.NULL_CONSTRAINT
        assert stats.first_root_cause.record_id == 1335
    
    def test_cascade_failures_not_counted_as_root_cause(self):
        """TRANSACTION_ABORTED errors should be tracked as cascade failures."""
        reporter = ErrorReporter()
        
        # First: real NULL_CONSTRAINT error
        reporter.record_error(
            model="account.move.line",
            table_name="account_move_line",
            category=ErrorCategory.NULL_CONSTRAINT,
            record_id=1335,
            error_message="null value violates not-null constraint",
        )
        
        # Second: cascade TRANSACTION_ABORTED errors
        for i in range(999):
            reporter.record_error(
                model="account.move.line",
                table_name="account_move_line",
                category=ErrorCategory.TRANSACTION_ABORTED,
                record_id=1336 + i,
                error_message="current transaction is aborted",
            )
        
        stats = reporter.model_stats["account.move.line"]
        
        # Should only have 1 real failure (the NULL_CONSTRAINT)
        assert stats.failed == 1
        
        # Should have 999 cascade failures
        assert stats.cascade_failures == 999
        
        # Root cause should only be the first real error
        assert stats.first_root_cause.error_category == ErrorCategory.NULL_CONSTRAINT
        
        # Total processed should include cascade failures for tracking
        assert stats.processed == 1000
    
    def test_multiple_root_causes(self):
        """Multiple different error types should all be tracked."""
        reporter = ErrorReporter()
        
        reporter.record_error(
            model="test.model",
            table_name="test_table",
            category=ErrorCategory.NULL_CONSTRAINT,
            record_id=1,
            error_message="null error",
        )
        
        reporter.record_error(
            model="test.model",
            table_name="test_table",
            category=ErrorCategory.DATA_TOO_LONG,
            record_id=2,
            error_message="string too long",
        )
        
        reporter.record_error(
            model="test.model",
            table_name="test_table",
            category=ErrorCategory.TRANSACTION_ABORTED,
            record_id=3,
            error_message="cascade",
        )
        
        stats = reporter.model_stats["test.model"]
        assert stats.failed == 2  # Only real errors
        assert stats.cascade_failures == 1
        assert len(stats.root_causes) == 2
    
    def test_export_json(self):
        """Test JSON export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(output_dir=tmpdir)
            reporter.start_batch(model="test.model"); reporter.record_success(count=10)
            reporter.record_error(
                model="test.model",
                table_name="test_table",
                category=ErrorCategory.NULL_CONSTRAINT,
                record_id=1,
            )
            
            filepath = reporter.export_json()
            
            import json
            with open(filepath) as f:
                data = json.load(f)
            
            assert "models" in data
            assert "test.model" in data["models"]
            assert data["models"]["test.model"]["success"] == 10
            assert data["models"]["test.model"]["failed"] == 1
            assert data["models"]["test.model"]["cascade_failures"] == 0
    
    def test_export_root_causes(self):
        """Test root causes JSON export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(output_dir=tmpdir)
            reporter.record_error(
                model="test.model",
                table_name="test_table",
                category=ErrorCategory.NULL_CONSTRAINT,
                record_id=1,
                error_message="test error",
                column_name="test_col",
            )
            
            filepath = reporter.export_root_causes(filename=tmpdir + "/root_causes.json")
            
            import json
            with open(filepath) as f:
                data = json.load(f)
            
            assert data["total_root_causes"] == 1
            assert data["root_causes"][0]["record_id"] == 1
            assert data["root_causes"][0]["column"] == "test_col"
    
    def test_print_summary(self):
        """Test print summary doesn't crash."""
        reporter = ErrorReporter()
        reporter.start_batch(model="test.model"); reporter.record_success(count=100)
        reporter.record_error(
            model="test.model",
            table_name="test_table",
            category=ErrorCategory.NULL_CONSTRAINT,
            record_id=1,
        )
        
        # Should not raise
        reporter.print_summary()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
