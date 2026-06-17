"""Tests for the self-healing sync engine."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.odoo.self_healing import (
    RootCause,
    RootCauseType,
    ErrorPattern,
    ErrorSample,
    RepairResult,
    SelfHealingEngine,
    MAX_AUTO_FIX_ATTEMPTS,
)


class TestRootCauseDetection:
    """Tests for root cause detection."""
    
    def test_find_root_cause_undefined_column(self):
        """Test detection of UNDEFINED_COLUMN error."""
        engine = SelfHealingEngine(Mock())
        
        # Create mock exception with pgcode
        exc = Mock()
        exc.pgcode = "42703"
        exc.diag = Mock()
        exc.diag.message_primary = 'column "x_custom_field" of relation "product_template" does not exist'
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.UNDEFINED_COLUMN
        assert root_cause.column_name == "x_custom_field"
    
    def test_find_root_cause_string_truncation(self):
        """Test detection of STRING_DATA_RIGHT_TRUNCATION error."""
        engine = SelfHealingEngine(Mock())
        
        exc = Mock()
        exc.pgcode = "22001"
        exc.diag = Mock()
        exc.diag.message_primary = 'value too long for type character varying(255)'
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.STRING_DATA_RIGHT_TRUNCATION
    
    def test_find_root_cause_numeric_overflow(self):
        """Test detection of NUMERIC_VALUE_OUT_OF_RANGE error."""
        engine = SelfHealingEngine(Mock())
        
        exc = Mock()
        exc.pgcode = "22003"
        exc.diag = Mock()
        exc.diag.message_primary = 'numeric field overflow: precision 5 scale 2 exceeded'
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.NUMERIC_VALUE_OUT_OF_RANGE
    
    def test_find_root_cause_not_null_violation(self):
        """Test detection of NOT_NULL_VIOLATION error."""
        engine = SelfHealingEngine(Mock())
        
        # Test from raw message (not psycopg2)
        exc = Exception('null value in column "name" violates not-null constraint')
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.NOT_NULL_VIOLATION
        assert root_cause.column_name == "name"
    
    def test_find_root_cause_datatype_mismatch(self):
        """Test detection of DATATYPE_MISMATCH error."""
        engine = SelfHealingEngine(Mock())
        
        # Test with pgcode in message (real PostgreSQL format)
        exc = Exception('42804: datatype mismatch: column "price" cannot be cast to type NUMERIC')
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.DATATYPE_MISMATCH
    
    def test_find_root_cause_foreign_key(self):
        """Test detection of FOREIGN_KEY_VIOLATION error."""
        engine = SelfHealingEngine(Mock())
        
        exc = Mock()
        exc.pgcode = "23503"
        exc.diag = Mock()
        exc.diag.message_primary = 'insert or update violates foreign key constraint'
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.FOREIGN_KEY_VIOLATION
    
    def test_find_root_cause_unique_violation(self):
        """Test detection of UNIQUE_VIOLATION error."""
        engine = SelfHealingEngine(Mock())
        
        exc = Mock()
        exc.pgcode = "23505"
        exc.diag = Mock()
        exc.diag.message_primary = 'duplicate key value violates unique constraint'
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.UNIQUE_VIOLATION
    
    def test_find_root_cause_from_string(self):
        """Test detection from plain string exception."""
        engine = SelfHealingEngine(Mock())
        
        exc = Exception('column "custom_field" does not exist')
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.UNDEFINED_COLUMN
    
    def test_find_root_cause_unknown(self):
        """Test unknown error classification."""
        engine = SelfHealingEngine(Mock())
        
        exc = Exception('some random error that does not match')
        
        root_cause = engine.find_root_cause(exc)
        
        assert root_cause.type == RootCauseType.UNKNOWN


class TestRepairTypes:
    """Tests for repair type mappings."""
    
    def test_odoo_field_type_to_postgres_text(self):
        """Test TEXT types."""
        engine = SelfHealingEngine(Mock())
        
        assert engine._odoo_field_type_to_postgres('char') == 'TEXT'
        assert engine._odoo_field_type_to_postgres('text') == 'TEXT'
        assert engine._odoo_field_type_to_postgres('html') == 'TEXT'
        assert engine._odoo_field_type_to_postgres('selection') == 'TEXT'
    
    def test_odoo_field_type_to_postgres_numeric(self):
        """Test NUMERIC types."""
        engine = SelfHealingEngine(Mock())
        
        assert engine._odoo_field_type_to_postgres('float') == 'NUMERIC(30,10)'
        assert engine._odoo_field_type_to_postgres('monetary') == 'NUMERIC(30,10)'
    
    def test_odoo_field_type_to_postgres_integer(self):
        """Test INTEGER types."""
        engine = SelfHealingEngine(Mock())
        
        assert engine._odoo_field_type_to_postgres('integer') == 'BIGINT'
        assert engine._odoo_field_type_to_postgres('bigint') == 'BIGINT'
        assert engine._odoo_field_type_to_postgres('many2one') == 'BIGINT'
    
    def test_odoo_field_type_to_postgres_relational(self):
        """Test relational types."""
        engine = SelfHealingEngine(Mock())
        
        assert engine._odoo_field_type_to_postgres('one2many') == 'JSONB'
        assert engine._odoo_field_type_to_postgres('many2many') == 'JSONB'


class TestTargetTypeDetection:
    """Tests for target type detection."""
    
    def test_get_target_type_from_odoo_fields(self):
        """Test getting target type from Odoo fields."""
        engine = SelfHealingEngine(Mock())
        
        odoo_fields = {
            'list_price': {'type': 'monetary'},
            'name': {'type': 'char'},
        }
        
        assert engine._get_target_type('list_price', odoo_fields) == 'NUMERIC(30,10)'
        assert engine._get_target_type('name', odoo_fields) == 'TEXT'
    
    def test_get_target_type_inferred_price(self):
        """Test inferring target type for price columns."""
        engine = SelfHealingEngine(Mock())
        
        # No Odoo fields provided, infer from name
        assert engine._get_target_type('sale_price', None) == 'NUMERIC(30,10)'
        assert engine._get_target_type('amount_total', None) == 'NUMERIC(30,10)'
    
    def test_get_target_type_inferred_date(self):
        """Test inferring target type for date columns."""
        engine = SelfHealingEngine(Mock())
        
        assert engine._get_target_type('date', None) == 'TIMESTAMP'
        assert engine._get_target_type('write_date', None) == 'TIMESTAMP'
    
    def test_get_target_type_default(self):
        """Test default target type."""
        engine = SelfHealingEngine(Mock())
        
        assert engine._get_target_type('unknown_field', None) == 'TEXT'


class TestRequiredFieldDetection:
    """Tests for required field detection."""
    
    def test_check_required_true(self):
        """Test detecting required field."""
        engine = SelfHealingEngine(Mock())
        
        odoo_fields = {
            'name': {'required': True},
            'partner_id': {'required': False},
        }
        
        assert engine._check_if_field_required('name', odoo_fields) is True
        assert engine._check_if_field_required('partner_id', odoo_fields) is False
    
    def test_check_required_false(self):
        """Test detecting non-required field."""
        engine = SelfHealingEngine(Mock())
        
        odoo_fields = {
            'description': {'required': False},
        }
        
        assert engine._check_if_field_required('description', odoo_fields) is False
    
    def test_check_required_unknown_field(self):
        """Test unknown field defaults to False."""
        engine = SelfHealingEngine(Mock())
        
        assert engine._check_if_field_required('unknown', None) is False


class TestErrorPattern:
    """Tests for ErrorPattern dataclass."""
    
    def test_create_pattern(self):
        """Test creating an error pattern."""
        pattern = ErrorPattern(
            model="product.template",
            table="product_template",
            field="x_custom",
            error_type=RootCauseType.STRING_DATA_RIGHT_TRUNCATION,
            fix_applied="migrate_type",
        )
        
        assert pattern.model == "product.template"
        assert pattern.error_type == RootCauseType.STRING_DATA_RIGHT_TRUNCATION
        assert pattern.occurrences == 1
    
    def test_pattern_to_dict(self):
        """Test converting pattern to dict."""
        pattern = ErrorPattern(
            model="sale.order",
            table="sale_order",
            field="amount_total",
            error_type=RootCauseType.NUMERIC_VALUE_OUT_OF_RANGE,
            fix_applied="migrate_type",
        )
        
        data = pattern.to_dict()
        
        assert data["model"] == "sale.order"
        assert data["error_type"] == "NumericValueOutOfRange"
        assert data["fix_applied"] == "migrate_type"


class TestErrorSample:
    """Tests for ErrorSample dataclass."""
    
    def test_create_sample(self):
        """Test creating an error sample."""
        sample = ErrorSample(
            model="product.template",
            table="product_template",
            record_id=123,
            field="list_price",
            error_type=RootCauseType.NUMERIC_VALUE_OUT_OF_RANGE,
            error_message="numeric value out of range",
            value_preview="17762630700.00",
        )
        
        assert sample.record_id == 123
        assert sample.error_type == RootCauseType.NUMERIC_VALUE_OUT_OF_RANGE
    
    def test_sample_to_dict(self):
        """Test converting sample to dict."""
        sample = ErrorSample(
            model="sale.order",
            table="sale_order",
            record_id=456,
            field="date",
            error_type=RootCauseType.DATATYPE_MISMATCH,
            error_message="invalid input syntax",
            value_preview="not a date",
        )
        
        data = sample.to_dict()
        
        assert data["record_id"] == "456"
        assert data["field"] == "date"
        assert data["error_type"] == "DatatypeMismatch"


class TestRepairResult:
    """Tests for RepairResult dataclass."""
    
    def test_successful_repair(self):
        """Test successful repair result."""
        result = RepairResult(
            success=True,
            repair_type="add_column",
            details={"column_added": "x_custom"},
            record_retried=True,
            record_success=True,
        )
        
        assert result.success is True
        assert result.record_retried is True
        assert result.record_success is True
    
    def test_failed_repair(self):
        """Test failed repair result."""
        result = RepairResult(
            success=False,
            repair_type="add_column",
        )
        
        assert result.success is False
        assert result.record_retried is False


class TestSafetyRules:
    """Tests for production safety rules."""
    
    def test_max_auto_fix_attempts(self):
        """Test max auto-fix attempts limit."""
        assert MAX_AUTO_FIX_ATTEMPTS == 3
    
    def test_safe_repair_types(self):
        """Verify repair methods are safe."""
        engine = SelfHealingEngine(Mock())
        
        # These methods exist and are safe
        assert hasattr(engine, '_repair_add_column')
        assert hasattr(engine, '_repair_migrate_type')
        assert hasattr(engine, '_repair_drop_not_null')
        
        # These methods should NOT exist (unsafe)
        assert not hasattr(engine, '_repair_drop_table')
        assert not hasattr(engine, '_repair_drop_column')
        assert not hasattr(engine, '_repair_delete_data')
        assert not hasattr(engine, '_repair_truncate')


class TestRootCauseEnum:
    """Tests for RootCauseType enum."""
    
    def test_all_error_types_defined(self):
        """Verify all error types are defined."""
        expected_types = [
            "UNDEFINED_COLUMN",
            "UNDEFINED_TABLE",
            "DATATYPE_MISMATCH",
            "STRING_DATA_RIGHT_TRUNCATION",
            "NUMERIC_VALUE_OUT_OF_RANGE",
            "NOT_NULL_VIOLATION",
            "FOREIGN_KEY_VIOLATION",
            "UNIQUE_VIOLATION",
            "UNKNOWN",
        ]
        
        for type_name in expected_types:
            assert hasattr(RootCauseType, type_name), f"Missing: {type_name}"
    
    def test_error_types_are_strings(self):
        """Verify error types have string values."""
        for rt in RootCauseType:
            assert isinstance(rt.value, str)


class TestSelfHealingEngineInit:
    """Tests for SelfHealingEngine initialization."""
    
    def test_init_creates_error_samples_dict(self):
        """Test that initialization creates error samples storage."""
        engine = SelfHealingEngine(Mock())
        
        # Should have storage for all error types
        assert len(engine._error_samples) == len(RootCauseType)
    
    def test_init_creates_empty_repairs_list(self):
        """Test that initialization creates empty repairs list."""
        engine = SelfHealingEngine(Mock())
        
        assert engine._repairs_made == []
    
    def test_init_loads_error_patterns(self):
        """Test that initialization loads error patterns from DB."""
        engine = SelfHealingEngine(Mock())
        
        # Patterns should be empty initially
        assert len(engine._error_patterns) == 0
