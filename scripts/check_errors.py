#!/usr/bin/env python
"""
Quick Schema & Error Check

Quickly check schema and error issues for all models.

Usage:
    python scripts/check_errors.py
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

def check_error_reports():
    """Check all error reports and generate summary."""
    
    error_dir = "reports/errors"
    if not os.path.exists(error_dir):
        print("❌ No error reports found in reports/errors/")
        print("   Run sync first: python -m src.main --mode full")
        return
    
    # Find latest error report
    csv_files = [f for f in os.listdir(error_dir) if f.startswith("error_report_") and f.endswith(".csv")]
    if not csv_files:
        print("❌ No error CSV reports found")
        return
    
    latest_csv = os.path.join(error_dir, sorted(csv_files)[-1])
    
    # Analyze errors
    errors_by_model = defaultdict(lambda: defaultdict(int))
    errors_by_category = defaultdict(int)
    total_errors = 0
    
    print("=" * 70)
    print("SCHEMA & ERROR CHECK REPORT")
    print("=" * 70)
    print(f"\n📊 Source: {latest_csv}\n")
    
    with open(latest_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row['model']
            category = row['error_category']
            column = row['column_name']
            
            errors_by_model[model][category] += 1
            errors_by_category[category] += 1
            total_errors += 1
    
    # Print by model
    print("-" * 70)
    print("ERRORS BY MODEL")
    print("-" * 70)
    
    for model, categories in sorted(errors_by_model.items()):
        total = sum(categories.values())
        print(f"\n📦 {model} ({total} errors)")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"   ├── {cat}: {count}")
    
    # Print summary
    print("\n" + "-" * 70)
    print("ERROR SUMMARY")
    print("-" * 70)
    print(f"\nTotal Errors: {total_errors}")
    
    for cat, count in sorted(errors_by_category.items(), key=lambda x: -x[1]):
        pct = (count / total_errors * 100) if total_errors else 0
        bar = "█" * int(pct / 5)
        print(f"  {cat:20} {count:5} ({pct:5.1f}%) {bar}")
    
    # Recommendations
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    
    if 'SCHEMA_ERROR' in errors_by_category:
        print("\n🔧 SCHEMA_ERROR detected!")
        print("   → Run: python scripts/repair_schema.py --dry-run")
        print("   → Then: python scripts/repair_schema.py")
    
    if 'DATA_TOO_LONG' in errors_by_category:
        print("\n🔧 DATA_TOO_LONG detected!")
        print("   → Run: python scripts/repair_schema.py --migrate-varchar --dry-run")
        print("   → Then: python scripts/repair_schema.py --migrate-varchar")
    
    if 'NUMERIC_OVERFLOW' in errors_by_category:
        print("\n🔧 NUMERIC_OVERFLOW detected!")
        print("   → Run: python scripts/repair_schema.py")
        print("   → Will migrate NUMERIC columns to NUMERIC(30,10)")
    
    if 'NULL_CONSTRAINT' in errors_by_category:
        print("\n🔧 NULL_CONSTRAINT detected!")
        print("   → Run: python scripts/repair_schema.py")
        print("   → Will drop NOT NULL from optional columns")
    
    if 'FOREIGN_KEY' in errors_by_category:
        print("\n⚠️  FOREIGN_KEY detected!")
        print("   → Check if related records exist in Odoo")
        print("   → May need to sync parent models first")
    
    if 'UNIQUE_CONSTRAINT' in errors_by_category:
        print("\n⚠️  UNIQUE_CONSTRAINT detected!")
        print("   → Duplicate records found in Odoo")
        print("   → Check Odoo for duplicate entries")
    
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Quick Schema & Error Check")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose output")
    args = parser.parse_args()
    
    check_error_reports()


if __name__ == "__main__":
    main()
