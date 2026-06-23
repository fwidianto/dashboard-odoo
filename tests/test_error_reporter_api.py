"""Tests for ErrorReporter API compatibility with SyncEngine."""

import pytest
import tempfile
import os

from src.reporting.error_enums import ErrorCategory
from src.reporting.error_reporter import ErrorReporter


class TestErrorReporterAPI:
    """Test ErrorReporter API matches SyncEngine expectations."""
    
    def test_start_batch(self):
        """Test start_batch method exists and works."""
        reporter = ErrorReporter()
        reporter.start_batch(model="product.template", table_name="product_template")
        assert "product.template" in reporter.model_stats
        assert reporter._current_model == "product.template"
    
    def test_end_batch(self):
        """Test end_batch method exists and works."""
        reporter = ErrorReporter()
        reporter.start_batch(model="product.template")
        reporter.end_batch()
        assert reporter._current_model is None
    
    def test_record_success(self):
        """Test record_success method exists and works."""
        reporter = ErrorReporter()
        reporter.start_batch(model="product.template")
        reporter.record_success(count=100)
        stats = reporter.model_stats["product.template"]
        assert stats.success == 100
        assert stats.processed == 100
    
    def test_record_failure(self):
        """Test record_failure method exists and works."""
        reporter = ErrorReporter()
        reporter.start_batch(model="account.move.line")
        reporter.record_failure(
            category=ErrorCategory.NULL_CONSTRAINT,
            record_id=1335,
            error_message="null value in column",
            column_name="move_id",
        )
        stats = reporter.model_stats["account.move.line"]
        assert stats.failed == 1
    
    def test_generate_report(self):
        """Test generate_report method exists and works."""
        reporter = ErrorReporter()
        reporter.start_batch(model="test.model")
        reporter.record_success(count=50)
        reporter.record_failure(ErrorCategory.NULL_CONSTRAINT, record_id=1)
        
        report = reporter.generate_report()
        assert "models" in report
        assert "test.model" in report["models"]
        assert report["models"]["test.model"]["success"] == 50
        assert report["models"]["test.model"]["failed"] == 1
    
    def test_save_report(self):
        """Test save_report method exists and works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(output_dir=tmpdir)
            reporter.start_batch(model="test.model")
            reporter.record_success(count=10)
            
            filepath = reporter.save_report()
            assert os.path.exists(filepath)
    
    def test_print_batch_summary(self):
        """Test print_batch_summary method exists."""
        reporter = ErrorReporter()
        reporter.start_batch(model="test.model")
        reporter.record_success(count=10)
        # Should not raise
        reporter.print_batch_summary()


class TestRootCauseDetection:
    """Test root cause detection works correctly."""
    
    def test_cascade_failures_tracked_separately(self):
        """TRANSACTION_ABORTED errors are tracked as cascade failures."""
        reporter = ErrorReporter()
        reporter.start_batch(model="test.model")
        
        # First: real error
        reporter.record_failure(
            category=ErrorCategory.NULL_CONSTRAINT,
            record_id=1,
            error_message="null value violates not-null constraint",
        )
        
        # Subsequent: cascade errors
        for i in range(999):
            reporter.record_failure(
                category=ErrorCategory.TRANSACTION_ABORTED,
                record_id=2 + i,
                error_message="current transaction is aborted",
            )
        
        stats = reporter.model_stats["test.model"]
        assert stats.failed == 1  # Only real errors
        assert stats.cascade_failures == 999
    
    def test_root_cause_exported(self):
        """Root cause is saved for later analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(output_dir=tmpdir)
            reporter.start_batch(model="test.model")
            reporter.record_failure(
                category=ErrorCategory.NULL_CONSTRAINT,
                record_id=1335,
                error_message="null value in column move_id",
                column_name="move_id",
            )
            
            filepath = reporter.export_root_causes(filename=tmpdir + "/root_causes.json")
            
            import json
            with open(filepath) as f:
                data = json.load(f)
            
            assert data["total_root_causes"] == 1
            assert data["root_causes"][0]["record_id"] == 1335
            assert data["root_causes"][0]["column"] == "move_id"


class TestErrorClassification:
    """Test error classification still works."""
    
    def test_null_constraint(self):
        msg = "null value in column violates not-null constraint"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.NULL_CONSTRAINT
    
    def test_transaction_aborted(self):
        msg = "current transaction is aborted"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.TRANSACTION_ABORTED
    
    def test_data_too_long(self):
        msg = "value too long for type character varying(255)"
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.DATA_TOO_LONG

    def test_invalid_text_for_integer_is_schema_error(self):
        msg = 'invalid input syntax for type integer: "VELO CITRA TEKNOLOGI, PT"'
        assert ErrorCategory.classify_from_message(msg) == ErrorCategory.SCHEMA_ERROR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
