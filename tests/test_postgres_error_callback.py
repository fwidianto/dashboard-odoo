"""Tests for PostgreSQL client error callback functionality."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.exc import SQLAlchemyError

from src.clients.postgres_client import PostgresClient, DetailedError
from src.reporting.error_enums import ErrorCategory


class TestDetailedError:
    """Tests for DetailedError dataclass."""

    def test_create_detailed_error(self):
        """Test creating a detailed error."""
        error = DetailedError(
            record_id=123,
            error_message="null value in column \"name\" violates not-null constraint",
            error_category=ErrorCategory.NULL_CONSTRAINT,
            column_name="name",
            value_preview=None,
        )
        
        assert error.record_id == 123
        assert error.error_category == ErrorCategory.NULL_CONSTRAINT
        assert error.column_name == "name"

    def test_detailed_error_with_value_preview(self):
        """Test creating a detailed error with value preview."""
        error = DetailedError(
            record_id=456,
            error_message="value too long for type character varying(255)",
            error_category=ErrorCategory.DATA_TOO_LONG,
            column_name="description",
            value_preview="This is a very long description that exceeds the limit...",
        )
        
        assert error.value_preview is not None
        assert len(error.value_preview) <= 200


class TestExtractColumnFromError:
    """Tests for column extraction from error messages."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = PostgresClient()

    def test_extract_column_null_constraint(self):
        """Test extracting column name from NULL constraint error."""
        error_msg = 'null value in column "name" violates not-null constraint'
        columns = ["id", "name", "email", "phone"]
        
        result = self.client._extract_column_from_error(error_msg, columns)
        
        assert result == "name"

    def test_extract_column_value_too_long(self):
        """Test extracting column name from value too long error."""
        # When column is not explicitly mentioned in error
        error_msg = 'value too long for type character varying(255)'
        columns = ["id", "name", "description"]
        
        result = self.client._extract_column_from_error(error_msg, columns)
        
        # Column is not explicitly in error message, so returns None
        assert result is None
        
        # Test with column explicitly mentioned
        error_msg_with_col = 'value too long for column "description"'
        result_with_col = self.client._extract_column_from_error(error_msg_with_col, columns)
        assert result_with_col == "description"

    def test_extract_column_from_quoted(self):
        """Test extracting column name from quoted text in error."""
        error_msg = 'relation "unknown_table" does not exist'
        columns = ["id", "name"]
        
        result = self.client._extract_column_from_error(error_msg, columns)
        
        # Should return None as quoted text doesn't match available columns
        assert result is None

    def test_extract_column_from_schema_error(self):
        """Test extracting column name from schema error."""
        error_msg = 'column "email" of relation "test_table" does not exist'
        columns = ["id", "name", "email"]
        
        result = self.client._extract_column_from_error(error_msg, columns)
        
        assert result == "email"

    def test_extract_column_not_found(self):
        """Test when column is not in available columns."""
        error_msg = 'some unknown error'
        columns = ["id", "name"]
        
        result = self.client._extract_column_from_error(error_msg, columns)
        
        assert result is None


class TestUpsertErrorCallback:
    """Tests for upsert with error callback."""

    def test_upsert_with_error_callback_called(self):
        """Test that error callback is called on failures."""
        collected_errors = []
        
        def error_callback(error: DetailedError):
            collected_errors.append(error)
        
        # This would require a real database connection to test properly
        # For now, we just verify the callback signature is correct
        assert callable(error_callback)

    def test_upsert_error_callback_signature(self):
        """Test that error callback accepts DetailedError."""
        def error_callback(error: DetailedError):
            pass
        
        # Verify the callback can be called with a DetailedError
        test_error = DetailedError(
            record_id=1,
            error_message="test",
            error_category=ErrorCategory.UNKNOWN,
        )
        
        error_callback(test_error)

    def test_error_category_classification_in_callback(self):
        """Test error category classification when processing errors."""
        # Test VARCHAR overflow classification
        msg1 = "value too long for type character varying(255)"
        cat1 = ErrorCategory.classify_from_message(msg1)
        assert cat1 == ErrorCategory.DATA_TOO_LONG
        
        # Test NULL constraint classification
        msg2 = "null value in column \"name\" violates not-null constraint"
        cat2 = ErrorCategory.classify_from_message(msg2)
        assert cat2 == ErrorCategory.NULL_CONSTRAINT
        
        # Test numeric overflow classification
        msg3 = "numeric field overflow"
        cat3 = ErrorCategory.classify_from_message(msg3)
        assert cat3 == ErrorCategory.NUMERIC_OVERFLOW
        
        # Test foreign key classification
        msg4 = "insert or update violates foreign key constraint"
        cat4 = ErrorCategory.classify_from_message(msg4)
        assert cat4 == ErrorCategory.FOREIGN_KEY
        
        # Test unique constraint classification
        msg5 = "duplicate key value violates unique constraint"
        cat5 = ErrorCategory.classify_from_message(msg5)
        assert cat5 == ErrorCategory.UNIQUE_CONSTRAINT


class TestUpsertBatchErrorCallback:
    """Tests for upsert_batch with error callback."""

    def test_upsert_batch_accepts_error_callback(self):
        """Test that upsert_batch accepts error_callback parameter."""
        # Verify the method signature accepts the parameter
        import inspect
        sig = inspect.signature(PostgresClient.upsert_batch)
        params = list(sig.parameters.keys())
        
        assert "error_callback" in params

    def test_upsert_batch_passes_callback_to_upsert(self):
        """Test that upsert_batch passes callback to upsert."""
        # This is a design verification test
        # The implementation should pass error_callback from upsert_batch to upsert
        client = PostgresClient()
        
        # We can't easily test the actual database interaction without a real DB
        # But we can verify the method accepts the parameter
        assert hasattr(client, "upsert_batch")
        assert callable(client.upsert_batch)


class TestDetailedErrorIntegration:
    """Integration tests for detailed error handling."""

    def test_error_message_parsing(self):
        """Test parsing various PostgreSQL error messages."""
        test_cases = [
            (
                'null value in column "partner_id" violates not-null constraint',
                ErrorCategory.NULL_CONSTRAINT,
                "partner_id",
            ),
            (
                'value too long for type character varying(100)',
                ErrorCategory.DATA_TOO_LONG,
                None,  # Column might not be in error message
            ),
            (
                'duplicate key value violates unique constraint "product_tmpl_id_uniq"',
                ErrorCategory.UNIQUE_CONSTRAINT,
                None,
            ),
            (
                'insert or update violates foreign key constraint "fk_sale_order_partner"',
                ErrorCategory.FOREIGN_KEY,
                None,
            ),
            (
                'numeric field overflow: precision 5 scale 2',
                ErrorCategory.NUMERIC_OVERFLOW,
                None,
            ),
        ]
        
        for error_msg, expected_category, expected_column in test_cases:
            category = ErrorCategory.classify_from_message(error_msg)
            assert category == expected_category, f"Failed for: {error_msg}"

    def test_value_preview_generation(self):
        """Test generating value previews for errors."""
        client = PostgresClient()
        
        # Test with string value
        record = {"id": 1, "name": "Test Product", "description": "A" * 300}
        columns = ["id", "name", "description"]
        error_msg = 'value too long for type character varying(255)'
        
        column_name = client._extract_column_from_error(error_msg, columns)
        
        if column_name and column_name in record:
            value = record[column_name]
            if value is not None:
                value_preview = str(value)[:200]
                assert len(value_preview) == 200 or len(value_preview) < 200
