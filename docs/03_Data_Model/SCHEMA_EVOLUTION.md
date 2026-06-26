# Schema Evolution Documentation

This document explains how the Odoo to PostgreSQL synchronization platform handles schema evolution - changes to Odoo's data model that require corresponding PostgreSQL schema changes.

## Table of Contents

- [Overview](#overview)
- [New Field Workflow](#new-field-workflow)
- [New Model Workflow](#new-model-workflow)
- [Type Migration Workflow](#type-migration-workflow)
- [Failure Recovery](#failure-recovery)

---

## Overview

The platform automatically handles schema evolution through `ensure_table_schema()` in `postgres_client.py`. This method:

1. **Creates tables** if they don't exist
2. **Adds new columns** automatically when fields are added to Odoo
3. **Migrates column types** when Odoo requires larger/specific types
4. **Creates indexes** for foreign keys and sync date fields
5. **Ensures primary key constraints** on existing tables

### Key Features

| Feature | Description |
|---------|-------------|
| **Automatic Detection** | Uses Odoo's `fields_get()` to detect changes |
| **Idempotent Operations** | Safe to run multiple times |
| **Zero-Downtime Migration** | Adds nullable columns before populating |
| **Type Widening** | Automatically upgrades restrictive types |
| **Graceful Degradation** | Skips invalid fields, continues sync |

---

## New Field Workflow

When Odoo adds a new field to a model, follow this workflow:

### Step 1: Detect the New Field

The sync engine automatically detects new fields via `fields_get()`:

```python
# In sync_engine.py
odoo_fields = self._odoo.get_model_fields(model_config.odoo_model)
```

The response includes all current Odoo fields:

```python
{
    'name': {'type': 'char', 'string': 'Name', ...},
    'email': {'type': 'char', 'string': 'Email', ...},
    'website': {'type': 'char', 'string': 'Website', ...},  # NEW!
}
```

### Step 2: Update Configuration

Add the new field to `config/models.yaml`:

```yaml
models:
  - odoo_model: res.partner
    postgres_table: res_partner
    fields:
      - id
      - name
      - email
      - website      # NEW FIELD
      - write_date
```

**Tip:** Use simple format - field names are auto-detected:
- `website` → `VARCHAR` type
- `website` → `TEXT` type (char fields become TEXT)

### Step 3: Run Sync

```bash
python -m src.main --mode full
```

### Step 4: Automatic Column Creation

The platform automatically:

1. Detects the new column doesn't exist in PostgreSQL
2. Adds the column as `NULLABLE`
3. Existing rows get `NULL` for the new column
4. New column is populated on next sync

```python
# In postgres_client.py - alter_table_add_columns()
ALTER TABLE res_partner ADD COLUMN website TEXT;
```

### Verification

Check the column was added:

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'res_partner';
```

---

## New Model Workflow

When adding an entirely new Odoo model to sync:

### Step 1: Prepare Configuration

Add to `config/models.yaml`:

```yaml
models:
  # Existing models...
  
  - odoo_model: stock.quant
    postgres_table: stock_quant
    description: "Stock quantities"
    fields:
      - id                    # Primary key
      - product_id            # Foreign key (auto-detected)
      - location_id           # Foreign key (auto-detected)
      - quantity              # Numeric value
      - write_date            # Sync date field
```

### Step 2: Validate Configuration

```bash
python -m src.main --validate
```

Expected output:
```
✓ All validation checks passed!
```

### Step 3: Run Initial Sync

```bash
python -m src.main --mode full --models stock.quant
```

This will:
1. Create the `stock_quant` table
2. Create primary key on `id`
3. Create indexes on `product_id`, `location_id`, `write_date`
4. Sync all records from Odoo

### Step 4: Verify Table Creation

```sql
-- Check table exists
SELECT table_name FROM information_schema.tables 
WHERE table_name = 'stock_quant';

-- Check columns
\d stock_quant

-- Check row count
SELECT COUNT(*) FROM stock_quant;
```

### Step 5: Add to Scheduler (Optional)

If using the scheduler, the new model will be included automatically:

```bash
python -m src.engine.scheduler --interval 15 --run-immediately
```

---

## Type Migration Workflow

The platform automatically migrates column types when PostgreSQL types are too restrictive for Odoo data.

### Automatic Migrations

| From Type | To Type | Trigger Condition |
|-----------|---------|------------------|
| `VARCHAR(n)` where n ≤ 255 | `TEXT` | Odoo char fields often exceed 255 chars |
| `NUMERIC(p,s)` where p < 14 | `NUMERIC(20,4)` | Odoo monetary values can exceed 10 billion |

### Migration Process

```python
# In postgres_client.py - migrate_column_types()
def migrate_column_types(self, model_config):
    """
    For each column:
    1. Compare current PostgreSQL type with expected type
    2. If migration needed, alter column type
    """
    for field in model_config.fields:
        current_type = get_current_type(field.postgres_column)
        expected_type = get_expected_type(field)
        
        if needs_migration(current_type, expected_type):
            alter_column_type(field, expected_type)
```

### Example: VARCHAR → TEXT Migration

**Before:**
```sql
-- PostgreSQL column (created with old config)
name VARCHAR(255)
```

**After:**
```sql
-- Automatic migration
ALTER TABLE res_partner ALTER COLUMN name TYPE TEXT;
```

### Example: Small NUMERIC → Large NUMERIC

**Before:**
```sql
-- Too small for Odoo monetary values
amount_total NUMERIC(12,2)
```

**After:**
```sql
-- Automatic migration
ALTER TABLE res_partner ALTER COLUMN amount_total TYPE NUMERIC(20,4);
```

### Manual Type Specification

For explicit control, specify types in verbose format:

```yaml
models:
  - odoo_model: sale.order
    postgres_table: sale_order
    fields:
      - odoo_field: amount_total
        postgres_column: amount_total
        postgres_type: NUMERIC(20,4)  # Explicit large type
```

### Verifying Migrations

Check migration logs:

```bash
python -m src.main --mode full --log-level DEBUG 2>&1 | grep -i migrate
```

Output:
```
INFO - Column type migrations: {'column': 'name', 'from': 'VARCHAR(255)', 'to': 'TEXT'}
```

---

## Failure Recovery

The platform is designed to handle failures gracefully.

### Scenario 1: Sync Fails Mid-Way

**Problem:** Sync interrupted due to network error or timeout

**Recovery:**
1. Rerun sync - it will resume where it left off
2. Incremental sync will pick up any missed records
3. No data corruption - upsert is idempotent

```bash
# Resume sync
python -m src.main --mode incremental
```

### Scenario 2: Invalid Field Configuration

**Problem:** Configured field doesn't exist in Odoo

**Detection:**
```
WARNING - Field 'old_field' not found on model 'res.partner'. Skipping field.
```

**Recovery:**
1. Field is automatically skipped
2. Sync continues with valid fields
3. Update `models.yaml` to remove invalid field

### Scenario 3: PostgreSQL Type Mismatch

**Problem:** Data too large for column type (e.g., name > 255 chars)

**Detection:**
```
ERROR - Batch upsert failed, retrying individually
```

**Recovery:**
1. Individual records are retried (batch splits)
2. Failed records are logged
3. Platform automatically widens column type
4. On next sync, records are inserted

### Scenario 4: Odoo Field Type Changes

**Problem:** Odoo changes a field's type (e.g., char → many2one)

**Detection:** `fields_get()` returns different type

**Recovery:**
1. Manual intervention required
2. Options:
   - Remove field from config
   - Drop column and re-add with correct type
   - Create new column with different name

### Scenario 5: Primary Key Constraint Missing

**Problem:** Existing table without primary key

**Detection:**
```
WARNING - Table 'res_partner' missing primary key constraint on 'id'. Adding constraint.
```

**Recovery:** Automatic - platform adds constraint:

```sql
ALTER TABLE res_partner ADD CONSTRAINT res_partner_pkey PRIMARY KEY (id);
```

### Scenario 6: Connection Lost During Upsert

**Problem:** Database connection drops mid-batch

**Recovery:**
1. Transaction is rolled back
2. On retry, records are re-upserted
3. No duplicate data (upsert handles this)

### Recovery Checklist

If sync fails:

1. **Check logs** for error details:
   ```bash
   tail -f sync.log
   ```

2. **Verify connections**:
   ```bash
   python -m src.main --validate
   ```

3. **Check sync state**:
   ```bash
   python -m src.main --status
   ```

4. **Reset if needed**:
   ```bash
   python -m src.main --reset --models <model_name>
   python -m src.main --mode full --models <model_name>
   ```

### Preventing Failures

| Practice | Benefit |
|----------|---------|
| Use API keys | More stable than passwords |
| Set appropriate timeouts | Prevents hanging |
| Monitor disk space | Ensures PostgreSQL has room |
| Regular incremental syncs | Smaller batches = less failure risk |

---

## Schema Validation Commands

### Check Current Schema

```bash
# View PostgreSQL table structure
psql -d sync_db -c "\d res_partner"

# View indexes
psql -d sync_db -c "\di" | grep res_partner

# Check column types
psql -d sync_db -c "SELECT column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_name = 'res_partner';"
```

### Verify Sync State

```sql
-- Check sync status
SELECT * FROM sync_state;

-- Check last sync times
SELECT model_name, last_sync_date, record_count, status FROM sync_state;

-- Check sync history
SELECT * FROM sync_history ORDER BY started_at DESC LIMIT 10;
```

### Debug Schema Issues

```bash
# Run with debug logging
python -m src.main --mode full --log-level DEBUG --log-file debug.log

# Check what fields Odoo has
python -m src.utils.config_generator --model res.partner
```
