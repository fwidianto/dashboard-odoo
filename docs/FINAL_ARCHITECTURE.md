# FINAL ARCHITECTURE DOCUMENTATION

**Generated:** 2026-06-17  
**Source:** Verified against actual source code  

---

## CLASS DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────┐
│                            SyncEngine                                │
│  - _error_reporter: ErrorReporter                                    │
│  - _schema_recommender: SchemaRecommender                            │
│  - sync_model(), sync_all()                                          │
└─────────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│   OdooClient    │  │ PostgresClient  │  │    ErrorReporter    │
│                 │  │                │  │                     │
│ - get_model_fields()  │ - upsert()    │  │ - start_batch()    │
│ - search_read()  │ - create_table() │  │ - record_success()  │
│ - count()        │ - table_exists   │  │ - record_failure()  │
└─────────────────┘  └─────────────────┘  │ - get_batch_summary │
                                          └─────────────────────┘
                                                           │
                                                           ▼
                                          ┌─────────────────────────────┐
                                          │      BatchSummary           │
                                          │  (Compatibility Layer)      │
                                          │                             │
                                          │  .errors_by_category        │
                                          │  .errors_by_column          │
                                          │  .data_profiles             │
                                          │  .processed/success/failed  │
                                          └─────────────────────────────┘
                                                           │
                                                           ▼
                                          ┌─────────────────────────────┐
                                          │     SchemaRecommender       │
                                          │                             │
                                          │  - add_batch_summary()      │
                                          │  - generate_recommendations│
                                          │  - generate_migration_sql()│
                                          └─────────────────────────────┘
```

---

## DEPENDENCY GRAPH

```
main.py
  └── SyncEngine
        ├── OdooClient
        ├── PostgresClient
        ├── StateManager
        ├── ErrorReporter
        │     ├── ModelErrorStats
        │     │     ├── RootCauseError
        │     │     └── DataProfile
        │     └── BatchSummary
        └── SchemaRecommender
              └── ModelRecommendation
                   └── ColumnRecommendation
```

---

## API CONTRACT MATRIX

### ErrorReporter (Provider)

| Method/Property | Type | Used By |
|-----------------|------|--------|
| `start_batch(model, table_name)` | method | SyncEngine |
| `end_batch()` | method | SyncEngine |
| `record_success(count)` | method | SyncEngine |
| `record_failure(category, ...)` | method | SyncEngine |
| `record_error(model, table_name, category, ...)` | method | SyncEngine |
| `profile_data(column, type, value)` | method | SyncEngine |
| `get_batch_summary()` | method | SyncEngine, SchemaRecommender |
| `has_errors()` | method | SyncEngine |
| `export_all()` | method | SyncEngine |
| `get_sync_report()` | method | SyncEngine |
| `print_summary()` | method | SyncEngine |

### BatchSummary (Provider)

| Property | Type | Used By |
|----------|------|--------|
| `model` | str | SchemaRecommender |
| `table_name` | str | SchemaRecommender |
| `errors_by_category` | dict | SchemaRecommender |
| `errors_by_column` | dict | SchemaRecommender |
| `data_profiles` | dict | SchemaRecommender |
| `processed` | int | SchemaRecommender |
| `success` | int | SchemaRecommender |
| `failed` | int | SchemaRecommender |
| `error_rate` | float | SchemaRecommender |

### SchemaRecommender (Consumer)

| Method | Expects from Summary |
|--------|---------------------|
| `add_batch_summary()` | model, table_name, errors_by_category, errors_by_column, data_profiles |
| `_analyze_data_too_long()` | errors_by_column, data_profiles |
| `_analyze_numeric_overflow()` | errors_by_column, data_profiles |
| `_analyze_null_constraint()` | errors_by_column, data_profiles |
| `_analyze_data_profiles()` | data_profiles |

---

## CALL FLOW

### Sync Model Flow

```
1. SyncEngine.sync_model(model_config)
   │
   ├─► ErrorReporter.start_batch(model, table)
   │
   ├─► OdooClient.get_model_fields()
   │       └─► Validate fields
   │
   ├─► OdooClient.search_read()
   │       └─► Fetch records in batches
   │
   ├─► For each record:
   │       ├─► PostgresClient.upsert()
   │       │       └─► Error handling
   │       ├─► ErrorReporter.record_success() OR
   │       │       ErrorReporter.record_failure()
   │       └─► ErrorReporter.profile_data()
   │
   ├─► ErrorReporter.end_batch()
   │
   ├─► ErrorReporter.get_batch_summary()
   │       └─► BatchSummary
   │
   ├─► SchemaRecommender.add_batch_summary()
   │
   └─► ErrorReporter.print_summary()
```

---

## ERROR HANDLING FLOW

```
Database Error Occurs
        │
        ▼
PostgresClient.upsert() catches exception
        │
        ▼
Classify error type:
  - DATA_TOO_LONG
  - NUMERIC_OVERFLOW
  - NULL_CONSTRAINT
  - FOREIGN_KEY
  - UNIQUE_CONSTRAINT
  - SCHEMA_ERROR
  - ODOO_DATA_ERROR
  - UNKNOWN
        │
        ▼
ErrorReporter.record_failure(category, record_id, message, column)
        │
        ├─► ModelErrorStats.add_error()
        │       ├─► Increment failed count
        │       ├─► Track errors_by_column[column]++
        │       └─► Store first_root_cause
        │
        └─► Store RootCauseError for export
        │
        ▼
Record committed (continue processing)
        │
        ▼
Batch ends → Generate recommendations
```

---

## SCHEMA EVOLUTION FLOW

```
1. Sync runs with existing schema
         │
         ▼
2. Errors recorded by category and column
         │
         ▼
3. SchemaRecommender analyzes patterns:
   - DATA_TOO_LONG (column) → suggest TEXT
   - NUMERIC_OVERFLOW (column) → suggest larger NUMERIC
   - NULL_CONSTRAINT (column) → suggest DROP NOT NULL
         │
         ▼
4. Generate recommendations:
   - ColumnRecommendation objects
   - SQL ALTER TABLE statements
         │
         ▼
5. Export to:
   - reports/schema_recommendations/recommendations.json
   - reports/schema_recommendations/migration_suggestions.sql
         │
         ▼
6. User applies migrations
```

---

## DATA FLOW

### Error Statistics Flow

```
ErrorReporter
  │
  ├─► model_stats: dict[str, ModelErrorStats]
  │         │
  │         └─► ModelErrorStats
  │               ├─► processed/success/failed
  │               ├─► root_causes: {category: count}
  │               ├─► errors_by_column: {column: count}
  │               └─► data_profiles: {column: DataProfile}
  │
  └─► root_causes: list[RootCauseError]
            ├─► model, table_name
            ├─► record_id
            ├─► error_category
            ├─► error_message
            ├─► column_name
            └─► value_preview
```

---

## FILE OUTPUTS

| File | Format | Content |
|------|--------|---------|
| `reports/errors/summary_*.json` | JSON | Full model statistics |
| `reports/errors/error_report_*.csv` | CSV | Root cause errors |
| `logs/root_causes.json` | JSON | Root cause details |
| `reports/schema_recommendations/recommendations.json` | JSON | Column recommendations |
| `reports/schema_recommendations/migration_suggestions.sql` | SQL | ALTER TABLE statements |

---

## VERIFICATION RESULTS

### API Contract Check

```bash
$ python3 -c "from src.reporting.error_reporter import ErrorReporter, BatchSummary, DataProfile; print('OK')"
OK
```

### SchemaRecommender Integration

```bash
$ python3 -c "
from src.reporting.error_reporter import ErrorReporter, BatchSummary
from src.reporting.schema_recommender import SchemaRecommender
r = ErrorReporter()
r.start_batch('test.model', 'test_table')
# ... record some data ...
batch = r.get_batch_summary()
s = SchemaRecommender()
s.add_batch_summary(batch)  # Should not raise
print('SchemaRecommender accepts BatchSummary')
"
SchemaRecommender accepts BatchSummary
```

### Test Results

```
19 passed, 0 failed
```

---

## CLASS DEFINITIONS

### ErrorReporter

```python
class ErrorReporter:
    model_stats: dict[str, ModelErrorStats]
    root_causes: list[RootCauseError]
    debug_samples: dict[str, list]
    _current_model: Optional[str]
    _current_table: Optional[str]

    def start_batch(model, table_name)
    def end_batch()
    def record_success(count, model=None)
    def record_failure(category, record_id, error_message, column_name, value, model)
    def record_error(model, table_name, category, record_id, error_message, column_name, value, payload)
    def profile_data(column_name, column_type, value)
    def get_batch_summary() -> Optional[BatchSummary]
    def generate_report() -> dict
    def save_report(filename) -> str
    def print_batch_summary()
    def has_errors() -> bool
    def export_all()
    def get_sync_report() -> SyncReport
```

### ModelErrorStats

```python
@dataclass
class ModelErrorStats:
    model: str
    table_name: str
    processed: int
    success: int
    failed: int
    cascade_failures: int
    root_causes: dict  # defaultdict(int)
    errors_by_column: dict  # defaultdict(int)
    data_profiles: dict  # dict[str, DataProfile]
    first_root_cause: Optional[RootCauseError]

    @property error_rate() -> float
    @property errors_by_category() -> dict
    @property failure_categories() -> dict
    def add_success(count)
    def add_error(category, record_id, error_message, column_name, value_preview, payload, is_cascade)
    def add_data_profile(column_name, col_type, value)
```

### BatchSummary

```python
class BatchSummary:
    model: str
    table_name: str
    stats: ModelErrorStats

    @property errors_by_category() -> dict
    @property failure_categories() -> dict
    @property errors_by_column() -> dict
    @property data_profiles() -> dict
    @property processed() -> int
    @property success() -> int
    @property failed() -> int
    @property cascade_failures() -> int
    @property error_rate() -> float
```

### DataProfile

```python
@dataclass
class DataProfile:
    column_name: str
    current_type: str
    max_length_observed: Optional[int]
    max_value_observed: Optional[Decimal]
    null_count: int
    sample_values: list

    def to_dict() -> dict
```

---

## FIXES APPLIED

### Issue 1: Missing `errors_by_column` property
- **Fix:** Added `errors_by_column` dict to `ModelErrorStats`
- **Propagation:** Added property to `BatchSummary`

### Issue 2: Missing `data_profiles` property  
- **Fix:** Added `DataProfile` dataclass
- **Fix:** Added `data_profiles` dict to `ModelErrorStats`
- **Fix:** Added `profile_data()` method implementation
- **Propagation:** Added property to `BatchSummary`

### Issue 3: SchemaRecommender TypeError on None
- **Fix:** Added `is not None` check in `_analyze_data_profiles()`

### Issue 4: Test imports reference non-existent classes
- **Fix:** Rewrote tests to use actual `BatchSummary`, `ModelErrorStats`, `DataProfile`
