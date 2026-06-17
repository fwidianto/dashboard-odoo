#!/usr/bin/env python
"""
Demo: Automatic Odoo Schema Discovery and Migration

This demo shows the complete workflow for automatic schema discovery:
1. Type mapping configuration (updated to NUMERIC(30,10), TEXT, etc.)
2. Schema discovery from Odoo metadata
3. Schema cache with hash comparison
4. Validation pipeline
5. Migration logic

Run with: python demo_schema_discovery.py
"""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.config_loader import ConfigLoader


def demo_type_mapping():
    """Demonstrate the updated type mapping."""
    print("=" * 70)
    print("PHASE 2: POSTGRESQL TYPE MAPPING")
    print("=" * 70)
    
    loader = ConfigLoader()
    
    print("\nOdoo Field Types -> PostgreSQL Types:")
    print("-" * 50)
    
    type_mapping = loader.ODOO_TYPE_TO_POSTGRES
    
    for odoo_type, pg_type in sorted(type_mapping.items()):
        if odoo_type != 'SKIP':
            print(f"  {odoo_type:<20} -> {pg_type}")
    
    print("\nKey Changes from Old Mapping:")
    print("  - INTEGER -> BIGINT (was 'INTEGER', now 'BIGINT')")
    print("  - NUMERIC(20,4) -> NUMERIC(30,10) (handles 17762630700.00)")
    print("  - VARCHAR(255) -> TEXT (Odoo strings exceed 255)")
    print("  - one2many/many2many: SKIP -> JSONB (stored as JSON)")


def demo_metadata_discovery():
    """Demonstrate metadata discovery structure."""
    print("\n" + "=" * 70)
    print("PHASE 1: ODOO METADATA DISCOVERY")
    print("=" * 70)
    
    from src.odoo.metadata_discovery import (
        OdooField,
        OdooModelMetadata,
        OdooMetadataDiscovery,
        SchemaCache,
        generate_field_configs,
    )
    
    print("\nDataclass Structure:")
    print("-" * 50)
    
    # Show OdooField structure
    field = OdooField(
        name="list_price",
        field_type="monetary",
        string="Sale Price",
        required=False,
        store=True,
        index=False,
        relation="product.pricelist",
    )
    print(f"OdooField: {json.dumps(field.to_dict(), indent=2)}")
    
    # Show metadata structure
    metadata = OdooModelMetadata(model="product.template", table="product_template")
    metadata.fields["list_price"] = field
    metadata.metadata_hash = metadata.compute_hash()
    
    print(f"\nOdooModelMetadata:")
    print(f"  model: {metadata.model}")
    print(f"  table: {metadata.table}")
    print(f"  stored_fields: {metadata.get_field_count()}")
    print(f"  metadata_hash: {metadata.metadata_hash}")
    
    # Show field config generation
    print("\nGenerated Field Configs:")
    print("-" * 50)
    
    configs = generate_field_configs(metadata)
    for cfg in configs:
        print(f"  {cfg['odoo_field']}: {cfg['postgres_type']}")


def demo_schema_cache():
    """Demonstrate schema caching."""
    print("\n" + "=" * 70)
    print("PHASE 4: SCHEMA CACHE")
    print("=" * 70)
    
    from src.odoo.metadata_discovery import SchemaCache
    import tempfile
    
    # Create temp cache file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_cache = f.name
    
    try:
        cache = SchemaCache(cache_file=temp_cache)
        
        # Simulate cache entry
        from src.odoo.metadata_discovery import OdooModelMetadata, OdooField
        
        metadata = OdooModelMetadata(model="product.template", table="product_template")
        metadata.fields["name"] = OdooField(
            name="name",
            field_type="char",
            string="Name",
            store=True,
        )
        metadata.metadata_hash = metadata.compute_hash()
        
        cache.set("product.template", metadata)
        cache.save()
        
        print("\nCache Entry:")
        print("-" * 50)
        print(f"  File: {temp_cache}")
        
        cache.load()
        entry = cache.get("product.template")
        print(f"  model: {entry['model']}")
        print(f"  table: {entry['table']}")
        print(f"  field_count: {entry['field_count']}")
        print(f"  metadata_hash: {entry['metadata_hash']}")
        
        # Check if update needed
        same_hash = not cache.needs_update("product.template", entry['metadata_hash'])
        diff_hash = cache.needs_update("product.template", "different_hash")
        
        print(f"\n  needs_update (same hash): {diff_hash}")
        print(f"  needs_update (diff hash): {same_hash}")
        
    finally:
        os.unlink(temp_cache)


def demo_migration_logic():
    """Demonstrate migration logic."""
    print("\n" + "=" * 70)
    print("PHASE 3: AUTOMATIC SCHEMA MIGRATION")
    print("=" * 70)
    
    print("\nMigration Rules:")
    print("-" * 50)
    
    migrations = [
        ("VARCHAR(255)", "TEXT", "Migrate"),
        ("VARCHAR(100)", "TEXT", "Migrate"),
        ("NUMERIC(12,2)", "NUMERIC(30,10)", "Migrate"),
        ("NUMERIC(14,2)", "NUMERIC(30,10)", "Migrate"),
        ("NUMERIC(20,4)", "NUMERIC(30,10)", "Migrate"),
        ("NUMERIC(30,10)", "NUMERIC(30,10)", "No change"),
        ("INTEGER", "BIGINT", "Implicit cast"),
        ("TEXT", "TEXT", "No change"),
    ]
    
    for old, new, action in migrations:
        print(f"  {old:<20} -> {new:<20} : {action}")


def demo_identifier_naming():
    """Demonstrate index naming."""
    print("\n" + "=" * 70)
    print("PHASE 6: INDEX NAMING (Max 63 chars)")
    print("=" * 70)
    
    from src.utils.identifier import generate_index_name, validate_identifier
    
    test_cases = [
        ("purchase_order_line", "x_studio_approval_request_receipt_location"),
        ("product_template", "name"),
        ("sale_order", "x_studio_custom_field_with_very_long_name_that_exceeds_limit"),
    ]
    
    print("\nIndex Name Generation:")
    print("-" * 50)
    
    for table, column in test_cases:
        index_name = generate_index_name(table, column)
        valid, error = validate_identifier(index_name)
        status = "✓" if valid else "✗"
        print(f"  {table}.{column}")
        print(f"    -> {index_name}")
        print(f"    -> {len(index_name)} chars {status}")
        if not valid:
            print(f"    -> Error: {error}")


def demo_validation_pipeline():
    """Demonstrate validation pipeline structure."""
    print("\n" + "=" * 70)
    print("PHASE 10: VALIDATION PIPELINE")
    print("=" * 70)
    
    from src.odoo.schema_validator import ValidationResult, SchemaValidationReport
    
    print("\nValidation Phases:")
    print("-" * 50)
    
    phases = [
        ("SchemaDiscovery", "Discover Odoo metadata using fields_get()"),
        ("SchemaValidation", "Validate discovered schema"),
        ("SchemaMigration", "Apply necessary migrations"),
        ("IndexValidation", "Ensure indexes are correct"),
        ("MetadataSnapshot", "Record schema state to sync_schema_snapshot"),
    ]
    
    for phase, description in phases:
        print(f"  {phase}: {description}")
    
    print("\nValidation Report Structure:")
    print("-" * 50)
    
    report = SchemaValidationReport()
    report.models_discovered = 12
    report.tables_created = 12
    report.columns_added = 234
    report.columns_migrated = 56
    
    summary = report.get_summary()
    print(f"  is_valid: {summary['valid']}")
    print(f"  models_discovered: {summary['models_discovered']}")
    print(f"  tables_created: {summary['tables_created']}")
    print(f"  columns_added: {summary['columns_added']}")
    print(f"  columns_migrated: {summary['columns_migrated']}")


def demo_sync_health_report():
    """Demonstrate sync health report generation."""
    print("\n" + "=" * 70)
    print("PHASE 8: SYNC HEALTH REPORT")
    print("=" * 70)
    
    from src.odoo.schema_validator import SyncHealthReporter
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = SyncHealthReporter(reports_dir=tmpdir)
        
        # Sample model results
        model_results = [
            {
                "model": "product.template",
                "processed": 17536,
                "success": 17000,
                "failed": 536,
                "errors_by_category": {
                    "SCHEMA_ERROR": 500,
                    "NULL_CONSTRAINT": 20,
                    "NUMERIC_OVERFLOW": 10,
                    "DATA_TOO_LONG": 6,
                },
            },
            {
                "model": "sale.order",
                "processed": 1192,
                "success": 1192,
                "failed": 0,
                "errors_by_category": {},
            },
            {
                "model": "stock.move",
                "processed": 293444,
                "success": 293442,
                "failed": 2,
                "errors_by_category": {
                    "SCHEMA_ERROR": 2,
                },
            },
        ]
        
        # Sample error samples
        error_samples = [
            {
                "model": "product.template",
                "record_id": 12345,
                "field": "list_price",
                "value": 10865523596.49,
                "error_category": "NUMERIC_OVERFLOW",
            },
        ]
        
        paths = reporter.generate_report(model_results, error_samples)
        
        print("\nGenerated Reports:")
        print("-" * 50)
        for key, path in paths.items():
            print(f"  {key}: {path}")
        
        # Show content
        for key, path in paths.items():
            if path.endswith('.txt'):
                print(f"\n{key} content:")
                print("-" * 50)
                with open(path, 'r') as f:
                    print(f.read())


def main():
    """Run all demos."""
    print("=" * 70)
    print("AUTO-SCHEMA DISCOVERY DEMONSTRATION")
    print("=" * 70)
    print()
    print("This demo shows the complete workflow for automatic Odoo schema")
    print("discovery and PostgreSQL schema migration.")
    print()
    
    demo_type_mapping()
    demo_metadata_discovery()
    demo_schema_cache()
    demo_migration_logic()
    demo_identifier_naming()
    demo_validation_pipeline()
    demo_sync_health_report()
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    
    print("\nSummary of Changes:")
    print("-" * 50)
    print("""
Phase 1 - Metadata Discovery:
  ✓ OdooMetadataDiscovery class
  ✓ Uses fields_get() and ir.model.fields
  ✓ Only syncs store=True fields

Phase 2 - Type Mapping:
  ✓ NUMERIC(30,10) for all numeric types
  ✓ TEXT for all text types (no VARCHAR)
  ✓ JSONB for one2many/many2many
  ✓ BIGINT for all integers

Phase 3 - Automatic Migration:
  ✓ VARCHAR -> TEXT
  ✓ NUMERIC -> NUMERIC(30,10)
  ✓ Auto-add new columns
  ✓ Auto-create indexes

Phase 4 - Schema Cache:
  ✓ SchemaCache class
  ✓ Hash-based change detection
  ✓ Cache file: schema_cache.json

Phase 5 - Metadata Snapshot:
  ✓ sync_schema_snapshot table
  ✓ Records all field metadata
  ✓ Tracks schema changes over time

Phase 6 - Index Naming:
  ✓ Deterministic hash suffixes
  ✓ Max 63 characters guaranteed
  ✓ Uses IdentifierGenerator

Phase 7-9 - Error Reporting:
  ✓ Error classification implemented
  ✓ Health reports implemented
  ✓ Error sampling implemented

Phase 10 - Validation Pipeline:
  ✓ SchemaValidationPipeline class
  ✓ 5-phase validation at startup
  ✓ SyncHealthReporter class
""")


if __name__ == "__main__":
    main()
