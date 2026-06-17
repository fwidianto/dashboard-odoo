"""Tests for error reporting and diagnostics module."""

import csv
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.reporting.error_enums import ErrorCategory
from src.reporting.error_reporter import (
    ErrorReporter,
    ErrorRecord,
    BatchErrorSummary,
    SyncErrorReport,
)


class TestErrorCategory:
    """Tests for ErrorCategory classification."""

    def test_classify_varchar_overflow(self):
        """Test classification of VARCHAR overflow errors."""
        error_msg = 'value too long for type character varying(255)'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.DATA_TOO_LONG

    def test_classify_string_length_error(self):
        """Test classification of string length errors."""
        error_msg = 'string data right truncation'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.DATA_TOO_LONG

    def test_classify_numeric_overflow(self):
        """Test classification of numeric overflow errors."""
        error_msg = 'numeric field overflow: precision 5 scale 2'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.NUMERIC_OVERFLOW

    def test_classify_numeric_out_of_range(self):
        """Test classification of numeric out of range errors."""
        error_msg = 'value out of range for type numeric'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.NUMERIC_OVERFLOW

    def test_classify_null_constraint(self):
        """Test classification of NULL constraint violations."""
        error_msg = 'null value in column "name" violates not-null constraint'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.NULL_CONSTRAINT

    def test_classify_foreign_key(self):
        """Test classification of foreign key violations."""
        error_msg = 'insert or update violates foreign key constraint'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.FOREIGN_KEY

    def test_classify_unique_constraint(self):
        """Test classification of unique constraint violations."""
        error_msg = 'duplicate key value violates unique constraint'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.UNIQUE_CONSTRAINT

    def test_classify_duplicate_key(self):
        """Test classification of duplicate key errors."""
        error_msg = 'duplicate key: key (id)=(1) already exists'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.UNIQUE_CONSTRAINT

    def test_classify_schema_error_missing_column(self):
        """Test classification of missing column errors."""
        error_msg = 'column "invalid_col" does not exist'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.SCHEMA_ERROR

    def test_classify_unknown(self):
        """Test classification of unknown errors."""
        error_msg = 'some mysterious error occurred'
        category = ErrorCategory.classify_from_message(error_msg)
        assert category == ErrorCategory.UNKNOWN


class TestErrorRecord:
    """Tests for ErrorRecord dataclass."""

    def test_create_error_record(self):
        """Test creating an error record."""
        record = ErrorRecord(
            model="product.template",
            record_id=123,
            error_category=ErrorCategory.DATA_TOO_LONG,
            error_message="value too long for type character varying(255)",
            column_name="name",
            value_preview="This is a very long product name...",
        )
        
        assert record.model == "product.template"
        assert record.record_id == 123
        assert record.error_category == ErrorCategory.DATA_TOO_LONG
        assert record.column_name == "name"

    def test_to_dict(self):
        """Test converting error record to dictionary."""
        record = ErrorRecord(
            model="res.partner",
            record_id=456,
            error_category=ErrorCategory.NULL_CONSTRAINT,
            error_message="violates not-null constraint",
        )
        
        result = record.to_dict()
        
        assert result["model"] == "res.partner"
        assert result["record_id"] == 456
        assert result["error_category"] == "NULL_CONSTRAINT"
        assert "timestamp" in result


class TestBatchErrorSummary:
    """Tests for BatchErrorSummary."""

    def test_add_error(self):
        """Test adding errors to batch summary."""
        summary = BatchErrorSummary(model="test.model")
        
        summary.add_error(
            ErrorCategory.DATA_TOO_LONG,
            record_id=1,
            error_message="value too long",
            column_name="description",
        )
        
        assert summary.failed == 1
        assert summary.errors_by_category[ErrorCategory.DATA_TOO_LONG] == 1

    def test_record_success(self):
        """Test recording successful operations."""
        summary = BatchErrorSummary(model="test.model")
        
        summary.record_success(5)
        summary.record_success(3)
        
        assert summary.processed == 8
        assert summary.success == 8

    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        summary = BatchErrorSummary(model="test.model")
        
        # Record success first (90 records)
        summary.record_success(90)
        # Then add errors - each add_error also increments processed
        summary.add_error(ErrorCategory.NUMERIC_OVERFLOW, record_id=1)
        summary.add_error(ErrorCategory.NUMERIC_OVERFLOW, record_id=2)
        summary.add_error(ErrorCategory.DATA_TOO_LONG, record_id=3)
        summary.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=4)
        summary.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=5)
        summary.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=6)
        summary.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=7)
        summary.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=8)
        summary.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=9)
        summary.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=10)
        
        # processed = 90 (successes) + 10 (errors) = 100
        assert summary.processed == 100
        # success = 90
        assert summary.success == 90
        # failed = 10
        assert summary.failed == 10
        # Error rate = 10 / 100 * 100 = 10%
        assert summary.error_rate == 10.0

    def test_error_rate_zero_processed(self):
        """Test error rate with zero processed records."""
        summary = BatchErrorSummary(model="test.model")
        assert summary.error_rate == 0.0

    def test_sample_records_limit(self):
        """Test that sample records are limited."""
        summary = BatchErrorSummary(model="test.model")
        
        # Add more than 5 errors for DATA_TOO_LONG
        for i in range(10):
            summary.add_error(
                ErrorCategory.DATA_TOO_LONG,
                record_id=i,
                column_name="name",
                value_preview=f"Very long value {i}",
            )
        
        # Should only have 5 samples
        assert len(summary.sample_records[ErrorCategory.DATA_TOO_LONG]) == 5


class TestSyncErrorReport:
    """Tests for SyncErrorReport."""

    def test_add_model_summary(self):
        """Test adding model summaries to report."""
        report = SyncErrorReport()
        
        summary1 = BatchErrorSummary(model="product.template")
        summary1.record_success(100)
        summary1.add_error(ErrorCategory.DATA_TOO_LONG, record_id=1)
        
        summary2 = BatchErrorSummary(model="sale.order")
        summary2.record_success(200)
        
        report.add_model_summary("product.template", summary1)
        report.add_model_summary("sale.order", summary2)
        
        assert len(report.models) == 2
        # Total processed = 100 (success) + 1 (error) + 200 (success) = 301
        assert report.get_total_processed() == 301
        # Total success = 100 + 200 = 300
        assert report.get_total_success() == 300
        # Total failed = 1
        assert report.get_total_failed() == 1

    def test_overall_error_rate(self):
        """Test overall error rate calculation."""
        report = SyncErrorReport()
        
        summary1 = BatchErrorSummary(model="model1")
        summary1.record_success(80)
        summary1.add_error(ErrorCategory.UNKNOWN, record_id=1)
        summary1.add_error(ErrorCategory.UNKNOWN, record_id=2)
        
        summary2 = BatchErrorSummary(model="model2")
        summary2.record_success(190)
        summary2.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=3)
        summary2.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=4)
        summary2.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=5)
        summary2.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=6)
        summary2.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=7)
        summary2.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=8)
        summary2.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=9)
        summary2.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=10)
        
        report.add_model_summary("model1", summary1)
        report.add_model_summary("model2", summary2)
        
        # Total processed = successes + errors (each add_error increments processed)
        # model1: 80 success + 2 errors = 82 processed
        # model2: 190 success + 8 errors = 198 processed
        # Total: 82 + 198 = 280
        assert report.get_total_processed() == 280
        # Total failed = only errors count
        # model1: 2 errors, model2: 8 errors = 10 total
        assert report.get_total_failed() == 10
        assert report.get_overall_error_rate() == pytest.approx(3.57, rel=0.1)

    def test_top_failure_causes(self):
        """Test getting top failure causes."""
        report = SyncErrorReport()
        
        summary1 = BatchErrorSummary(model="model1")
        summary1.record_success(100)
        summary1.add_error(ErrorCategory.DATA_TOO_LONG, record_id=1)
        summary1.add_error(ErrorCategory.DATA_TOO_LONG, record_id=2)
        summary1.add_error(ErrorCategory.DATA_TOO_LONG, record_id=3)
        summary1.add_error(ErrorCategory.NULL_CONSTRAINT, record_id=4)
        
        summary2 = BatchErrorSummary(model="model2")
        summary2.record_success(100)
        summary2.add_error(ErrorCategory.DATA_TOO_LONG, record_id=5)
        summary2.add_error(ErrorCategory.NUMERIC_OVERFLOW, record_id=6)
        summary2.add_error(ErrorCategory.NUMERIC_OVERFLOW, record_id=7)
        summary2.add_error(ErrorCategory.NUMERIC_OVERFLOW, record_id=8)
        summary2.add_error(ErrorCategory.NUMERIC_OVERFLOW, record_id=9)
        
        report.add_model_summary("model1", summary1)
        report.add_model_summary("model2", summary2)
        
        top_causes = report.get_top_failure_causes()
        
        assert len(top_causes) == 3
        assert top_causes[0] == (ErrorCategory.DATA_TOO_LONG, 4)
        assert top_causes[1] == (ErrorCategory.NUMERIC_OVERFLOW, 4)
        assert top_causes[2] == (ErrorCategory.NULL_CONSTRAINT, 1)


class TestErrorReporter:
    """Tests for ErrorReporter."""

    def test_start_end_batch(self):
        """Test starting and ending batches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.start_batch("product.template")
            assert reporter._current_model == "product.template"
            assert reporter._current_batch is not None
            
            summary = reporter.end_batch()
            assert summary is not None
            assert summary.model == "product.template"
            assert reporter._current_model is None

    def test_record_success(self):
        """Test recording successful operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.start_batch("test.model")
            reporter.record_success(10)
            reporter.record_success(5)
            
            summary = reporter.get_batch_summary()
            assert summary.success == 15
            assert summary.processed == 15

    def test_record_error(self):
        """Test recording errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.start_batch("test.model")
            reporter.record_success(100)
            
            reporter.record_error(
                ErrorCategory.DATA_TOO_LONG,
                record_id=101,
                error_message="value too long for type varchar(255)",
                column_name="description",
                value="A" * 300,
            )
            
            summary = reporter.get_batch_summary()
            assert summary.failed == 1
            assert summary.errors_by_category[ErrorCategory.DATA_TOO_LONG] == 1
            
            # Check that error was recorded
            assert reporter.has_errors()
            assert len(reporter._all_errors) == 1
            assert reporter._all_errors[0].record_id == 101

    def test_csv_export(self):
        """Test CSV export functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.start_batch("product.template")
            reporter.record_success(100)
            reporter.record_error(
                ErrorCategory.NULL_CONSTRAINT,
                record_id=101,
                error_message="null value in column",
                column_name="name",
            )
            reporter.end_batch()
            
            csv_path, json_path = reporter.export()
            
            # Verify CSV was created
            assert Path(csv_path).exists()
            
            # Read and verify CSV content
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
                assert len(rows) == 1
                assert rows[0]["model"] == "product.template"
                assert rows[0]["record_id"] == "101"
                assert rows[0]["error_category"] == "NULL_CONSTRAINT"
                assert rows[0]["column_name"] == "name"

    def test_json_export(self):
        """Test JSON export functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.start_batch("res.partner")
            reporter.record_success(200)
            reporter.record_error(
                ErrorCategory.NUMERIC_OVERFLOW,
                record_id=201,
                error_message="numeric field overflow",
            )
            reporter.end_batch()
            
            csv_path, json_path = reporter.export()
            
            # Verify JSON was created
            assert Path(json_path).exists()
            
            # Read and verify JSON content
            with open(json_path, "r") as f:
                data = json.load(f)
                
                assert "run_timestamp" in data
                assert "models" in data
                assert "res.partner" in data["models"]
                
                model_data = data["models"]["res.partner"]
                # Processed = 200 success + 1 error = 201
                assert model_data["processed"] == 201
                # Success = 200
                assert model_data["success"] == 200
                # Failed = 1
                assert model_data["failed"] == 1
                assert "NUMERIC_OVERFLOW" in model_data["errors"]

    def test_print_summary_no_errors(self, capsys):
        """Test printing summary when there are no errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.print_summary()
            
            captured = capsys.readouterr()
            assert "No sync errors recorded" in captured.out

    def test_print_summary_with_errors(self, capsys):
        """Test printing summary with errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.start_batch("product.template")
            reporter.record_success(16421)
            for i in range(100):
                reporter.record_error(
                    ErrorCategory.DATA_TOO_LONG,
                    record_id=1000 + i,
                    error_message="value too long for type varchar(255)",
                    column_name="description",
                )
            for i in range(15):
                reporter.record_error(
                    ErrorCategory.NULL_CONSTRAINT,
                    record_id=2000 + i,
                    error_message="null value in column",
                    column_name="name",
                )
            reporter.end_batch()
            
            reporter.print_summary()
            
            captured = capsys.readouterr()
            assert "SYNC HEALTH REPORT" in captured.out
            assert "product.template" in captured.out
            assert "16421" in captured.out
            assert "115" in captured.out  # total failed
            assert "DATA_TOO_LONG" in captured.out
            assert "NULL_CONSTRAINT" in captured.out

    def test_batch_summary_print(self, capsys):
        """Test batch summary printing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.start_batch("sale.order")
            reporter.record_success(2200)
            reporter.record_error(
                ErrorCategory.UNIQUE_CONSTRAINT,
                record_id=2201,
                error_message="duplicate key",
            )
            reporter.record_error(
                ErrorCategory.UNIQUE_CONSTRAINT,
                record_id=2202,
                error_message="duplicate key",
            )
            
            # Print before ending batch (end_batch clears current batch)
            reporter.print_batch_summary()
            
            captured = capsys.readouterr()
            assert "BATCH ERROR SUMMARY" in captured.out
            assert "sale.order" in captured.out
            assert "2202" in captured.out  # processed (2200 success + 2 errors)
            assert "2200" in captured.out  # success
            assert "UNIQUE_CONSTRAINT" in captured.out

    def test_clear(self):
        """Test clearing error reporter state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            reporter.start_batch("test.model")
            reporter.record_success(100)
            reporter.record_error(
                ErrorCategory.UNKNOWN,
                record_id=101,
                error_message="test error",
            )
            reporter.end_batch()
            
            assert reporter.has_errors()
            assert len(reporter._all_errors) == 1
            
            reporter.clear()
            
            assert not reporter.has_errors()
            assert len(reporter._all_errors) == 0
            assert reporter._current_model is None


class TestErrorClassificationIntegration:
    """Integration tests for error classification in real scenarios."""

    def test_varchar_overflow_classification(self):
        """Test VARCHAR overflow error classification."""
        error_messages = [
            'value too long for type character varying(255)',
            'string data right truncation',
            'ERROR: value too long for type varchar(100)',
            'VARCHAR length exceeded',
        ]
        
        for msg in error_messages:
            category = ErrorCategory.classify_from_message(msg)
            assert category == ErrorCategory.DATA_TOO_LONG, f"Failed for: {msg}"

    def test_numeric_overflow_classification(self):
        """Test numeric overflow error classification."""
        error_messages = [
            'numeric field overflow',
            'ERROR: numeric scale exceeds column precision',
            'value out of range for type numeric',
            'decimal overflow',
        ]
        
        for msg in error_messages:
            category = ErrorCategory.classify_from_message(msg)
            assert category == ErrorCategory.NUMERIC_OVERFLOW, f"Failed for: {msg}"

    def test_null_constraint_classification(self):
        """Test NULL constraint error classification."""
        error_messages = [
            'null value in column "name" violates not-null constraint',
            'NOT NULL constraint failed',
            'ERROR: null value in column',
        ]
        
        for msg in error_messages:
            category = ErrorCategory.classify_from_message(msg)
            assert category == ErrorCategory.NULL_CONSTRAINT, f"Failed for: {msg}"

    def test_foreign_key_classification(self):
        """Test foreign key error classification."""
        error_messages = [
            'insert or update violates foreign key constraint "fk_orders_partner"',
            'referenced key does not exist',
            'foreign key constraint failed',
        ]
        
        for msg in error_messages:
            category = ErrorCategory.classify_from_message(msg)
            assert category == ErrorCategory.FOREIGN_KEY, f"Failed for: {msg}"

    def test_unique_constraint_classification(self):
        """Test unique constraint error classification."""
        error_messages = [
            'duplicate key value violates unique constraint "uniq_orders_reference"',
            'ERROR: duplicate key',
            'key (id)=(123) already exists',
        ]
        
        for msg in error_messages:
            category = ErrorCategory.classify_from_message(msg)
            assert category == ErrorCategory.UNIQUE_CONSTRAINT, f"Failed for: {msg}"

    def test_schema_error_classification(self):
        """Test schema error classification."""
        error_messages = [
            'column "invalid_field" does not exist',
            'relation "unknown_table" does not exist',
            'type "unknown_type" does not exist',
        ]
        
        for msg in error_messages:
            category = ErrorCategory.classify_from_message(msg)
            assert category == ErrorCategory.SCHEMA_ERROR, f"Failed for: {msg}"


class TestValuePreviewTruncation:
    """Tests for value preview truncation."""

    def test_long_value_truncation(self):
        """Test that long values are truncated to 200 chars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            long_value = "A" * 500  # 500 character value
            
            reporter.start_batch("test.model")
            reporter.record_error(
                ErrorCategory.DATA_TOO_LONG,
                record_id=1,
                error_message="value too long",
                column_name="description",
                value=long_value,
            )
            
            assert reporter._all_errors[0].value_preview is not None
            assert len(reporter._all_errors[0].value_preview) == 200

    def test_short_value_preserved(self):
        """Test that short values are not truncated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = ErrorReporter(reports_dir=tmpdir)
            
            short_value = "Short product name"
            
            reporter.start_batch("test.model")
            reporter.record_error(
                ErrorCategory.DATA_TOO_LONG,
                record_id=1,
                error_message="value too long",
                column_name="name",
                value=short_value,
            )
            
            assert reporter._all_errors[0].value_preview == short_value
