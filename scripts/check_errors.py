#!/usr/bin/env python
"""
Comprehensive Schema & Error Check

Check all models from YAML, their sync status, schema, and errors.

Usage:
    python scripts/check_errors.py
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime

# Check dependencies
try:
    import psycopg2
except ImportError:
    print("❌ Error: psycopg2 is required")
    print("   Install with: pip install psycopg2-binary")
    sys.exit(1)


def load_env_file():
    """Load environment variables from .env file."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())


def get_db_connection():
    """Get PostgreSQL connection from environment."""
    load_env_file()
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'sync_db'),
        user=os.getenv('POSTGRES_USER', 'sync_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'password'),
    )


def load_models_from_yaml():
    """Load all models from config/models.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'models.yaml')
    
    if not os.path.exists(config_path):
        return ["res.partner", "product.template", "sale.order"]  # defaults
    
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        models = []
        if config:
            if "models" in config:
                models.extend(config["models"])
            if "models_with_options" in config:
                for item in config["models_with_options"]:
                    if isinstance(item, dict):
                        models.append(item.get("odoo_model", ""))
                    elif isinstance(item, str):
                        models.append(item)
            if "legacy_models" in config:
                for item in config["legacy_models"]:
                    if isinstance(item, dict):
                        models.append(item.get("odoo_model", ""))
        
        return [m for m in models if m]
    except ImportError:
        # yaml not available, read manually
        with open(config_path, 'r') as f:
            content = f.read()
        
        models = []
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('- '):
                continue
            if line.startswith('- '):
                model = line[2:].strip().strip('"').strip("'")
                if model and '.' in model:
                    models.append(model)
        return models if models else ["res.partner", "product.template"]


def get_sync_state(conn):
    """Get sync state from PostgreSQL."""
    state = {}
    try:
        with conn.cursor() as cur:
            # Try sync_state table
            cur.execute("""
                SELECT model, last_sync, records_synced, errors 
                FROM sync_state 
                ORDER BY last_sync DESC
            """)
            for row in cur.fetchall():
                state[row[0]] = {
                    'last_sync': row[1],
                    'records_synced': row[2],
                    'errors': row[3],
                    'table': row[0].replace('.', '_').lower()
                }
    except:
        pass
    return state


def get_postgres_tables(conn):
    """Get all PostgreSQL tables."""
    tables = {}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                AND table_name NOT LIKE 'pg_%'
                AND table_name NOT LIKE 'sql_%'
            """)
            for row in cur.fetchall():
                tables[row[0]] = True
    except:
        pass
    return tables


def get_table_columns(conn, table):
    """Get columns for a table."""
    columns = {}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
            """, (table,))
            for row in cur.fetchall():
                columns[row[0]] = {
                    'type': row[1],
                    'nullable': row[2] == 'YES',
                    'max_length': row[3]
                }
    except:
        pass
    return columns


def get_error_reports():
    """Get all error reports with timestamps."""
    error_dir = "reports/errors"
    if not os.path.exists(error_dir):
        return None
    
    csv_files = [f for f in os.listdir(error_dir) 
                 if f.startswith("error_report_") and f.endswith(".csv")]
    
    if not csv_files:
        return None
    
    # Parse timestamps and sort
    reports = []
    for f in csv_files:
        # Extract timestamp from filename: error_report_YYYYMMDD_HHMMSS.csv
        ts_str = f.replace("error_report_", "").replace(".csv", "")
        try:
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            reports.append((ts, os.path.join(error_dir, f)))
        except:
            reports.append((datetime.min, os.path.join(error_dir, f)))
    
    # Return all reports sorted by date
    return sorted(reports, key=lambda x: x[0], reverse=True)


def analyze_error_report(csv_path):
    """Analyze an error report CSV."""
    errors_by_model = defaultdict(lambda: defaultdict(int))
    total_errors = 0
    last_modified = datetime.fromtimestamp(os.path.getmtime(csv_path))
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row['model']
            category = row['error_category']
            errors_by_model[model][category] += 1
            total_errors += 1
    
    return errors_by_model, total_errors, last_modified


def check_postgres_schema(conn, table):
    """Check schema issues for a table."""
    issues = []
    columns = get_table_columns(conn, table)
    
    for col_name, col_info in columns.items():
        col_type = col_info['type'].upper()
        
        # Check VARCHAR limits
        if col_type.startswith('CHARACTER VARYING') or col_type.startswith('VARCHAR'):
            max_len = col_info.get('max_length')
            if max_len and max_len < 1000:
                issues.append({
                    'type': 'SMALL_VARCHAR',
                    'column': col_name,
                    'current': f"VARCHAR({max_len})",
                    'recommended': 'TEXT'
                })
        
        # Check INTEGER vs BIGINT
        if col_type == 'INTEGER':
            issues.append({
                'type': 'SMALL_INT',
                'column': col_name,
                'current': 'INTEGER',
                'recommended': 'BIGINT'
            })
    
    return issues


def main():
    parser = argparse.ArgumentParser(description="Comprehensive Schema & Error Check")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose output")
    parser.add_argument("--schema", action="store_true", help="Check PostgreSQL schema")
    args = parser.parse_args()
    
    print("=" * 70)
    print("COMPREHENSIVE SCHEMA & ERROR CHECK")
    print("=" * 70)
    
    # 1. Load models from YAML
    print("\n📋 STEP 1: Loading models from config/models.yaml...")
    models = load_models_from_yaml()
    print(f"   Found {len(models)} models:")
    for m in models:
        print(f"   • {m}")
    
    # 2. Check PostgreSQL connection
    print("\n📡 STEP 2: Connecting to PostgreSQL...")
    try:
        conn = get_db_connection()
        print("   ✓ Connected successfully")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        print("   Make sure PostgreSQL is running and .env is configured")
        sys.exit(1)
    
    # 3. Check sync state
    print("\n📊 STEP 3: Checking sync state...")
    sync_state = get_sync_state(conn)
    
    if sync_state:
        print(f"   Found {len(sync_state)} synced models")
        for model, state in sorted(sync_state.items()):
            last_sync = state['last_sync']
            records = state['records_synced'] or 0
            errors = state['errors'] or 0
            print(f"   • {model}: {records:,} records, {errors} errors (last: {last_sync})")
    else:
        print("   ⚠ No sync state found (run sync first)")
    
    # 4. Check PostgreSQL tables
    print("\n🗄️  STEP 4: Checking PostgreSQL tables...")
    tables = get_postgres_tables(conn)
    print(f"   Found {len(tables)} tables")
    
    for model in models:
        table = model.replace('.', '_').lower()
        if table in tables:
            cols = get_table_columns(conn, table)
            print(f"   ✓ {table}: {len(cols)} columns")
            
            # Check schema issues
            if args.schema:
                issues = check_postgres_schema(conn, table)
                for issue in issues[:3]:  # Show first 3
                    print(f"      ⚠ {issue['column']}: {issue['current']} → {issue['recommended']}")
        else:
            print(f"   ✗ {table}: TABLE NOT FOUND")
    
    # 5. Check error reports
    print("\n📝 STEP 5: Checking error reports...")
    reports = get_error_reports()
    
    if reports:
        print(f"   Found {len(reports)} error report(s)")
        print(f"   Latest report: {reports[0][0].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Analyze latest report
        errors_by_model, total_errors, report_time = analyze_error_report(reports[0][1])
        
        print("\n" + "-" * 70)
        print("ERROR BREAKDOWN (From Latest Report)")
        print("-" * 70)
        
        for model, categories in sorted(errors_by_model.items()):
            total = sum(categories.values())
            print(f"\n📦 {model} ({total} errors)")
            for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
                print(f"   ├── {cat}: {count}")
        
        # Summary
        print("\n" + "-" * 70)
        print("ERROR SUMMARY")
        print("-" * 70)
        
        all_categories = defaultdict(int)
        for model_errors in errors_by_model.values():
            for cat, count in model_errors.items():
                all_categories[cat] += count
        
        for cat, count in sorted(all_categories.items(), key=lambda x: -x[1]):
            pct = (count / total_errors * 100) if total_errors else 0
            bar = "█" * int(pct / 5)
            print(f"  {cat:20} {count:5} ({pct:5.1f}%) {bar}")
        
        print(f"\nTotal Errors: {total_errors:,}")
        
        # Recommendations
        print("\n" + "=" * 70)
        print("RECOMMENDATIONS")
        print("=" * 70)
        
        if 'SCHEMA_ERROR' in all_categories:
            print("\n🔧 SCHEMA_ERROR detected!")
            print("   → Run: python scripts/repair_schema.py --dry-run")
        
        if 'DATA_TOO_LONG' in all_categories:
            print("\n🔧 DATA_TOO_LONG detected!")
            print("   → Run: python scripts/repair_schema.py --migrate-varchar --dry-run")
        
        if 'NUMERIC_OVERFLOW' in all_categories:
            print("\n🔧 NUMERIC_OVERFLOW detected!")
            print("   → Run: python scripts/repair_schema.py")
        
        if 'NULL_CONSTRAINT' in all_categories:
            print("\n🔧 NULL_CONSTRAINT detected!")
            print("   → Run: python scripts/repair_schema.py")
    else:
        print("   ⚠ No error reports found")
        print("   Run sync first: python -m src.main --mode full")
    
    # 6. Summary table
    print("\n" + "=" * 70)
    print("MODEL STATUS OVERVIEW")
    print("=" * 70)
    print(f"\n{'Model':<30} {'Table':<25} {'Synced':<10} {'Errors':<10}")
    print("-" * 75)
    
    for model in models:
        table = model.replace('.', '_').lower()
        synced = "✓" if table in tables else "✗"
        
        if model in sync_state:
            errors = sync_state[model].get('errors', 0)
        elif model in errors_by_model:
            errors = sum(errors_by_model[model].values())
        else:
            errors = "-"
        
        print(f"{model:<30} {table:<25} {synced:<10} {errors}")
    
    conn.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
