#!/usr/bin/env python
"""Demo script for error reporting functionality.

This script demonstrates the error reporting and diagnostics system
by simulating sync operations with various error types.
"""

import os
import sys
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.reporting.error_enums import ErrorCategory
from src.reporting.error_reporter import ErrorReporter


def simulate_sync_with_errors():
    """Simulate a sync operation with various error types."""
    
    print("=" * 70)
    print("ERROR REPORTING DEMO - Simulating Sync with Errors")
    print("=" * 70)
    print()
    
    # Create error reporter
    reporter = ErrorReporter(reports_dir="reports/errors")
    
    # Simulate product.template sync
    print("Simulating sync for: product.template")
    reporter.start_batch("product.template")
    
    # Simulate 1000 records with various errors
    for i in range(997):
        # 587 DATA_TOO_LONG errors (varchar overflow)
        if i < 587:
            reporter.record_error(
                ErrorCategory.DATA_TOO_LONG,
                record_id=1000 + i,
                error_message='value too long for type character varying(255)',
                column_name="description" if i % 2 == 0 else "name",
                value="This is a very long product description " + "X" * 100 + f" (product {i})",
            )
        # 314 NUMERIC_OVERFLOW errors
        elif i < 901:
            reporter.record_error(
                ErrorCategory.NUMERIC_OVERFLOW,
                record_id=1000 + i,
                error_message="numeric field overflow: precision 5 scale 2 exceeded",
                column_name="list_price",
                value="999999999999999.99",
            )
        # 96 other errors
        else:
            if i % 3 == 0:
                reporter.record_error(
                    ErrorCategory.NULL_CONSTRAINT,
                    record_id=1000 + i,
                    error_message='null value in column "name" violates not-null constraint',
                    column_name="name",
                )
            else:
                reporter.record_error(
                    ErrorCategory.UNKNOWN,
                    record_id=1000 + i,
                    error_message="unexpected error occurred during sync",
                )
    
    # 3 successful records
    reporter.record_success(3)
    
    # End batch
    batch_summary = reporter.end_batch()
    
    # Print batch summary
    reporter.print_batch_summary()
    
    # Simulate sale.order sync
    print("\nSimulating sync for: sale.order")
    reporter.start_batch("sale.order")
    
    # 2201 records, 12 errors
    for i in range(10):
        reporter.record_error(
            ErrorCategory.FOREIGN_KEY,
            record_id=2000 + i,
            error_message='insert or update violates foreign key constraint "fk_partner"',
            column_name="partner_id",
        )
    for i in range(2):
        reporter.record_error(
            ErrorCategory.UNIQUE_CONSTRAINT,
            record_id=2010 + i,
            error_message='duplicate key value violates unique constraint "sale_order_name_uniq"',
            column_name="name",
        )
    
    reporter.record_success(2189)
    reporter.end_batch()
    reporter.print_batch_summary()
    
    # Simulate purchase.order sync (no errors)
    print("\nSimulating sync for: purchase.order")
    reporter.start_batch("purchase.order")
    reporter.record_success(1802)
    reporter.end_batch()
    reporter.print_batch_summary()
    
    # Export reports
    print("\nExporting reports...")
    csv_path, json_path = reporter.export()
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")
    
    # Print final summary
    reporter.print_summary()
    
    return reporter


def main():
    """Run the demo."""
    # Ensure reports directory exists
    os.makedirs("reports/errors", exist_ok=True)
    
    # Run simulation
    reporter = simulate_sync_with_errors()
    
    # Show generated files
    print("\n" + "=" * 70)
    print("GENERATED FILES")
    print("=" * 70)
    
    import glob
    csv_files = sorted(glob.glob("reports/errors/error_report_*.csv"))
    json_files = sorted(glob.glob("reports/errors/summary_*.json"))
    
    if csv_files:
        latest_csv = csv_files[-1]
        print(f"\nLatest CSV: {latest_csv}")
        print("-" * 70)
        with open(latest_csv, 'r') as f:
            lines = f.readlines()[:15]  # Show first 15 lines
            for line in lines:
                print(line.strip())
    
    if json_files:
        latest_json = json_files[-1]
        print(f"\nLatest JSON: {latest_json}")
        print("-" * 70)
        with open(latest_json, 'r') as f:
            print(f.read()[:2000])  # Show first 2000 chars
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
