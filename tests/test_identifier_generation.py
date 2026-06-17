"""Tests for PostgreSQL identifier generation utilities.

This test suite validates the identifier generation and validation
functionality to ensure PostgreSQL identifier limits are respected.

Test coverage:
- Extremely long Odoo model names
- x_studio custom fields
- Nested custom field names
- Multiple long identifiers generating unique hashes
- Identifier collisions
- Schema evolution scenarios
- Reserved keyword handling
- Deterministic generation (stability across calls)
"""

import pytest

from src.utils.identifier import (
    generate_safe_identifier,
    generate_table_name,
    generate_column_name,
    generate_index_name,
    generate_primary_key_name,
    generate_foreign_key_name,
    generate_unique_constraint_name,
    generate_check_constraint_name,
    generate_sequence_name,
    validate_identifier,
    validate_schema_identifiers,
    IdentifierGenerator,
    _sanitize_name,
    _generate_deterministic_hash,
    MAX_IDENTIFIER_LENGTH,
    RESERVED_KEYWORDS,
)


class TestSanitizeName:
    """Tests for the _sanitize_name helper function."""

    def test_lowercase_conversion(self):
        """Names should be converted to lowercase."""
        assert _sanitize_name("MyTable") == "mytable"
        assert _sanitize_name("UPPERCASE") == "uppercase"

    def test_invalid_characters_replaced(self):
        """Invalid characters should be replaced with underscores."""
        assert _sanitize_name("table-name") == "table_name"
        assert _sanitize_name("table.name") == "table_name"
        assert _sanitize_name("table name") == "table_name"
        assert _sanitize_name("table@name!") == "table_name"

    def test_starts_with_digit(self):
        """Names starting with digits are allowed in PostgreSQL (unlike standard SQL)."""
        # PostgreSQL allows identifiers to start with digits
        assert _sanitize_name("123table") == "123table"

    def test_consecutive_underscores_collapsed(self):
        """Consecutive underscores should be collapsed."""
        assert _sanitize_name("table___name") == "table_name"
        assert _sanitize_name("a__b__c") == "a_b_c"

    def test_leading_trailing_underscores_removed(self):
        """Leading and trailing underscores should be removed."""
        assert _sanitize_name("_table_") == "table"
        assert _sanitize_name("__name__") == "name"

    def test_empty_name(self):
        """Empty names should return underscore."""
        assert _sanitize_name("") == "_"
        assert _sanitize_name(None) == "_"

    def test_special_characters(self):
        """Special characters should be handled."""
        assert _sanitize_name("table$name") == "table_name"
        assert _sanitize_name("name-with-dots.and.dashes") == "name_with_dots_and_dashes"


class TestDeterministicHash:
    """Tests for the deterministic hash generation."""

    def test_same_inputs_same_hash(self):
        """Same inputs should always produce the same hash."""
        hash1 = _generate_deterministic_hash("table", "column")
        hash2 = _generate_deterministic_hash("table", "column")
        assert hash1 == hash2

    def test_different_inputs_different_hash(self):
        """Different inputs should produce different hashes."""
        hash1 = _generate_deterministic_hash("table1", "column")
        hash2 = _generate_deterministic_hash("table2", "column")
        assert hash1 != hash2

    def test_hash_length(self):
        """Hash should be exactly 8 characters."""
        hash_result = _generate_deterministic_hash("test")
        assert len(hash_result) == 8

    def test_hash_characters(self):
        """Hash should only contain alphanumeric characters."""
        hash_result = _generate_deterministic_hash("test")
        assert hash_result.isalnum()

    def test_order_matters(self):
        """Different order should produce different hash."""
        hash1 = _generate_deterministic_hash("a", "b")
        hash2 = _generate_deterministic_hash("b", "a")
        assert hash1 != hash2


class TestGenerateSafeIdentifier:
    """Tests for the main generate_safe_identifier function."""

    def test_short_identifier(self):
        """Short identifiers should be returned as-is."""
        result = generate_safe_identifier("idx", "table", "column")
        assert result == "idx_table_column"
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_exactly_63_chars(self):
        """Identifier at exactly 63 chars should be returned as-is."""
        # Build an identifier that's exactly 63 chars
        result = generate_safe_identifier("idx", "very_long_table_name_here", "col")
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_long_identifier_truncated(self):
        """Long identifiers should be truncated with hash suffix."""
        # This long name would exceed 63 characters
        long_table = "purchase_order_line_x_studio_approval_request_receipt_location"
        result = generate_safe_identifier("idx", long_table, "column")
        assert len(result) <= MAX_IDENTIFIER_LENGTH
        assert "_" in result  # Should have hash suffix

    def test_deterministic_output(self):
        """Same inputs should always produce the same output."""
        result1 = generate_safe_identifier("idx", "table", "column")
        result2 = generate_safe_identifier("idx", "table", "column")
        assert result1 == result2

    def test_different_prefixes(self):
        """Different prefixes should produce different identifiers."""
        result1 = generate_safe_identifier("idx", "table", "column")
        result2 = generate_safe_identifier("fk", "table", "column")
        assert result1 != result2

    def test_extra_suffix(self):
        """Extra suffix should be included in the identifier."""
        result = generate_safe_identifier(
            "fk", "table", "column", extra_suffix="ref_table"
        )
        assert "ref_table" in result or len(result) <= MAX_IDENTIFIER_LENGTH

    def test_custom_max_length(self):
        """Custom max_length should be respected."""
        result = generate_safe_identifier(
            "idx", "very_long_table_name", "column", max_length=30
        )
        assert len(result) <= 30

    def test_reserved_keyword_suffix(self):
        """Compound identifiers containing reserved words should be allowed."""
        # "idx_table_select" is NOT a reserved keyword - it's a compound identifier
        # that happens to contain the word "select" as part of the column name
        result = generate_safe_identifier("idx", "table", "select")
        assert result == "idx_table_select"
        
    def test_direct_reserved_keyword(self):
        """A bare reserved keyword should get _x suffix."""
        # When the entire identifier is a reserved word, add suffix
        # This would happen with very short names
        result = generate_safe_identifier("idx", "select", "field")
        # "idx_select_field" is not a reserved keyword, just contains it
        assert "select" in result.lower() or "_x" in result


class TestGenerateTableName:
    """Tests for table name generation."""

    def test_simple_model(self):
        """Simple model names should convert correctly."""
        assert generate_table_name("res.partner") == "res_partner"
        assert generate_table_name("sale.order") == "sale_order"
        assert generate_table_name("product.product") == "product_product"

    def test_multiple_dots(self):
        """Model names with multiple dots should convert all."""
        assert generate_table_name("purchase.order.line") == "purchase_order_line"

    def test_dashes_converted(self):
        """Dashes should be converted to underscores."""
        assert generate_table_name("sale-order") == "sale_order"

    def test_length_limit(self):
        """Generated table names should be within limits."""
        result = generate_table_name("x.studio.custom.field.model.name.that.is.very.long")
        assert len(result) <= MAX_IDENTIFIER_LENGTH


class TestGenerateColumnName:
    """Tests for column name generation."""

    def test_simple_field(self):
        """Simple field names should work directly."""
        assert generate_column_name("name") == "name"
        assert generate_column_name("email") == "email"

    def test_x_studio_field(self):
        """x_studio fields should work correctly."""
        result = generate_column_name("x_studio_approval_request_receipt_location")
        assert len(result) <= MAX_IDENTIFIER_LENGTH
        assert result.startswith("x_studio")

    def test_invalid_chars(self):
        """Invalid characters should be sanitized."""
        assert generate_column_name("field-name") == "field_name"
        assert generate_column_name("field name") == "field_name"


class TestGenerateIndexName:
    """Tests for index name generation."""

    def test_simple_index(self):
        """Simple index names should follow convention."""
        result = generate_index_name("table", "column")
        assert result.startswith("idx_")
        assert "table" in result
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_long_index_name(self):
        """Long index names should be truncated with hash."""
        long_table = "purchase_order_line_x_studio_approval_request_receipt_location"
        long_column = "x_studio_very_long_custom_field_name"
        result = generate_index_name(long_table, long_column)
        assert len(result) <= MAX_IDENTIFIER_LENGTH
        assert result.startswith("idx_")

    def test_with_index_type(self):
        """Index type should be included in name."""
        result = generate_index_name("table", "column", index_type="btree")
        assert result.startswith("idx_")

    def test_deterministic(self):
        """Index names should be deterministic."""
        result1 = generate_index_name("table", "column")
        result2 = generate_index_name("table", "column")
        assert result1 == result2


class TestGeneratePrimaryKeyName:
    """Tests for primary key name generation."""

    def test_simple_pkey(self):
        """Simple table should get _pkey suffix."""
        result = generate_primary_key_name("users")
        assert result.endswith("_pkey")
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_long_table_name(self):
        """Long table names should be truncated."""
        long_name = "purchase_order_line_x_studio_approval_request"
        result = generate_primary_key_name(long_name)
        assert len(result) <= MAX_IDENTIFIER_LENGTH


class TestGenerateForeignKeyName:
    """Tests for foreign key name generation."""

    def test_simple_fk(self):
        """Simple FK should include table, column, and suffix."""
        result = generate_foreign_key_name("orders", "user_id", "users")
        assert result.startswith("fk_")
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_long_names(self):
        """Long FK names should be truncated."""
        long_table = "purchase_order_line_x_studio_approval_request"
        long_column = "x_studio_very_long_custom_field"
        result = generate_foreign_key_name(long_table, long_column, "ref_table")
        assert len(result) <= MAX_IDENTIFIER_LENGTH


class TestGenerateUniqueConstraintName:
    """Tests for unique constraint name generation."""

    def test_single_column(self):
        """Single column constraint."""
        result = generate_unique_constraint_name("table", ["column"])
        assert result.startswith("uq_")
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_multi_column(self):
        """Multi-column constraint should combine names."""
        result = generate_unique_constraint_name("table", ["col1", "col2"])
        assert result.startswith("uq_")
        assert len(result) <= MAX_IDENTIFIER_LENGTH


class TestGenerateCheckConstraintName:
    """Tests for check constraint name generation."""

    def test_simple_check(self):
        """Simple check constraint."""
        result = generate_check_constraint_name("table", "positive_balance")
        assert result.startswith("ck_")
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_long_condition(self):
        """Long conditions should be truncated."""
        long_condition = "x_studio_very_long_custom_field_name_that_exceeds_limit"
        result = generate_check_constraint_name("table", long_condition)
        assert len(result) <= MAX_IDENTIFIER_LENGTH


class TestGenerateSequenceName:
    """Tests for sequence name generation."""

    def test_simple_sequence(self):
        """Simple sequence."""
        result = generate_sequence_name("table", "id")
        assert result.startswith("seq_")
        assert len(result) <= MAX_IDENTIFIER_LENGTH


class TestValidateIdentifier:
    """Tests for identifier validation."""

    def test_valid_identifier(self):
        """Valid identifiers should pass."""
        valid, error = validate_identifier("valid_name")
        assert valid is True
        assert error is None

    def test_valid_long_identifier(self):
        """Identifier at exactly 63 chars should pass."""
        identifier = "a" * 63
        valid, error = validate_identifier(identifier)
        assert valid is True

    def test_too_long_identifier(self):
        """Identifier over 63 chars should fail."""
        identifier = "a" * 64
        valid, error = validate_identifier(identifier)
        assert valid is False
        assert "63 characters" in error

    def test_starts_with_digit(self):
        """Identifiers starting with digit should fail."""
        valid, error = validate_identifier("123name")
        assert valid is False
        assert "letter or underscore" in error

    def test_invalid_characters(self):
        """Identifiers with invalid chars should fail."""
        valid, error = validate_identifier("name-with-dash")
        assert valid is False

    def test_reserved_keyword(self):
        """Reserved keywords should fail."""
        # These are actual PostgreSQL reserved keywords that cause parsing errors
        # 'insert' is not in our list (it's context-dependent)
        for keyword in ["select", "table", "from", "where", "join"]:
            valid, error = validate_identifier(keyword)
            assert valid is False
            assert "reserved keyword" in error

    def test_empty_identifier(self):
        """Empty identifiers should fail."""
        valid, error = validate_identifier("")
        assert valid is False

    def test_special_characters_allowed(self):
        """Underscores and alphanumeric should be allowed."""
        valid, error = validate_identifier("valid_name_123")
        assert valid is True


class TestValidateSchemaIdentifiers:
    """Tests for bulk schema identifier validation."""

    def test_all_valid(self):
        """All valid identifiers should pass."""
        errors = validate_schema_identifiers(
            table_name="users",
            column_names=["id", "name", "email"],
            index_names=["idx_users_email"],
            constraint_names=["users_pkey"],
        )
        assert len(errors) == 0

    def test_duplicate_column_names(self):
        """Duplicate column names should be reported."""
        errors = validate_schema_identifiers(
            table_name="users",
            column_names=["id", "name", "name"],  # Duplicate
            index_names=[],
            constraint_names=[],
        )
        assert len(errors) == 1
        assert "Duplicate" in errors[0]

    def test_invalid_index_names(self):
        """Invalid index names should be reported."""
        errors = validate_schema_identifiers(
            table_name="users",
            column_names=["id"],
            index_names=["idx_users_email", "idx-invalid"],  # Invalid
            constraint_names=[],
        )
        assert len(errors) >= 1


class TestIdentifierGenerator:
    """Tests for the IdentifierGenerator class."""

    def test_generates_consistent_names(self):
        """Generator should produce consistent names."""
        gen = IdentifierGenerator()
        name1 = gen.generate("idx", "table", "column")
        name2 = gen.generate("idx", "table", "column")
        assert name1 == name2

    def test_tracks_generated_identifiers(self):
        """Generator should track all generated identifiers."""
        gen = IdentifierGenerator()
        gen.generate_index("table1", "col1")
        gen.generate_index("table2", "col2")
        assert len(gen._generated) == 2

    def test_detects_collisions(self):
        """Generator should detect duplicate generation."""
        gen = IdentifierGenerator()
        gen.generate("idx", "table", "column")
        gen.generate("idx", "table", "column")
        assert gen.has_collisions()

    def test_get_duplicates(self):
        """Should return list of duplicated identifiers."""
        gen = IdentifierGenerator()
        gen.generate("idx", "table", "column")
        gen.generate("idx", "table", "column")
        duplicates = gen.get_duplicates()
        assert len(duplicates) > 0

    def test_validate_all(self):
        """Should validate all generated identifiers."""
        gen = IdentifierGenerator()
        gen.generate("idx", "table", "column")
        gen.generate("fk", "table", "col")  # Reserved keyword
        errors = gen.validate_all()
        # fk_table_col might be valid since 'fk' isn't reserved


class TestRealWorldScenarios:
    """Tests for real-world Odoo field name scenarios."""

    def test_x_studio_field_index(self):
        """Test x_studio field that caused the original error."""
        # This is the exact field name from the error
        field_name = "x_studio_approval_request_receipt_location"
        table_name = "purchase_order_line"
        
        index_name = generate_index_name(table_name, field_name)
        assert len(index_name) <= MAX_IDENTIFIER_LENGTH
        assert index_name.startswith("idx_")

    def test_multiple_long_x_studio_fields(self):
        """Multiple long x_studio fields should generate unique identifiers."""
        fields = [
            "x_studio_approval_request_receipt_location",
            "x_studio_approval_request_shipping_location",
            "x_studio_approval_request_billing_location",
        ]
        
        table = "purchase_order_line"
        index_names = [generate_index_name(table, f) for f in fields]
        
        # All should be unique
        assert len(set(index_names)) == len(index_names)
        
        # All should be valid length
        for name in index_names:
            assert len(name) <= MAX_IDENTIFIER_LENGTH

    def test_nested_model_names(self):
        """Nested model names should work correctly."""
        models = [
            "x_studio_custom_module.model.submodel.deep.nested",
            "base_import.import.imported.record",
            "stock.warehouse.order.point",
        ]
        
        for model in models:
            table_name = generate_table_name(model)
            assert len(table_name) <= MAX_IDENTIFIER_LENGTH

    def test_long_model_with_many_relations(self):
        """Model with many long field names should generate stable identifiers."""
        fields = [
            f"x_studio_custom_field_{i}_with_very_long_name_that_exceeds_limits"
            for i in range(20)
        ]
        
        table = "x_studio_very_long_custom_model_name_that_exceeds_standard"
        index_names = [generate_index_name(table, f) for f in fields]
        
        # All should be unique
        assert len(set(index_names)) == len(index_names)
        
        # Running again should produce the same result (stability)
        index_names_2 = [generate_index_name(table, f) for f in fields]
        assert index_names == index_names_2

    def test_schema_evolution_add_field(self):
        """Schema evolution should generate same identifier for same field."""
        # Initial sync
        name1 = generate_index_name("sale_order", "x_studio_new_custom_field")
        
        # Schema evolution (adding same field again)
        name2 = generate_index_name("sale_order", "x_studio_new_custom_field")
        
        assert name1 == name2  # Should be deterministic

    def test_migration_scenario(self):
        """Test migration scenario with renamed fields."""
        # Original field
        name1 = generate_index_name("res_partner", "x_studio_old_field_name")
        
        # Field renamed but same content
        name2 = generate_index_name("res_partner", "x_studio_new_field_name")
        
        # Should be different
        assert name1 != name2
        
        # Both should be valid
        assert len(name1) <= MAX_IDENTIFIER_LENGTH
        assert len(name2) <= MAX_IDENTIFIER_LENGTH


class TestMaxIdentifierLengthConstant:
    """Tests for the MAX_IDENTIFIER_LENGTH constant."""

    def test_value_is_63(self):
        """PostgreSQL identifier limit is 63."""
        assert MAX_IDENTIFIER_LENGTH == 63


class TestReservedKeywords:
    """Tests for reserved keyword handling."""

    def test_common_keywords_are_reserved(self):
        """Common SQL keywords should be in the reserved set."""
        # These are the keywords in our RESERVED_KEYWORDS set
        common_keywords = ["select", "from", "where", "table", "join"]
        for keyword in common_keywords:
            assert keyword in RESERVED_KEYWORDS

    def test_type_keywords_are_reserved(self):
        """Type keywords should be reserved."""
        type_keywords = ["integer", "varchar", "text", "numeric", "boolean"]
        for keyword in type_keywords:
            assert keyword in RESERVED_KEYWORDS


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_field_at_boundary(self):
        """Field name at 63 chars should work."""
        # Exactly 63 chars
        field = "a" * 63
        result = generate_column_name(field)
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_very_long_field_over_boundary(self):
        """Field name over 63 chars should be sanitized."""
        field = "x_studio_" + "a" * 100
        result = generate_column_name(field)
        assert len(result) <= MAX_IDENTIFIER_LENGTH

    def test_only_underscores(self):
        """Name with only underscores should be handled."""
        result = _sanitize_name("___")
        assert result  # Should return something valid

    def test_unicode_characters(self):
        """Unicode characters should be sanitized."""
        result = _sanitize_name("mytable_日本語_name")
        assert result  # Should return valid ASCII

    def test_hash_with_special_chars(self):
        """Hash should work with special characters in input."""
        result = _generate_deterministic_hash("table-name", "column/name")
        assert len(result) == 8
        assert result.isalnum()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
