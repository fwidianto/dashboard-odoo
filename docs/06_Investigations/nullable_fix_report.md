# account.move.line Sync Failure Investigation Report

## Executive Summary

**Problem:** 1000/1000 NULL_CONSTRAINT failures when syncing `account.move.line`  
**Root Cause:** `_needs_null_constraint_migration()` only triggered migration if **existing NULLs** were in data  
**Fix Applied:** Corrected migration logic to always migrate NOT NULL→NULL when Odoo says field is optional

---

## Investigation Findings

### Task 1: Verify Odoo field metadata for move_id
✅ **PASSED** - Odoo's `fields_get()` correctly returns:
```python
{
    "move_id": {
        "type": "many2one",
        "required": False,  # Field is OPTIONAL
        "readonly": False,
        "store": True,
        "relation": "account.move"
    }
}
```

Configuration loader correctly maps this to `nullable=True` (line 819 in `config_loader.py`).

### Task 2: Verify move_id is included in search_read()
✅ **PASSED** - `move_id` is included in Odoo's record output and transformation preserves it.

### Task 3: Verify move_id is NOT dropped during transformation
✅ **PASSED** - The `_transform_records` method correctly handles all valid fields.

### Task 4: Compare Odoo field metadata vs PostgreSQL schema
❌ **FOUND THE BUG** - In `postgres_client.py`:

---

## Root Cause Analysis

### The Bug: Incorrect Migration Logic

**File:** `src/clients/postgres_client.py`

**BEFORE (Buggy):**
```python
def _needs_null_constraint_migration(
    self,
    table_name: str,
    column_name: str,
    current_nullable: bool,
    expected_nullable: bool,
) -> bool:
    """Check if NULL constraint needs to be relaxed."""
    if current_nullable or not expected_nullable:
        return False

    # BUG: Only returns True if there are EXISTING NULLs in the data
    with self.engine.connect() as conn:
        result = conn.execute(
            __import__('sqlalchemy').text(
                f'SELECT COUNT(*) FROM "{table_name}" WHERE "{column_name}" IS NULL'
            )
        )
        null_count = result.scalar()
        return null_count > 0  # <-- Wrong!
```

**This logic is incorrect because:**
1. If Odoo says a field is optional, PostgreSQL **should allow NULLs**
2. Even if no NULLs exist **yet**, future syncs will have NULLs
3. The `NOT NULL` constraint was blocking valid data from syncing

**AFTER (Fixed):**
```python
def _needs_null_constraint_migration(
    self,
    table_name: str,
    column_name: str,
    current_nullable: bool,
    expected_nullable: bool,
) -> bool:
    """
    Check if NULL constraint needs to be migrated.
    
    Migration is needed when:
    - current_nullable=False (PostgreSQL has NOT NULL)
    - expected_nullable=True (Odoo says field is optional/nullable)
    """
    # Migration needed when: current is NOT NULL but should be nullable
    if not current_nullable and expected_nullable:
        self._logger.info(
            "NULL constraint mismatch detected",
            table=table_name,
            column=column_name,
            current_nullable=False,
            expected_nullable=True,
            reason="Odoo field is optional but PostgreSQL has NOT NULL constraint",
        )
        return True
    
    # No migration needed if:
    # - Already nullable (current_nullable=True)
    # - Should be NOT NULL (expected_nullable=False) - stricter is fine
    return False
```

---

## Additional Fixes Applied

### Fix 1: Added Schema Validation Method

**File:** `src/clients/postgres_client.py` (lines 728-834)

Added `validate_schema_against_odoo()` method that:
- Compares Odoo `required` flag vs PostgreSQL `nullable` flag
- Generates mismatch report with SQL fix statements
- Logs warnings for any schema mismatches

### Fix 2: Integrated Validation into Sync Engine

**File:** `src/engine/sync_engine.py` (lines 138-156)

Added validation call during `initialize()` to generate mismatch reports before sync.

---

## Migration Path

### Immediate Fix for account_move_line.move_id

```sql
ALTER TABLE account_move_line ALTER COLUMN move_id DROP NOT NULL;
```

The existing `scripts/repair_schema.py` already supports this via `--from-report` flag.

---

## Test Results

### New Regression Tests (12 total - all passing)

```
tests/test_null_constraint_migration.py
  test_needs_null_constraint_migration_already_nullable ... PASSED ✅
  test_needs_null_constraint_migration_both_not_nullable . PASSED ✅
  test_needs_null_constraint_migration_current_nullable_expected_not PASSED ✅
  test_move_id_migration_from_not_null_to_nullable ....... PASSED ✅ (NEW)
  test_required_field_no_migration_needed ................ PASSED ✅ (NEW)
  test_nullable_field_already_nullable .................... PASSED ✅ (NEW)
  test_detect_move_id_mismatch ........................... PASSED ✅ (NEW)

tests/test_nullable_sync.py
  test_nullable_field_in_odoo_syncs_to_nullable_in_postgres ... PASSED ✅
  test_required_field_in_odoo_syncs_to_not_nullable_in_postgres . PASSED ✅
  test_no_change_when_nullable_matches ........................ PASSED ✅
  test_primary_key_always_not_null ............................ PASSED ✅
  test_schema_mismatch_detection ................................ PASSED ✅
```

---

## Files Changed

| File | Change |
|------|--------|
| `src/clients/postgres_client.py` | Fixed `_needs_null_constraint_migration()`, added `validate_schema_against_odoo()` |
| `src/engine/sync_engine.py` | Integrated schema validation into `initialize()` |
| `tests/test_null_constraint_migration.py` | Added 4 regression tests for bug fix |

---

## Expected Behavior After Fix

### Sync Output

```
INFO - NULL constraint mismatch detected
INFO - table=account_move_line, column=move_id, current_nullable=False, expected_nullable=True
INFO - Migrating NULL constraint
INFO - table=account_move_line, column=move_id, from_constraint=NOT NULL, to_constraint=NULL

Processing account.move.line
Records Processed: 1000
Success: 1000      ← No more NULL_CONSTRAINT errors!
Failed: 0
```

---

## Prevention

To prevent similar issues in the future:

1. **Schema validation** runs automatically during sync engine initialization
2. **Mismatch reports** are logged before any sync begins
3. **Migration** is automatic when schema mismatches are detected

The fix ensures PostgreSQL schema always reflects Odoo's `required` flag:
- `required=True` in Odoo → `NOT NULL` in PostgreSQL
- `required=False` in Odoo → `NULL` in PostgreSQL

---

## Recommendations

1. **Deploy this fix** to prevent future schema mismatches
2. **Run migration** on existing PostgreSQL schemas:
   ```sql
   ALTER TABLE account_move_line ALTER COLUMN move_id DROP NOT NULL;
   ```
3. **Monitor** sync logs for any remaining `NULL_CONSTRAINT` errors
