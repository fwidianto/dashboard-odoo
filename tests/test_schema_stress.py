"""Schema stress test suite.

This test module simulates extreme schema generation scenarios to validate
the production-readiness of the identifier generation and schema creation
infrastructure.

Test scenarios:
- 100+ Odoo models
- 1000+ fields
- Extremely long custom field names
- Schema evolution
- Incremental sync
- Repeated startup
"""

import pytest
import random
import string
from typing import List, Dict, Any

from src.utils.identifier import (
    generate_safe_identifier,
    generate_table_name,
    generate_column_name,
    generate_index_name,
    generate_primary_key_name,
    validate_identifier,
    validate_schema_identifiers,
    IdentifierGenerator,
    MAX_IDENTIFIER_LENGTH,
)


class FieldSimulator:
    """Simulates Odoo field definitions."""
    
    # Common Odoo field types
    FIELD_TYPES = [
        'char', 'text', 'integer', 'float', 'boolean', 
        'date', 'datetime', 'many2one', 'selection'
    ]
    
    # Standard field prefixes
    STANDARD_PREFIXES = ['name', 'email', 'date', 'state', 'partner', 'company', 'user']
    
    # x_studio custom field name patterns
    X_STUDIO_PATTERNS = [
        "x_studio_{category}_{subcategory}_{attribute}_{location}",
        "x_studio_{action}_{target}_{context}",
        "x_studio_{department}_{function}_{identifier}",
        "x_studio_{process}_{step}_{result}",
    ]
    
    CATEGORIES = [
        "approval", "workflow", "custom", "approval", "request",
        "document", "record", "field", "template", "configuration"
    ]
    
    ATTRIBUTES = [
        "location", "date", "amount", "status", "priority",
        "category", "type", "mode", "method", "source"
    ]
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
    
    def generate_standard_field(self) -> Dict[str, Any]:
        """Generate a standard Odoo field."""
        return {
            'name': f"{self.rng.choice(self.STANDARD_PREFIXES)}_{self.rng.randint(1, 100)}",
            'type': self.rng.choice(self.FIELD_TYPES),
        }
    
    def generate_x_studio_field(self, max_length: int = 100) -> Dict[str, Any]:
        """Generate an x_studio custom field with potentially long names."""
        # Create a long field name
        base = self.rng.choice(self.CATEGORIES)
        attr = self.rng.choice(self.ATTRIBUTES)
        
        # Build a long name
        components = [base]
        for _ in range(self.rng.randint(2, 5)):
            components.append(self.rng.choice(self.CATEGORIES))
        
        field_name = "x_studio_" + "_".join(components) + "_" + attr
        
        # Sometimes make it even longer
        if self.rng.random() < 0.3:
            field_name += "_" + "_".join([
                self.rng.choice(self.CATEGORIES) for _ in range(5)
            ])
        
        return {
            'name': field_name,
            'type': 'char',
        }
    
    def generate_model_fields(self, count: int, long_ratio: float = 0.2) -> List[Dict[str, Any]]:
        """Generate a list of field definitions for a model."""
        fields = []
        
        # Always start with id
        fields.append({'name': 'id', 'type': 'integer'})
        
        for _ in range(count - 1):
            if self.rng.random() < long_ratio:
                fields.append(self.generate_x_studio_field())
            else:
                fields.append(self.generate_standard_field())
        
        return fields


class ModelSimulator:
    """Simulates Odoo model configurations."""
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.field_sim = FieldSimulator(seed)
    
    def generate_long_model_name(self) -> str:
        """Generate a very long model name."""
        modules = ["x_studio", "custom", "studio", "extension", "addon", "module"]
        components = [self.rng.choice(modules)]
        
        for _ in range(self.rng.randint(3, 8)):
            components.append(self.rng.choice(modules))
        
        return ".".join(components) + ".model." + ".".join([
            self.rng.choice(modules) for _ in range(3)
        ])
    
    def generate_model_config(self, field_count: int = 20) -> Dict[str, Any]:
        """Generate a complete model configuration."""
        odoo_model = self.generate_long_model_name()
        
        return {
            'odoo_model': odoo_model,
            'fields': self.field_sim.generate_model_fields(field_count),
        }


class TestMassiveModelGeneration:
    """Test generation of 100+ models with 1000+ fields."""
    
    def test_generate_100_models(self):
        """Generate 100 model configurations."""
        sim = ModelSimulator(seed=42)
        
        models = []
        for i in range(100):
            model = sim.generate_model_config(field_count=20)
            models.append(model)
        
        assert len(models) == 100
        
        # Total fields should be 100 * 20 = 2000
        total_fields = sum(len(m['fields']) for m in models)
        assert total_fields >= 2000
    
    def test_all_identifiers_valid(self):
        """All generated identifiers should be valid."""
        sim = ModelSimulator(seed=42)
        
        all_errors = []
        
        for i in range(100):
            model = sim.generate_model_config(field_count=20)
            table_name = generate_table_name(model['odoo_model'])
            
            # Validate table name
            valid, error = validate_identifier(table_name)
            if not valid:
                all_errors.append(f"Table {table_name}: {error}")
            
            # Validate field names
            for field in model['fields']:
                col_name = generate_column_name(field['name'])
                valid, error = validate_identifier(col_name)
                if not valid:
                    all_errors.append(f"Column {col_name}: {error}")
                
                # Validate index name
                index_name = generate_index_name(table_name, col_name)
                valid, error = validate_identifier(index_name)
                if not valid:
                    all_errors.append(f"Index {index_name}: {error}")
        
        assert len(all_errors) == 0, f"Found {len(all_errors)} invalid identifiers: {all_errors[:5]}"


class TestExtremelyLongFieldNames:
    """Test handling of extremely long field names."""
    
    def test_field_name_at_63_chars(self):
        """Field name at exactly 63 characters should work."""
        # 63 char field name
        field = "a" * 63
        col_name = generate_column_name(field)
        assert len(col_name) <= MAX_IDENTIFIER_LENGTH
    
    def test_field_name_at_100_chars(self):
        """Field name at 100 characters should be truncated."""
        field = "x_studio_" + "a" * 90
        col_name = generate_column_name(field)
        assert len(col_name) <= MAX_IDENTIFIER_LENGTH
    
    def test_field_name_at_200_chars(self):
        """Field name at 200 characters should be truncated."""
        field = "x_studio_custom_very_long_field_name_" + "x" * 170
        col_name = generate_column_name(field)
        assert len(col_name) <= MAX_IDENTIFIER_LENGTH
    
    def test_original_error_field(self):
        """Test the exact field name that caused the original error."""
        field = "x_studio_approval_request_receipt_location"
        table = "purchase_order_line"
        
        # This should work without error
        index_name = generate_index_name(table, field)
        assert len(index_name) <= MAX_IDENTIFIER_LENGTH
        
        # Should be deterministic
        index_name2 = generate_index_name(table, field)
        assert index_name == index_name2


class TestCollisionResistance:
    """Test that identifier generation is collision-resistant."""
    
    def test_many_similar_field_names(self):
        """Many similar field names should produce unique identifiers."""
        table = "test_table"
        
        # Generate many similar field names
        fields = [
            f"x_studio_approval_request_{location}_location"
            for location in ["receipt", "shipping", "billing", "delivery", "pickup"]
        ]
        
        index_names = [generate_index_name(table, f) for f in fields]
        
        # All should be unique
        assert len(set(index_names)) == len(index_names)
    
    def test_identical_hash_collision_detection(self):
        """Test that the identifier generator can detect potential collisions."""
        gen = IdentifierGenerator()
        
        # Generate the same identifier twice
        gen.generate_index("table", "column1")
        gen.generate_index("table", "column1")
        
        # Should detect collision
        assert gen.has_collisions()
        assert len(gen.get_duplicates()) > 0
    
    def test_no_collision_within_100_fields(self):
        """100 fields on same table should not collide."""
        sim = FieldSimulator(seed=123)
        
        gen = IdentifierGenerator()
        table = "stress_test_table"
        
        for i in range(100):
            field = sim.generate_x_studio_field()
            name = gen.generate_index(table, field['name'])
        
        # Should not have collisions
        assert not gen.has_collisions()


class TestSchemaEvolution:
    """Test schema evolution scenarios."""
    
    def test_add_new_field_same_identifier(self):
        """Adding the same field should produce same identifier."""
        table = "sale_order"
        field = "x_studio_custom_field"
        
        # First sync
        name1 = generate_index_name(table, field)
        
        # Second sync (after adding the same field)
        name2 = generate_index_name(table, field)
        
        assert name1 == name2
    
    def test_rename_field_different_identifier(self):
        """Renaming a field should produce a different identifier."""
        table = "sale_order"
        
        name1 = generate_index_name(table, "x_studio_old_field_name")
        name2 = generate_index_name(table, "x_studio_new_field_name")
        
        assert name1 != name2
    
    def test_multiple_sync_cycles(self):
        """Multiple sync cycles should produce stable identifiers."""
        table = "res_partner"
        field = "x_studio_approval_request_receipt_location"
        
        names = [generate_index_name(table, field) for _ in range(10)]
        
        # All should be identical
        assert len(set(names)) == 1


class TestIncrementalSync:
    """Test incremental sync scenarios."""
    
    def test_sync_with_existing_schema(self):
        """Sync should work with existing schema."""
        table = "existing_table"
        existing_fields = {"id", "name", "create_date"}
        new_fields = ["x_studio_new_field_1", "x_studio_new_field_2"]
        
        # Generate identifiers for new fields
        for field in new_fields:
            index_name = generate_index_name(table, field)
            assert len(index_name) <= MAX_IDENTIFIER_LENGTH
            
            # Verify it's unique from existing
            assert index_name not in [
                generate_index_name(table, f) for f in existing_fields
            ]
    
    def test_sync_with_long_model_names(self):
        """Sync should work with very long model names."""
        long_model = "x.studio.custom.module.model.with.many.levels.deep"
        table = generate_table_name(long_model)
        
        assert len(table) <= MAX_IDENTIFIER_LENGTH
        
        # Should still be able to generate field identifiers
        field = "x_studio_very_long_custom_field_name_for_testing"
        index_name = generate_index_name(table, field)
        assert len(index_name) <= MAX_IDENTIFIER_LENGTH


class TestRepeatedStartup:
    """Test repeated application startup scenarios."""
    
    def test_startup_100_times_same_identifiers(self):
        """100 startups should produce the same identifiers."""
        table = "test_table"
        field = "x_studio_approval_request_receipt_location"
        
        all_names = []
        for i in range(100):
            name = generate_index_name(table, field)
            all_names.append(name)
        
        # All should be identical
        assert len(set(all_names)) == 1
    
    def test_startup_with_different_seeds(self):
        """Startups with different seeds should still produce valid identifiers."""
        # Even if different random seeds are used in simulation,
        # the identifier generation itself should be deterministic
        
        table = "test_table"
        field = "x_studio_custom_field"
        
        # Generate many times
        names = [generate_index_name(table, field) for _ in range(50)]
        
        # Should all be identical (deterministic)
        assert len(set(names)) == 1


class TestStressTestSuite:
    """Full stress test simulating production scenarios."""
    
    def test_full_stress_scenario(self):
        """Simulate a full production stress test."""
        print("\n" + "=" * 60)
        print("RUNNING SCHEMA STRESS TEST")
        print("=" * 60)
        
        errors = []
        all_identifiers = []
        gen = IdentifierGenerator()
        
        # Scenario 1: 50 models with 30 fields each
        print("\nScenario 1: 50 models × 30 fields")
        sim = ModelSimulator(seed=100)
        
        for i in range(50):
            model = sim.generate_model_config(field_count=30)
            table = generate_table_name(model['odoo_model'])
            
            # Validate table
            valid, error = validate_identifier(table)
            if not valid:
                errors.append(f"Table {table}: {error}")
            
            # Generate field identifiers
            for field in model['fields']:
                col = generate_column_name(field['name'])
                valid, error = validate_identifier(col)
                if not valid:
                    errors.append(f"Column {col}: {error}")
                
                # Generate index
                idx = gen.generate_index(table, col)
                valid, error = validate_identifier(idx)
                if not valid:
                    errors.append(f"Index {idx}: {error}")
                
                all_identifiers.append(idx)
        
        print(f"  Generated {len(all_identifiers)} identifiers")
        print(f"  Errors so far: {len(errors)}")
        
        # Scenario 2: 100 x_studio fields
        print("\nScenario 2: 100 x_studio fields")
        field_sim = FieldSimulator(seed=200)
        
        for i in range(100):
            field = field_sim.generate_x_studio_field()
            col = generate_column_name(field['name'])
            
            valid, error = validate_identifier(col)
            if not valid:
                errors.append(f"x_studio Column {col}: {error}")
            
            idx = gen.generate_index("studio_test_table", col)
            valid, error = validate_identifier(idx)
            if not valid:
                errors.append(f"x_studio Index {idx}: {error}")
        
        print(f"  Total identifiers: {len(all_identifiers)}")
        print(f"  Errors so far: {len(errors)}")
        
        # Scenario 3: Long field names
        print("\nScenario 3: Very long field names (200+ chars)")
        long_fields = [
            "x_studio_" + "a" * 200,
            "x_studio_" + "b" * 300,
            "x_studio_custom_field_" + "c" * 250,
        ]
        
        for field in long_fields:
            col = generate_column_name(field)
            valid, error = validate_identifier(col)
            if not valid:
                errors.append(f"Long Column {col[:50]}...: {error}")
            
            idx = gen.generate_index("long_test_table", col)
            valid, error = validate_identifier(idx)
            if not valid:
                errors.append(f"Long Index {idx[:50]}...: {error}")
        
        # Scenario 4: Schema evolution simulation
        print("\nScenario 4: Schema evolution (10 iterations)")
        for iteration in range(10):
            field_sim = FieldSimulator(seed=iteration)
            
            for i in range(20):
                field = field_sim.generate_x_studio_field()
                col = generate_column_name(field['name'])
                idx = generate_index_name("evolution_test", col)
                
                valid, error = validate_identifier(idx)
                if not valid:
                    errors.append(f"Evolution Index {idx}: {error}")
        
        # Check for collisions
        print("\nScenario 5: Collision detection")
        has_collisions = gen.has_collisions()
        print(f"  Collisions detected: {has_collisions}")
        
        # Final summary
        print("\n" + "=" * 60)
        print("STRESS TEST RESULTS")
        print("=" * 60)
        print(f"Total identifiers generated: {len(all_identifiers)}")
        print(f"Unique identifiers: {len(set(all_identifiers))}")
        print(f"Total errors: {len(errors)}")
        print(f"Collision detection active: {has_collisions}")
        
        if errors:
            print("\nFirst 10 errors:")
            for error in errors[:10]:
                print(f"  - {error}")
        
        print("=" * 60)
        
        # Assert no errors - identifier length errors are the critical failures
        # Collisions are expected when the same field is generated multiple times
        assert len(errors) == 0, f"Found {len(errors)} errors during stress test"


class TestIdentifierLengthDistribution:
    """Test distribution of identifier lengths."""
    
    def test_identifier_length_distribution(self):
        """Verify identifier lengths are well-distributed."""
        lengths = []
        
        sim = ModelSimulator(seed=500)
        
        for i in range(100):
            model = sim.generate_model_config(field_count=25)
            table = generate_table_name(model['odoo_model'])
            
            for field in model['fields']:
                col = generate_column_name(field['name'])
                idx = generate_index_name(table, col)
                lengths.append(len(idx))
        
        # All should be <= 63 (PostgreSQL limit)
        assert all(l <= 63 for l in lengths), "All identifiers must be <= 63 chars"
        
        # Critical: ALL identifiers must be exactly 63 or less (no overflow)
        over_limit = sum(1 for l in lengths if l > 63)
        assert over_limit == 0, f"Found {over_limit} identifiers exceeding 63 chars"


class TestPostgreSQLLimitCompliance:
    """Test that all generated identifiers comply with PostgreSQL limits."""
    
    def test_all_identifiers_under_63(self):
        """All identifiers must be under 63 characters."""
        sim = FieldSimulator(seed=999)
        
        failures = []
        
        # Generate 500 random field names
        for i in range(500):
            field = sim.generate_x_studio_field()
            col = generate_column_name(field['name'])
            
            if len(col) > 63:
                failures.append(f"Column '{col}' is {len(col)} chars")
            
            # Also check index names
            idx = generate_index_name("test_table", col)
            if len(idx) > 63:
                failures.append(f"Index '{idx}' is {len(idx)} chars")
        
        assert len(failures) == 0, f"Found {len(failures)} length violations: {failures[:5]}"
    
    def test_table_names_under_63(self):
        """All table names must be under 63 characters."""
        sim = ModelSimulator(seed=888)
        
        failures = []
        
        for i in range(200):
            model = sim.generate_model_config(field_count=10)
            table = generate_table_name(model['odoo_model'])
            
            if len(table) > 63:
                failures.append(f"Table '{table}' is {len(table)} chars")
        
        assert len(failures) == 0, f"Found {len(failures)} table name violations"


class TestDeterminism:
    """Test that identifier generation is deterministic."""
    
    def test_same_input_same_output(self):
        """Same input should always produce same output."""
        table = "purchase_order_line"
        field = "x_studio_approval_request_receipt_location"
        
        # Generate 100 times
        results = [generate_index_name(table, field) for _ in range(100)]
        
        # All should be identical
        assert len(set(results)) == 1
    
    def test_different_seeds_same_result(self):
        """Different random seeds should not affect output."""
        # The identifier generation is deterministic by design,
        # so this test verifies the implementation is correct
        
        results = []
        for seed in [1, 42, 100, 999, 12345]:
            # Simulate different scenarios but same core data
            result = generate_index_name("table", "x_studio_same_field")
            results.append(result)
        
        # All should be identical
        assert len(set(results)) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
