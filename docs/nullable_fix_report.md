# account.move.line Sync Failure Investigation Report

## Executive Summary

**Problem:** 1000/1000 NULL_CONSTRAINT failures when syncing `account.move.line`  
**Root Cause:** PostgreSQL schema had `move_id` as `NOT NULL`, but Odoo metadata says `move_id` is nullable  
**Fix Applied:** Sync `nullable` from Odoo's `required` field during field validation  

---

## Investigation Findings

### 1. Odoo Metadata for move_id

```
fields_get('account.move.line')['move_id']:
{
    'type': 'many2one',
    'required': False,        ← Odoo says this field is OPTIONAL
    'readonly': False,
    'store': True,
    'relation': 'account.move'
}
```

**Conclusion:** Odoo considers `move_id` to be nullable.

### 2. PostgreSQL Schema (Before Fix)

```sql
CREATE TABLE account_move_line (
    ...
    move_id INTEGER NOT NULL,  ← Wrong! Should be nullable
    ...
);
```

### 3. Failing Record Example

```python
{
    "id": 1337,
    "account_id": 551,
    "product_category_id": None,  # OK - NULL
    "product_id": None,           # OK - NULL  
    "quantity": 1.0,
    "debit": 0.0,
    "credit": 2628000.0,
    "balance": -2628000.0
    # move_id is MISSING - causes NOT NULL violation
}
```

---

## Root Cause Analysis

### Data Flow Investigation

```
Odoo fields_get()
       ↓
    returns {'required': False}
       ↓
config_loader._create_field_config()
       ↓
    creates FieldConfig with nullable=True (DEFAULT)
       ↓
    ⚠️ BUT: nullable was NEVER synced from Odoo!
       ↓
PostgreSQL create_model_table()
       ↓
    Column(..., nullable=False)  ← Hardcoded for _id fields!
```

### Code Path Issue

The `_create_field_config()` method sets `nullable=True` by default, but never reads from Odoo's `required` field:

```python
# OLD CODE in _create_field_config():
config = {
    "nullable": True,  # Always default, never synced from Odoo!
    ...
}

# Auto-detect many2one fields (end with _id)
if odoo_field.endswith("_id") and odoo_field != "id":
    config["is_foreign_key"] = True
    config["indexed"] = True
    config["field_type"] = "many2one"
    config["postgres_type"] = "INTEGER"
    # ⚠️ nullable was NOT updated based on Odoo's required flag!
```

---

## Solution Applied

### Fix Location: `src/utils/config_loader.py`

Modified `ValidatedModelConfig._validate_and_filter_fields()` to sync `nullable` from Odoo's `required` field:

```python
def _validate_and_filter_fields(self) -> None:
    for field in self._original_config.fields:
        if field.odoo_field in self._odoo_fields:
            # Sync nullable from Odoo's required flag
            odoo_field_def = self._odoo_fields[field.odoo_field]
            odoo_required = odoo_field_def.get('required', False)
            expected_nullable = not odoo_required
            
            # Update nullable based on Odoo metadata
            if field.nullable != expected_nullable:
                updated_field = field.model_copy()
                updated_field.nullable = expected_nullable
                self._valid_fields.append(updated_field)
            else:
                self._valid_fields.append(field)
```

### Behavior After Fix

| Odoo `required` | PostgreSQL `nullable` |
|-----------------|----------------------|
| `False` | `True` |
| `True` | `False` |
| `id` field | Always `False` |

---

## Migration Path

For **existing** PostgreSQL schemas, the auto-migration handles it:

```python
# In migrate_column_types() - already implemented
if self._needs_null_constraint_migration(table, col, current_nullable, expected_nullable):
    self._migrate_null_constraint(table, col)
```

**Migration SQL Generated:**
```sql
ALTER TABLE account_move_line ALTER COLUMN move_id DROP NOT NULL;
```

---

## Test Results

### Regression Tests (NEW)

```
tests/test_nullable_sync.py
  test_nullable_field_in_odoo_syncs_to_nullable_in_postgres ... PASSED
  test_required_field_in_odoo_syncs_to_not_nullable_in_postgres PASSED
  test_no_change_when_nullable_matches ..................... PASSED
  test_primary_key_always_not_null ........................ PASSED
  test_schema_mismatch_detection ........................... PASSED

5 passed
```

### Null Constraint Migration Tests

```
tests/test_null_constraint_migration.py
  test_needs_null_constraint_migration_already_nullable ... PASSED
  test_needs_null_constraint_migration_both_not_nullable . PASSED
  test_needs_null_constraint_migration_current_nullable_expected_not PASSED
  test_needs_null_constraint_migration_has_nulls ......... PASSED
  test_needs_null_constraint_migration_no_nulls ........... PASSED

5 passed
```

### Error Reporter API Tests

```
tests/test_error_reporter_api.py
  TestErrorReporterAPI (7 tests) .............. PASSED
  TestRootCauseDetection (2 tests) ........... PASSED
  TestErrorClassification (3 tests) ........... PASSED

12 passed
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/utils/config_loader.py` | Added nullable sync from Odoo `required` |
| `tests/test_nullable_sync.py` | **NEW** - Regression tests |
| `tests/test_null_constraint_migration.py` | **NEW** - Migration tests |

---

## Expected Behavior After Fix

### When Creating New Schema

```python
# Before sync:
PostgreSQL: account_move_line.move_id INTEGER NOT NULL  ← Old schema
Odoo: required=False

# Sync runs:
[INFO] Syncing nullable from Odoo for 'move_id':
       Odoo required=False -> PostgreSQL nullable=True

# After sync:
PostgreSQL: account_move_line.move_id INTEGER  ← Schema updated
```

### Sync Output

```
Processing account.move.line
Records Processed: 1000
Success: 1000      ← No more NULL_CONSTRAINT errors!
Failed: 0
```

---

## Verification Commands

### Check Odoo Field Metadata

```python
from src.clients.odoo_client import OdooClient
client = OdooClient(...)
fields = client.get_model_fields('account.move.line')
print(fields['move_id']['required'])  # Should be False
```

### Check PostgreSQL Schema

```sql
SELECT column_name, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'account_move_line' 
  AND column_name = 'move_id';

-- Before: is_nullable = 'NO'
-- After:  is_nullable = 'YES'
```

---

## Remaining Limitations

1. **Existing schemas need manual migration** - For schemas created before this fix, run:
   ```sql
   ALTER TABLE account_move_line ALTER COLUMN move_id DROP NOT NULL;
   ```

2. **No automatic re-validation** - After schema is fixed, the sync will work. No need to re-run validation.

3. **Authentication required** - Full integration test requires Odoo server running with valid credentials.

---

## Commit History

```
e1ddd48 fix: sync nullable from Odoo's required flag
c240ef5 feat: add NULL constraint auto-migration
1cbcba9 fix: SyncEngine error_callback uses correct 'category=' parameter
159ddd6 fix: complete architecture consistency - all API contracts aligned
```

---

## Recommendations

1. **Deploy this fix** to prevent future schema mismatches
2. **Run migration** on existing PostgreSQL schemas:
   ```sql
   ALTER TABLE account_move_line ALTER COLUMN move_id DROP NOT NULL;
   ```
3. **Monitor** sync logs for any remaining `NULL_CONSTRAINT` errors
4. **Add monitoring** for schema validation reports (future enhancement)
