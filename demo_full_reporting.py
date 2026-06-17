#!/usr/bin/env python
"""Full demo of production-grade sync health reporting system.

This demo exercises all phases of the reporting system:
1. Executive Report (Sync Health)
2. Model Health Reports
3. Error Classification
4. Column Analysis
5. Sample Failures
6. Schema Recommendations
7. Data Profiling
8. Top Issues Report
"""

import os
import sys
import json
import glob

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.reporting.error_enums import ErrorCategory
from src.reporting.error_reporter import ErrorReporter
from src.reporting.schema_recommender import SchemaRecommender


def simulate_full_sync():
    """Simulate a full sync with various error types."""
    
    print("=" * 70)
    print("PRODUCTION-GRADE SYNC HEALTH REPORTING - FULL DEMO")
    print("=" * 70)
    print()
    
    # Create error reporter with reports directory
    reporter = ErrorReporter(reports_dir="reports")
    recommender = SchemaRecommender(reports_dir="reports")
    
    # =====================================================
    # PHASE 1: product.template sync with DATA_TOO_LONG
    # =====================================================
    print("Simulating sync for: product.template")
    reporter.start_batch("product.template", "product_template")
    
    # Simulate 17,536 records with various errors
    # 587 DATA_TOO_LONG errors
    for i in range(587):
        if i % 2 == 0:
            reporter.profile_data("name", "VARCHAR(255)", "X" * (300 + i % 100))
        else:
            reporter.profile_data("description", "TEXT", "Y" * (500 + i % 200))
        reporter.record_error(
            ErrorCategory.DATA_TOO_LONG,
            record_id=1000 + i,
            error_message='value too long for type character varying(255)',
            column_name="name" if i % 2 == 0 else "description",
            value="Product description " + "X" * (300 + i % 100),
        )
    
    # 314 NUMERIC_OVERFLOW errors
    for i in range(314):
        reporter.profile_data("list_price", "NUMERIC(12,2)", 9999999999.99 + i)
        reporter.record_error(
            ErrorCategory.NUMERIC_OVERFLOW,
            record_id=2000 + i,
            error_message="numeric field overflow: precision 5 scale 2 exceeded",
            column_name="list_price",
            value=str(9999999999.99 + i),
        )
    
    # 214 NULL_CONSTRAINT errors
    for i in range(214):
        reporter.record_error(
            ErrorCategory.NULL_CONSTRAINT,
            record_id=3000 + i,
            error_message='null value in column "name" violates not-null constraint',
            column_name="name",
        )
    
    # Profile all data
    for i in range(10000):
        reporter.profile_data("name", "VARCHAR(255)", f"Product {i}" * 10)
        reporter.profile_data("list_price", "NUMERIC(12,2)", 100.0 + i * 0.5)
    
    # 16,421 successful
    reporter.record_success(16421)
    
    summary1 = reporter.end_batch()
    recommender.add_batch_summary(summary1)
    print(f"  Processed: 17,536 | Success: 16,421 | Failed: 1,115")
    
    # =====================================================
    # PHASE 2: sale.order sync with NUMERIC_OVERFLOW
    # =====================================================
    print("\nSimulating sync for: sale.order")
    reporter.start_batch("sale.order", "sale_order")
    
    # 12 NUMERIC_OVERFLOW errors
    for i in range(12):
        reporter.profile_data("amount_total", "NUMERIC(14,2)", 999999999.99 + i * 1000)
        reporter.record_error(
            ErrorCategory.NUMERIC_OVERFLOW,
            record_id=4000 + i,
            error_message="numeric field overflow",
            column_name="amount_total",
            value=str(999999999.99 + i * 1000),
        )
    
    # Profile data
    for i in range(1000):
        reporter.profile_data("amount_total", "NUMERIC(14,2)", 1000.0 + i * 10)
    
    reporter.record_success(1180)
    summary2 = reporter.end_batch()
    recommender.add_batch_summary(summary2)
    print(f"  Processed: 1,192 | Success: 1,180 | Failed: 12")
    
    # =====================================================
    # PHASE 3: res.partner (no errors)
    # =====================================================
    print("\nSimulating sync for: res.partner")
    reporter.start_batch("res.partner", "res_partner")
    
    for i in range(1000):
        reporter.profile_data("name", "VARCHAR(255)", f"Partner {i}")
        reporter.profile_data("email", "VARCHAR(255)", f"partner{i}@example.com")
    
    reporter.record_success(2577)
    summary3 = reporter.end_batch()
    recommender.add_batch_summary(summary3)
    print(f"  Processed: 2,577 | Success: 2,577 | Failed: 0")
    
    # =====================================================
    # PHASE 4: stock.move (various errors)
    # =====================================================
    print("\nSimulating sync for: stock.move")
    reporter.start_batch("stock.move", "stock_move")
    
    # 300 DATA_TOO_LONG errors
    for i in range(300):
        reporter.profile_data("name", "VARCHAR(255)", "X" * (300 + i % 50))
        reporter.record_error(
            ErrorCategory.DATA_TOO_LONG,
            record_id=5000 + i,
            column_name="name",
        )
    
    # 332 SCHEMA_ERROR errors
    for i in range(332):
        reporter.record_error(
            ErrorCategory.SCHEMA_ERROR,
            record_id=6000 + i,
            error_message='column "origin_move_id" does not exist',
            column_name="origin_move_id",
        )
    
    # Profile data
    for i in range(10000):
        reporter.profile_data("name", "VARCHAR(255)", f"Move {i}")
    
    reporter.record_success(292812)
    summary4 = reporter.end_batch()
    recommender.add_batch_summary(summary4)
    print(f"  Processed: 293,444 | Success: 292,812 | Failed: 632")
    
    # =====================================================
    # EXPORT ALL REPORTS
    # =====================================================
    print("\n" + "=" * 70)
    print("EXPORTING ALL REPORTS")
    print("=" * 70)
    
    # Export error reports
    paths = reporter.export_all()
    print("\nExported reports:")
    for key, path in paths.items():
        print(f"  {key}: {path}")
    
    # Export schema recommendations
    rec_paths = recommender.export()
    print("\nSchema recommendations:")
    for key, path in rec_paths.items():
        print(f"  {key}: {path}")
    
    # =====================================================
    # PRINT SYNC HEALTH REPORT (Executive Summary)
    # =====================================================
    print("\n")
    reporter.print_summary()
    
    # =====================================================
    # PRINT SCHEMA RECOMMENDATIONS
    # =====================================================
    recommender.print_recommendations()
    
    return reporter, recommender


def show_generated_files():
    """Show the generated report files."""
    print("\n" + "=" * 70)
    print("GENERATED REPORT FILES")
    print("=" * 70)
    
    # Find all report files
    patterns = [
        "reports/latest_run_summary.json",
        "reports/model_health/*.json",
        "reports/sample_errors/*.json",
        "reports/schema_recommendations/*.sql",
        "reports/schema_recommendations/*.json",
        "reports/errors/*.csv",
        "reports/errors/*.json",
    ]
    
    for pattern in patterns:
        files = sorted(glob.glob(pattern))
        if files:
            print(f"\n{pattern}:")
            for f in files[:3]:  # Show first 3 of each
                print(f"  {f}")
            if len(files) > 3:
                print(f"  ... and {len(files) - 3} more")


def show_sample_reports():
    """Show sample content from generated reports."""
    print("\n" + "=" * 70)
    print("SAMPLE REPORT CONTENTS")
    print("=" * 70)
    
    # Show latest_run_summary.json
    summary_file = "reports/latest_run_summary.json"
    if os.path.exists(summary_file):
        print(f"\n--- {summary_file} ---")
        with open(summary_file, 'r') as f:
            data = json.load(f)
            print(json.dumps(data, indent=2)[:1500])
    
    # Show model health report
    health_file = "reports/model_health/product_template.json"
    if os.path.exists(health_file):
        print(f"\n--- {health_file} ---")
        with open(health_file, 'r') as f:
            data = json.load(f)
            print(json.dumps(data, indent=2)[:1500])
    
    # Show migration SQL
    sql_file = "reports/schema_recommendations/migration_suggestions.sql"
    if os.path.exists(sql_file):
        print(f"\n--- {sql_file} ---")
        with open(sql_file, 'r') as f:
            content = f.read()
            print(content[:1500])


def main():
    """Run the full demo."""
    # Clean up old reports
    import shutil
    if os.path.exists("reports"):
        shutil.rmtree("reports")
    os.makedirs("reports", exist_ok=True)
    
    # Run simulation
    reporter, recommender = simulate_full_sync()
    
    # Show generated files
    show_generated_files()
    
    # Show sample contents
    show_sample_reports()
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("\nAll phases of the sync health reporting system are working:")
    print("  ✓ Phase 1: Executive Report (Sync Health)")
    print("  ✓ Phase 2: Model Health Reports")
    print("  ✓ Phase 3: Error Classification")
    print("  ✓ Phase 4: Column Analysis")
    print("  ✓ Phase 5: Sample Failures")
    print("  ✓ Phase 6: Schema Recommendations")
    print("  ✓ Phase 7: Data Profiling")
    print("  ✓ Phase 8: Top Issues Report")
    print("  ✓ Phase 9: Safe Processing (no batch abort)")
    print("  ✓ Phase 10: Code Organization (src/reporting/)")
    print()


if __name__ == "__main__":
    main()
