# Architecture Documentation

**Generated:** 2026-06-18  
**Source:** Actual codebase inspection

---

## PROJECT STRUCTURE

```
dashboard-odoo/
├── src/
│   ├── main.py                 # Entry point
│   ├── api.py                  # API endpoints
│   ├── clients/
│   │   ├── odoo_client.py     # Odoo XML-RPC client
│   │   └── postgres_client.py # PostgreSQL client
│   ├── engine/
│   │   ├── sync_engine.py     # Main sync orchestrator
│   │   └── scheduler.py       # Scheduling logic
│   ├── models/
│   │   ├── config.py          # ModelConfig, FieldConfig
│   │   └── state.py           # SyncResult, SyncStatus
│   ├── odoo/
│   │   ├── metadata_discovery.py
│   │   ├── schema_validator.py
│   │   └── self_healing.py
│   ├── reporting/
│   │   ├── error_reporter.py  # ErrorReporter
│   │   ├── error_enums.py     # ErrorCategory enum
│   │   └── schema_recommender.py
│   ├── state/
│   │   └── state_manager.py
│   └── utils/
│       ├── config_loader.py
│       ├── logging.py
│       ├── settings.py
│       └── validation.py
├── tests/
├── config/
│   └── models.yaml            # Model definitions
├── docs/
└── reports/
```

---

## SYNC FLOW

```
main.py
  └── SyncEngine.sync_all()
        ├── OdooClient.get_model_fields()
        ├── OdooClient.search_read()
        ├── PostgresClient.upsert()
        └── ErrorReporter.record_*()
```

### Startup Sequence

1. `main.py` parses arguments
2. Creates `SyncEngine` instance
3. Loads `models.yaml` via `ConfigLoader`
4. For each model:
   - `engine.sync_model()`
   - `odoo.get_model_fields()` → validate fields
   - `odoo.search_read()` → fetch records
   - `postgres.upsert()` → write to database
   - `error_reporter.record_*()` → track results

---

## ERROR REPORTING SUBSYSTEM

### ErrorReporter

**File:** `src/reporting/error_reporter.py`

#### Public Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| `start_batch` | `(model, table_name)` | Begin tracking a model batch |
| `end_batch` | `()` | End current batch |
| `record_success` | `(count, model?)` | Record successful records |
| `record_failure` | `(category, record_id, ...)` | Record a failed record |
| `record_error` | `(model, table_name, category, ...)` | Record error with full details |
| `get_batch_summary` | `()` → `Optional[BatchSummary]` | Get summary for SchemaRecommender |
| `generate_report` | `()` → `dict` | Get full summary dict |
| `save_report` | `(filename?)` → `str` | Save JSON report |
| `print_batch_summary` | `()` | Print human-readable summary |
| `print_summary` | `()` | Print full summary |
| `has_errors` | `()` → `bool` | Check if any errors exist |
| `export_all` | `()` | Export JSON, CSV, root_causes |
| `export_json` | `(filename?)` → `str` | Export JSON |
| `export_csv` | `(filename?)` → `str` | Export CSV |
| `export_root_causes` | `(filename?)` → `str` | Export root causes JSON |
| `get_sync_report` | `()` → `SyncReport` | Get sync report object |

#### Internal State

```python
class ErrorReporter:
    model_stats: dict[str, ModelErrorStats]  # Per-model statistics
    root_causes: list[RootCauseError]        # All root cause errors
    debug_samples: dict[str, list]           # Debug info per model
    _current_model: Optional[str]              # Current batch model
    _current_table: Optional[str]             # Current batch table
```

#### Output Files

- `reports/errors/summary_YYYYMMDD_HHMMSS.json` - JSON summary
- `reports/errors/error_report_YYYYMMDD_HHMMSS.csv` - CSV root causes
- `logs/root_causes.json` - Root cause details

---

## MODELERRORSTATS

**File:** `src/reporting/error_reporter.py`

```python
@dataclass
class ModelErrorStats:
    model: str                           # Odoo model name
    table_name: str = ""                  # PostgreSQL table name
    processed: int = 0                    # Total records processed
    success: int = 0                     # Successfully synced
    failed: int = 0                      # Failed (root causes only)
    cascade_failures: int = 0            # TRANSACTION_ABORTED count
    root_causes: dict                    # defaultdict(int) by category
    first_root_cause: Optional[RootCauseError] = None
    
    @property
    def error_rate(self) -> float:       # (failed/processed) * 100
    
    @property
    def errors_by_category(self) -> dict: # dict(root_causes)
    
    @property
    def failure_categories(self) -> dict:  # alias for errors_by_category
    
    def add_success(self, count=1):        # Increment success
    def add_error(self, category, ...):    # Add error
```

---

## BATCHSUMMARY

**Purpose:** Compatibility layer for SchemaRecommender

```python
class BatchSummary:
    def __init__(self, model, table_name, stats):
        self.model = model
        self.table_name = table_name
        self.stats = stats  # ModelErrorStats
    
    @property
    def errors_by_category(self) -> dict:  # → stats.errors_by_category
    @property
    def failure_categories(self) -> dict:   # alias for errors_by_category
    @property
    def processed(self) -> int:
    @property
    def success(self) -> int:
    @property
    def failed(self) -> int:
    @property
    def cascade_failures(self) -> int:
    @property
    def error_rate(self) -> float:
```

---

## SCHEMARECOMMENDER

**File:** `src/reporting/schema_recommender.py`

### Public Methods

| Method | Purpose |
|--------|---------|
| `add_batch_summary(summary)` | Add batch data for analysis |
| `generate_recommendations()` | Generate recommendations |
| `generate_migration_sql()` | Generate ALTER TABLE statements |
| `export()` | Export to JSON/CSV |
| `print_recommendations()` | Print human-readable |

### Required Input

The `add_batch_summary()` method expects a `summary` object with:

```python
summary.model                    # str - Odoo model name
summary.table_name               # str - PostgreSQL table name
summary.errors_by_category       # dict[ErrorCategory, int]
summary.errors_by_column         # dict[str, int]  ← MISSING
summary.data_profiles           # dict[str, DataProfile]  ← MISSING
```

---

## CLASS DEPENDENCY MAP

```
main.py
  └── SyncEngine
        ├── OdooClient
        ├── PostgresClient
        ├── StateManager
        ├── ErrorReporter
        │     └── ModelErrorStats
        │           └── RootCauseError
        └── SchemaRecommender
              └── ColumnRecommendation
                   └── ModelRecommendation
```

### Who Creates What

| Class | Created By |
|-------|------------|
| `SyncEngine` | `main.py` |
| `OdooClient` | `SyncEngine.__init__` |
| `PostgresClient` | `SyncEngine.__init__` |
| `StateManager` | `SyncEngine.__init__` |
| `ErrorReporter` | `SyncEngine.__init__` |
| `SchemaRecommender` | `SyncEngine.__init__` |
| `ModelErrorStats` | `ErrorReporter.get_or_create_stats` |
| `RootCauseError` | `ErrorReporter.record_error` |
| `BatchSummary` | `ErrorReporter.get_batch_summary` |

---

## API CONTRACT AUDIT

### SyncEngine → ErrorReporter Calls

| Call | Status | Notes |
|------|--------|-------|
| `start_batch(model, table_name)` | ✅ | Implemented |
| `record_success(count)` | ✅ | Implemented |
| `record_error(model, table_name, category, ...)` | ✅ | Implemented |
| `profile_data(col, col_type, value)` | ✅ | Placeholder implemented |
| `end_batch()` | ✅ | Implemented |
| `print_batch_summary()` | ✅ | Implemented |
| `get_batch_summary()` | ✅ | Returns BatchSummary |
| `has_errors()` | ✅ | Implemented |
| `export_all()` | ✅ | Implemented |
| `print_summary()` | ✅ | Implemented |
| `get_sync_report()` | ✅ | Returns SyncReport |

### SchemaRecommender Expectations

| Expected | Status | Notes |
|---------|--------|-------|
| `add_batch_summary()` | ✅ | Implemented |
| `summary.errors_by_category` | ✅ | Property exists |
| `summary.errors_by_column` | ❌ | **MISSING from BatchSummary** |
| `summary.data_profiles` | ❌ | **MISSING from BatchSummary** |

---

## KNOWN ISSUES

### CRITICAL: SchemaRecommender API Mismatch

**Problem:** `SchemaRecommender._analyze_data_profiles()` expects:
- `summary.errors_by_column` (dict)
- `summary.data_profiles` (dict of DataProfile objects)

But `BatchSummary` does NOT provide these properties.

**Impact:** Schema recommendations for DATA_TOO_LONG, NUMERIC_OVERFLOW cannot work correctly.

**Fix Required:** Add `errors_by_column` and `data_profiles` to `BatchSummary`.

### Test References Non-Existent Classes

**File:** `tests/test_schema_recommender.py`

References `BatchErrorSummary` and `DataProfile` which don't exist in current codebase.

---

## MISSING FEATURES

### 1. errors_by_column

`SchemaRecommender` uses `summary.errors_by_column` to track failures per column:

```python
# Expected by schema_recommender.py line 93:
for col, failures in summary.errors_by_column.items():
```

**Missing from:** `BatchSummary`, `ModelErrorStats`

### 2. data_profiles

`SchemaRecommender` uses `summary.data_profiles` for type recommendations:

```python
# Expected by schema_recommender.py line 109:
if col in summary.data_profiles:
    profile = summary.data_profiles[col]
```

**Missing:** `DataProfile` class and `data_profiles` property on `BatchSummary`

---

## RECOMMENDED FIXES

### Priority 1: Add errors_by_column

Add to `ModelErrorStats`:
```python
errors_by_column: dict = field(default_factory=lambda: defaultdict(int))
```

Add property to `BatchSummary`:
```python
@property
def errors_by_column(self) -> dict:
    return self.stats.errors_by_column
```

### Priority 2: Add DataProfile class

Create `DataProfile` dataclass and add to `BatchSummary`:
```python
@property
def data_profiles(self) -> dict:
    return getattr(self.stats, 'data_profiles', {})
```

### Priority 3: Update tests

Update `tests/test_schema_recommender.py` to use actual classes.
