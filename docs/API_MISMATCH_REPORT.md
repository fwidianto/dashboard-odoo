# API Mismatch Report

**Generated:** 2026-06-18  
**Source:** Code inspection of src/reporting/

---

## Summary

Critical mismatches found between `SchemaRecommender` expectations and `ErrorReporter`/`BatchSummary` implementation.

---

## Critical Mismatches

### 1. `summary.errors_by_column` - MISSING

**Location:** `src/reporting/schema_recommender.py:93`

**Expected Usage:**
```python
for col, failures in summary.errors_by_column.items():
    if failures > 0:
        # Get current type from data profile
```

**Missing From:**
- `BatchSummary` class
- `ModelErrorStats` class

**Impact:** DATA_TOO_LONG recommendations cannot work

---

### 2. `summary.data_profiles` - MISSING

**Location:** `src/reporting/schema_recommender.py:109, 140, 172`

**Expected Usage:**
```python
if col in summary.data_profiles:
    profile = summary.data_profiles[col]
    current_type = profile.current_type
    max_value = profile.max_value_observed
```

**Expected Type:** `dict[str, DataProfile]`

**Missing:**
- `DataProfile` class definition
- `data_profiles` property on `BatchSummary`
- `data_profiles` attribute on `ModelErrorStats`

**Impact:** Cannot generate accurate type recommendations

---

### 3. `DataProfile` Class - MISSING

**Expected Structure (from tests):**
```python
class DataProfile:
    column_name: str
    current_type: str
    max_length_observed: Optional[int]
    max_value_observed: Optional[Decimal]
    null_count: int
    sample_values: list
```

**Referenced By:**
- `tests/test_schema_recommender.py`
- `src/reporting/schema_recommender.py`

---

### 4. `BatchErrorSummary` Class - OBSOLETE

**Problem:** Tests reference `BatchErrorSummary` which doesn't exist.

**Actual Class:** `BatchSummary`

**Action:** Tests need to be updated or `BatchErrorSummary` needs to be created as alias.

---

## Affected Files

### Source Files

| File | Issue |
|------|-------|
| `src/reporting/schema_recommender.py` | Expects `errors_by_column`, `data_profiles` |
| `src/reporting/error_reporter.py` | Missing `errors_by_column`, `data_profiles` |
| `tests/test_schema_recommender.py` | References `BatchErrorSummary`, `DataProfile` |

### Output Files Generated

| File | Contains |
|------|----------|
| `reports/errors/summary_*.json` | Model stats without `errors_by_column` |
| `logs/root_causes.json` | Root causes without column data |

---

## Root Cause Analysis

The error reporting subsystem was redesigned to focus on **root cause detection** and **cascade failure tracking**, but the `SchemaRecommender` was not updated to match the new data model.

Old model:
- `errors_by_category` - Error counts by type
- `errors_by_column` - Error counts by column
- `data_profiles` - Data type statistics

New model:
- `root_causes` - Only first error per category per model
- `cascade_failures` - TRANSACTION_ABORTED errors tracked separately

The SchemaRecommender still expects the old data model.

---

## Recommended Fixes

### Fix 1: Add errors_by_column to ModelErrorStats

**File:** `src/reporting/error_reporter.py`

Add to `ModelErrorStats`:
```python
errors_by_column: dict = field(default_factory=lambda: defaultdict(int))
```

### Fix 2: Create DataProfile class

**File:** `src/reporting/error_reporter.py`

```python
@dataclass
class DataProfile:
    column_name: str
    current_type: str
    max_length_observed: Optional[int] = None
    max_value_observed: Optional[Decimal] = None
    null_count: int = 0
    sample_values: list = field(default_factory=list)
```

### Fix 3: Add data_profiles to ModelErrorStats

**File:** `src/reporting/error_reporter.py`

```python
data_profiles: dict = field(default_factory=dict)
```

### Fix 4: Add properties to BatchSummary

```python
@property
def errors_by_column(self) -> dict:
    return self.stats.errors_by_column

@property
def data_profiles(self) -> dict:
    return self.stats.data_profiles
```

### Fix 5: Update record_error to track errors_by_column

```python
def record_error(self, ...):
    # Existing code...
    
    # Track by column
    if column_name:
        stats.errors_by_column[column_name] += 1
```

---

## Test Failures

Running tests will reveal these mismatches:

```
tests/test_schema_recommender.py::TestSchemaRecommender::test_add_batch_summary_data_too_long
  FAILED - AttributeError: 'BatchSummary' object has no attribute 'errors_by_column'

tests/test_schema_recommender.py::TestSchemaRecommender::test_add_batch_summary_numeric_overflow
  FAILED - AttributeError: 'BatchSummary' object has no attribute 'data_profiles'
```

---

## Verification Commands

```bash
# Check if BatchSummary has errors_by_column
python3 -c "from src.reporting.error_reporter import BatchSummary; print(hasattr(BatchSummary, 'errors_by_column'))"

# Check if DataProfile exists
python3 -c "from src.reporting.error_reporter import DataProfile; print('exists')"

# Run schema recommender tests
python3 -m pytest tests/test_schema_recommender.py -v
```

---

## Files to Modify

1. `src/reporting/error_reporter.py`
   - Add `DataProfile` dataclass
   - Add `errors_by_column` to `ModelErrorStats`
   - Add `data_profiles` to `ModelErrorStats`
   - Add properties to `BatchSummary`

2. `tests/test_schema_recommender.py`
   - Use `BatchSummary` instead of `BatchErrorSummary`
   - Use `DataProfile` for profiles
