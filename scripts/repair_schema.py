#!/usr/bin/env python
"""
Schema Repair Script

Automatically repairs PostgreSQL schema issues that cause sync errors:
- Missing columns (SCHEMA_ERROR)
- Wrong column types (DATA_TOO_LONG, NUMERIC_OVERFLOW)
- NULL constraint issues (NULL_CONSTRAINT)

Usage:
    python scripts/repair_schema.py                    # Repair from error reports
    python scripts/repair_schema.py --from-report      # Repair based on error reports
    python scripts/repair_schema.py --table product_template  # Repair specific table
    python scripts/repair_schema.py --dry-run          # Show what would be changed
    python scripts/repair_schema.py --verbose          # Show detailed progress
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect

from src.clients.postgres_client import PostgresClient
from src.utils.logging import get_logger

logger = get_logger("schema_repair")


class SchemaRepair:
    """Automatic schema repair for sync errors."""
    
    # Type detection based on error patterns
    TYPE_MAP = {
        'char': 'TEXT',
        'text': 'TEXT',
        'html': 'TEXT',
        'selection': 'TEXT',
        'float': 'NUMERIC(30,10)',
        'monetary': 'NUMERIC(30,10)',
        'integer': 'BIGINT',
        'bigint': 'BIGINT',
        'boolean': 'BOOLEAN',
        'date': 'DATE',
        'datetime': 'TIMESTAMP',
        'many2one': 'BIGINT',
        'one2many': 'JSONB',
        'many2many': 'JSONB',
        'binary': 'TEXT',
        'reference': 'TEXT',
    }
    
    # Column name to type inference
    COLUMN_TYPE_HINTS = {
        'name': 'TEXT',
        'description': 'TEXT',
        'description_sale': 'TEXT',
        'description_purchase': 'TEXT',
        'list_price': 'NUMERIC(30,10)',
        'standard_price': 'NUMERIC(30,10)',
        'amount': 'NUMERIC(30,10)',
        'amount_total': 'NUMERIC(30,10)',
        'price_unit': 'NUMERIC(30,10)',
        'price_subtotal': 'NUMERIC(30,10)',
        'price_tax': 'NUMERIC(30,10)',
        'product_qty': 'NUMERIC(30,10)',
        'qty_done': 'NUMERIC(30,10)',
        'quantity': 'NUMERIC(30,10)',
        'date': 'DATE',
        'date_order': 'DATE',
        'date_invoice': 'DATE',
        'write_date': 'TIMESTAMP',
        'create_date': 'TIMESTAMP',
        'active': 'BOOLEAN',
        'type': 'TEXT',
        'state': 'TEXT',
        'partner_id': 'BIGINT',
        'company_id': 'BIGINT',
        'user_id': 'BIGINT',
        'product_id': 'BIGINT',
        'origin_move_id': 'BIGINT',
        'move_id': 'BIGINT',
        'picking_id': 'BIGINT',
        'location_id': 'BIGINT',
        'location_dest_id': 'BIGINT',
        'procurement_id': 'BIGINT',
        'group_id': 'BIGINT',
        'route_id': 'BIGINT',
        'warehouse_id': 'BIGINT',
        'inventory_id': 'BIGINT',
        'lot_id': 'BIGINT',
        'package_id': 'BIGINT',
        'owner_id': 'BIGINT',
        'x_studio_': 'TEXT',  # Custom fields default to TEXT
    }
    
    def __init__(self, pg_client: PostgresClient, dry_run: bool = False):
        self._pg = pg_client
        self._dry_run = dry_run
        self._repairs = []
    
    def repair_from_error_report(self, error_csv_path: str = None) -> dict:
        """Repair schema based on error reports."""
        if error_csv_path is None:
            error_csv_path = self._find_latest_error_report()
        
        if not error_csv_path or not os.path.exists(error_csv_path):
            logger.warning("No error report found")
            return {"error": "No error report found"}
        
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": self._dry_run,
            "source_report": error_csv_path,
            "repairs": [],
            "summary": {
                "columns_added": 0,
                "types_migrated": 0,
                "constraints_fixed": 0,
            }
        }
        
        # Parse error report
        missing_columns = {}  # {table: {column: suggested_type}}
        type_issues = {}      # {table: {column: new_type}}
        constraint_issues = {}  # {table: {column: True}}
        
        with open(error_csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                table = row['model'].replace('.', '_').lower()
                column = row['column_name']
                error_cat = row['error_category']
                error_msg = row['error_message']
                
                if error_cat == 'SCHEMA_ERROR':
                    # Missing column
                    if 'does not exist' in error_msg or 'undefined column' in error_msg.lower():
                        if table not in missing_columns:
                            missing_columns[table] = {}
                        # Infer type from column name
                        missing_columns[table][column] = self._infer_type(column)
                
                elif error_cat == 'DATA_TOO_LONG':
                    # VARCHAR overflow -> TEXT
                    if table not in type_issues:
                        type_issues[table] = {}
                    type_issues[table][column] = 'TEXT'
                
                elif error_cat == 'NUMERIC_OVERFLOW':
                    # NUMERIC too small -> NUMERIC(30,10)
                    if table not in type_issues:
                        type_issues[table] = {}
                    type_issues[table][column] = 'NUMERIC(30,10)'
                
                elif error_cat == 'NULL_CONSTRAINT':
                    # NULL in NOT NULL column
                    if table not in constraint_issues:
                        constraint_issues[table] = {}
                    constraint_issues[table][column] = True
        
        # Execute repairs
        for table, columns in missing_columns.items():
            for column, pg_type in columns.items():
                repair = self._add_column(table, column, pg_type)
                if repair and 'error' not in repair:
                    results["summary"]["columns_added"] += 1
                    results["repairs"].append(repair)
        
        for table, columns in type_issues.items():
            for column, new_type in columns.items():
                repair = self._migrate_column(table, column, new_type)
                if repair and 'error' not in repair:
                    results["summary"]["types_migrated"] += 1
                    results["repairs"].append(repair)
        
        for table, columns in constraint_issues.items():
            for column in columns.keys():
                repair = self._drop_not_null(table, column)
                if repair and 'error' not in repair:
                    results["summary"]["constraints_fixed"] += 1
                    results["repairs"].append(repair)
        
        return results
    
    def repair_table(self, table: str, columns_to_add: dict = None) -> dict:
        """Repair schema for a specific table."""
        result = {
            "table": table,
            "repairs": [],
            "columns_added": 0,
            "types_migrated": 0,
            "constraints_fixed": 0,
        }
        
        if columns_to_add:
            for column, pg_type in columns_to_add.items():
                repair = self._add_column(table, column, pg_type)
                if repair:
                    result["repairs"].append(repair)
                    result["columns_added"] += 1
        
        return result
    
    def repair_all_varchar_to_text(self, tables: list[str] = None) -> dict:
        """Migrate all VARCHAR columns to TEXT."""
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": self._dry_run,
            "repairs": [],
            "summary": {"types_migrated": 0},
        }
        
        if tables is None:
            tables = self._get_sync_tables()
        
        for table in tables:
            pg_columns = self._get_pg_columns(table)
            for col_name, col_info in pg_columns.items():
                col_type = str(col_info.get("type", "")).upper()
                if col_type.startswith("VARCHAR"):
                    repair = self._migrate_column(table, col_name, "TEXT")
                    if repair and 'error' not in repair:
                        results["repairs"].append(repair)
                        results["summary"]["types_migrated"] += 1
        
        return results
    
    def _find_latest_error_report(self) -> str:
        """Find the most recent error report."""
        error_dir = "reports/errors"
        if not os.path.exists(error_dir):
            return None
        
        reports = []
        for f in os.listdir(error_dir):
            if f.startswith("error_report_") and f.endswith(".csv"):
                reports.append(os.path.join(error_dir, f))
        
        if not reports:
            return None
        
        return max(reports, key=os.path.getmtime)
    
    def _infer_type(self, column: str) -> str:
        """Infer PostgreSQL type from column name."""
        # Check exact matches first
        if column in self.COLUMN_TYPE_HINTS:
            return self.COLUMN_TYPE_HINTS[column]
        
        # Check prefix matches
        for prefix, pg_type in self.COLUMN_TYPE_HINTS.items():
            if column.startswith(prefix):
                return pg_type
        
        # Check suffixes
        if '_id' in column or column.endswith('_ids'):
            return 'BIGINT'
        if 'date' in column.lower():
            return 'TIMESTAMP'
        if 'price' in column.lower() or 'amount' in column.lower() or 'qty' in column.lower():
            return 'NUMERIC(30,10)'
        
        return 'TEXT'  # Default to TEXT
    
    def _get_sync_tables(self) -> list:
        """Get list of sync tables from PostgreSQL."""
        tables = []
        try:
            with self._pg.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name LIKE '%_template' 
                       OR table_name LIKE '%_order' 
                       OR table_name LIKE '%_move' 
                       OR table_name = 'res_partner'
                """))
                tables = [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get tables: {e}")
        return tables
    
    def _get_pg_columns(self, table: str) -> dict:
        """Get column info from PostgreSQL."""
        columns = {}
        try:
            inspector = inspect(self._pg.engine)
            for col in inspector.get_columns(table):
                columns[col["name"]] = {
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "default": col.get("default"),
                }
        except Exception as e:
            logger.warning(f"Could not inspect table {table}: {e}")
        return columns
    
    def _add_column(self, table: str, column: str, pg_type: str) -> Optional[dict]:
        """Add a missing column."""
        # Check if column already exists
        existing = self._get_pg_columns(table)
        if column in existing:
            return None
        
        repair = {
            "type": "ADD_COLUMN",
            "table": table,
            "column": column,
            "pg_type": pg_type,
            "sql": f'ALTER TABLE "{table}" ADD COLUMN "{column}" {pg_type}',
        }
        
        if self._dry_run:
            print(f"  [DRY RUN] Would execute: {repair['sql']}")
            logger.info(f"[DRY RUN] Would execute: {repair['sql']}")
        else:
            try:
                with self._pg.engine.connect() as conn:
                    conn.execute(text(repair["sql"]))
                    conn.commit()
                print(f"  ✓ Added column: {table}.{column} ({pg_type})")
                logger.info(f"Added column: {table}.{column} ({pg_type})")
            except Exception as e:
                logger.error(f"Failed to add column {column}: {e}")
                repair["error"] = str(e)
        
        self._repairs.append(repair)
        return repair
    
    def _migrate_column(self, table: str, column: str, new_type: str) -> Optional[dict]:
        """Migrate column to new type."""
        repair = {
            "type": "MIGRATE_TYPE",
            "table": table,
            "column": column,
            "new_type": new_type,
            "sql": f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE {new_type}',
        }
        
        if self._dry_run:
            print(f"  [DRY RUN] Would execute: {repair['sql']}")
            logger.info(f"[DRY RUN] Would execute: {repair['sql']}")
        else:
            try:
                with self._pg.engine.connect() as conn:
                    conn.execute(text(repair["sql"]))
                    conn.commit()
                print(f"  ✓ Migrated column: {table}.{column} -> {new_type}")
                logger.info(f"Migrated column: {table}.{column} -> {new_type}")
            except Exception as e:
                logger.error(f"Failed to migrate column {column}: {e}")
                repair["error"] = str(e)
        
        self._repairs.append(repair)
        return repair
    
    def _drop_not_null(self, table: str, column: str) -> Optional[dict]:
        """Drop NOT NULL constraint from column."""
        repair = {
            "type": "DROP_NOT_NULL",
            "table": table,
            "column": column,
            "sql": f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL',
        }
        
        if self._dry_run:
            print(f"  [DRY RUN] Would execute: {repair['sql']}")
            logger.info(f"[DRY RUN] Would execute: {repair['sql']}")
        else:
            try:
                with self._pg.engine.connect() as conn:
                    conn.execute(text(repair["sql"]))
                    conn.commit()
                print(f"  ✓ Dropped NOT NULL: {table}.{column}")
                logger.info(f"Dropped NOT NULL: {table}.{column}")
            except Exception as e:
                logger.error(f"Failed to drop NOT NULL on {column}: {e}")
                repair["error"] = str(e)
        
        self._repairs.append(repair)
        return repair
    
    def save_report(self, results: dict, output_dir: str = "reports/schema_repairs") -> str:
        """Save repair report to file."""
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"repair_report_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        return filepath


def main():
    parser = argparse.ArgumentParser(description="Repair PostgreSQL schema from sync errors")
    parser.add_argument("--from-report", action="store_true", help="Repair based on error reports")
    parser.add_argument("--table", type=str, help="Specific table to repair")
    parser.add_argument("--migrate-varchar", action="store_true", help="Migrate all VARCHAR to TEXT")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without making changes")
    parser.add_argument("--verbose", action="store_true", help="Show detailed progress")
    parser.add_argument("--output-dir", default="reports/schema_repairs", help="Output directory for reports")
    
    args = parser.parse_args()
    
    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.INFO)
    
    print("=" * 70)
    print("SCHEMA REPAIR TOOL")
    print("=" * 70)
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made\n")
    
    # Initialize PostgreSQL client
    print("Connecting to PostgreSQL...")
    try:
        pg = PostgresClient()
        print("✓ Connected successfully\n")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)
    
    # Run repair
    repair = SchemaRepair(pg, dry_run=args.dry_run)
    results = None
    
    if args.from_report:
        print("Reading error reports to identify issues...\n")
        results = repair.repair_from_error_report()
    elif args.table:
        print(f"Repairing table: {args.table}\n")
        results = repair.repair_table(args.table)
    elif args.migrate_varchar:
        print("Migrating all VARCHAR columns to TEXT...\n")
        results = repair.repair_all_varchar_to_text()
    else:
        # Default: repair from error reports
        print("Reading error reports to identify issues...\n")
        results = repair.repair_from_error_report()
    
    # Print summary
    print("\n" + "=" * 70)
    print("REPAIR SUMMARY")
    print("=" * 70)
    
    if results and "summary" in results:
        summary = results.get("summary", {})
        print(f"\nColumns Added:       {summary.get('columns_added', 0)}")
        print(f"Types Migrated:      {summary.get('types_migrated', 0)}")
        print(f"Constraints Fixed:   {summary.get('constraints_fixed', 0)}")
    elif results and "columns_added" in results:
        print(f"\nColumns Added:       {results.get('columns_added', 0)}")
        print(f"Types Migrated:      {results.get('types_migrated', 0)}")
        print(f"Constraints Fixed:   {results.get('constraints_fixed', 0)}")
    elif results and "summary" in results:
        print(f"\nTypes Migrated:      {results.get('summary', {}).get('types_migrated', 0)}")
    
    if results and "error" in results:
        print(f"\n✗ Error: {results['error']}")
    
    # Save report
    if not args.dry_run and results:
        report_path = repair.save_report(results, args.output_dir)
        print(f"\n✓ Report saved to: {report_path}")
    elif args.dry_run:
        print("\n✓ DRY RUN complete - no changes made")
    
    print("=" * 70)


if __name__ == "__main__":
    main()