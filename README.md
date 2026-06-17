# Odoo to PostgreSQL Synchronization Platform

A production-ready, **model-based** synchronization platform that bridges Odoo ERP with PostgreSQL databases. Built with Python, SQLAlchemy, and designed for extensibility.

## 🎯 NEW: Model-Based Architecture

**No more manual field definitions!** Simply add any Odoo model name to `models.yaml` and all fields are automatically discovered and synchronized.

```yaml
# That's it! All fields are auto-detected from Odoo
models:
  - res.partner
  - sale.order
  - product.product
  - stock.move
```

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Odoo and PostgreSQL settings
```

### 3. Add Models to Sync

Edit `config/models.yaml` - just add model names:

```yaml
models:
  - res.partner
  - sale.order
  - product.product
  - account.move
```

### 4. Run Sync

```bash
# Full sync (first time)
python -m src.main --mode full

# Incremental sync (subsequent runs)
python -m src.main --mode incremental
```

---

## Key Features

### ✅ Model-Based Auto-Discovery
- Add any Odoo model by name only
- ALL fields automatically discovered via `fields_get()`
- No need to define fields manually

### ✅ Automatic Schema Evolution
- Tables created automatically
- New columns added when Odoo adds fields
- Column types migrated when needed (VARCHAR→TEXT, etc.)

### ✅ Custom Field Support
- All `x_*` custom fields automatically synced
- No additional configuration needed

### ✅ Full Sync Modes
- **Full sync**: Syncs all records
- **Incremental sync**: Only syncs changed records (via `write_date`)

### ✅ Production Ready
- Strict read-only mode (Odoo never modified)
- UPSERT with accurate insert/update tracking
- Batch processing for large datasets
- Comprehensive logging and error handling

### ✅ Self-Healing Engine
- **Automatic error detection**: Root cause analysis vs cascading errors
- **Record isolation**: Bad records don't stop the batch
- **Auto-repair**: Missing columns, type migrations, NULL constraints
- **Adaptive learning**: Remembers fixes for future runs
- **Production-safe**: Never drops tables, columns, or data

### ✅ Comprehensive Error Reporting
- **Error classification**: SCHEMA_ERROR, DATA_TOO_LONG, NUMERIC_OVERFLOW, etc.
- **Error aggregation**: Batch summaries with counts by category
- **Sample records**: Up to 100 examples per error type
- **Health reports**: Sync status, error rates, top failure causes
- **Schema drift reports**: New/missing columns detected

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MODEL-BASED SYNC FLOW                        │
└─────────────────────────────────────────────────────────────────┘

   ┌─────────────┐
   │ models.yaml │
   │ (just names)│
   └──────┬──────┘
          │
          ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    ConfigLoader                              │
   │                                                              │
   │  1. For each model:                                        │
   │     └─→ fields_get() ─→ Discover ALL fields               │
   │                                                              │
   │  2. Auto-generate field configs:                           │
   │     └─→ Type mapping, indexes, primary keys               │
   │                                                              │
   │  3. Output: Complete ModelConfig with all fields            │
   └─────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    SyncEngine                                 │
   │                                                              │
   │  1. ensure_table_schema()                                  │
   │     ├─→ Create table if not exists                        │
   │     ├─→ Add new columns                                    │
   │     ├─→ Migrate column types                               │
   │     └─→ Create indexes                                     │
   │                                                              │
   │  2. Fetch data from Odoo                                   │
   │     └─→ search_read() with batching                        │
   │                                                              │
   │  3. Upsert to PostgreSQL                                    │
   │     └─→ INSERT ON CONFLICT DO UPDATE                        │
   │                                                              │
   │  4. Update sync state                                       │
   └─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Purpose |
|-----------|---------|
| `config_loader.py` | Auto-discovers fields from Odoo via `fields_get()` |
| `sync_engine.py` | Orchestrates sync with schema evolution |
| `odoo_client.py` | Read-only XML-RPC client |
| `postgres_client.py` | Schema management and upsert operations |
| `state_manager.py` | Tracks sync state for incremental sync |
| `self_healing.py` | Automatic error detection and repair |
| `error_reporter.py` | Error classification and reporting |
| `metadata_discovery.py` | Odoo schema introspection |
| `schema_validator.py` | Validation pipeline and health reports |

---

## Configuration

### Environment Variables

```env
ODOO_URL=http://localhost:8069
ODOO_DB=odoo_db
ODOO_USERNAME=admin
ODOO_API_KEY=your_api_key

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sync_db
POSTGRES_USER=sync_user
POSTGRES_PASSWORD=password

SYNC_BATCH_SIZE=1000
SYNC_MODE=incremental
```

### YAML Configuration Formats

#### 1. Model-Only (Recommended)

Just list model names - everything is auto-detected:

```yaml
models:
  - res.partner
  - sale.order
  - product.product
```

#### 2. Model with Options

Add customizations while auto-detecting fields:

```yaml
models_with_options:
  - odoo_model: sale.order
    postgres_table: my_sales
    deletion_strategy: soft_delete
    
  - odoo_model: product.product
    exclusions:
      - image_1920    # Skip large binary
      - image_1024
```

#### 3. Legacy Format (Still Supported)

Explicit field definitions:

```yaml
legacy_models:
  - odoo_model: stock.move
    postgres_table: stock_move
    fields:
      - id
      - name
      - product_id
        indexed: true
```

---

## Sync Modes

### Full Sync

```bash
python -m src.main --mode full
```

- Ignores previous sync state
- Fetches ALL records from Odoo
- Creates tables and columns if needed

### Incremental Sync

```bash
python -m src.main --mode incremental
```

- Uses `write_date >= last_sync_date` filter
- Only syncs changed records
- Much faster for subsequent syncs

---

## Schema Evolution

The platform automatically handles Odoo schema changes:

### What Happens Automatically

| Odoo Change | PostgreSQL Action |
|-------------|-------------------|
| New field added | Column automatically created |
| Field type changed | Column type migrated |
| Field renamed | (Not detected - rename handled manually) |
| Field deleted | Column remains (no auto-drop) |

---

## Self-Healing Engine

The platform includes a self-healing synchronization engine that automatically detects, classifies, isolates, repairs, and recovers from PostgreSQL errors.

### How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│  Exception Occurs                                                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 1: Root Cause Detection                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ find_root_cause() → RootCause                                 │  │
│  │                                                               │  │
│  │ • UNDEFINED_COLUMN (42703) - Column missing                   │  │
│  │ • STRING_DATA_RIGHT_TRUNCATION (22001) - VARCHAR overflow     │  │
│  │ • NUMERIC_VALUE_OUT_OF_RANGE (22003) - NUMERIC overflow       │  │
│  │ • NOT_NULL_VIOLATION (23502) - NULL in NOT NULL column        │  │
│  │ • DATATYPE_MISMATCH (42804) - Wrong type                      │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 2: Savepoint-Based Isolation                                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ for record in records:                                         │  │
│  │     SAVEPOINT sp_{hash}                                       │  │
│  │     try: upsert()                                             │  │
│  │     except: ROLLBACK TO SAVEPOINT  ← Isolated failure         │  │
│  │     finally: RELEASE SAVEPOINT                                │  │
│  │                                                               │  │
│  │ Result: Bad records SKIPPED, good records CONTINUE            │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 3-5: Automatic Repair                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ UNDEFINED_COLUMN  → ADD COLUMN IF NOT EXISTS                  │  │
│  │ STRING_TRUNCATION → ALTER TYPE → TEXT                         │  │
│  │ NUMERIC_OVERFLOW  → ALTER TYPE → NUMERIC(30,10)               │  │
│  │ NOT_NULL_VIOLATION → DROP NOT NULL (if not required)          │  │
│  │                                                               │  │
│  │ Then: RETRY RECORD (max 3 attempts)                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 6: Adaptive Learning                                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ sync_error_patterns table:                                    │  │
│  │ model + field + error_type → fix_applied                      │  │
│  │                                                               │  │
│  │ Next sync: Fix applied proactively, no error needed           │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Before vs After

| Scenario | Before | After |
|----------|--------|-------|
| 17,536 records, 36 bad | 80 success, 17,456 failed | 17,500 success, 36 failed |
| Missing column | Sync stops, manual ALTER | Auto ADD COLUMN, retry |
| VARCHAR overflow | 1000 records fail | Auto → TEXT, retry all |
| NULL constraint | Batch aborts | DROP NOT NULL, retry |
| Unknown error | No diagnostics | Full trace saved |

### Production Safety Rules

| Operation | Auto-Execute | Forbidden |
|-----------|-------------|-----------|
| CREATE TABLE | ✅ | ❌ |
| ADD COLUMN | ✅ | ❌ |
| ALTER COLUMN TYPE | ✅ | ❌ |
| DROP NOT NULL | ✅ | ❌ |
| CREATE INDEX | ✅ | ❌ |
| DROP TABLE | ❌ | ❌ |
| DROP COLUMN | ❌ | ❌ |
| DELETE DATA | ❌ | ❌ |
| TRUNCATE TABLE | ❌ | ❌ |

### Error Reports

Generated reports in `reports/` directory:

| Report | Contents |
|--------|----------|
| `sync_health_report_TIMESTAMP.txt` | Success/failure rates, error breakdown |
| `error_report_TIMESTAMP.csv` | All errors with details |
| `summary_TIMESTAMP.json` | Machine-readable summary |
| `self_healing/repair_report_*.json` | Repairs made during sync |
| `self_healing/error_samples_*.json` | Up to 100 samples per error type |
| `self_healing/learned_patterns_*.json` | Learned fix patterns |

### Type Mapping

| Odoo Type | PostgreSQL Type | Notes |
|-----------|-----------------|-------|
| integer, bigint | BIGINT | No overflow for large IDs |
| float, monetary | NUMERIC(30,10) | Handles 17762630700.00 |
| char, text, html, selection | TEXT | No 255 char limit |
| boolean | BOOLEAN | |
| date | DATE | |
| datetime | TIMESTAMP | |
| many2one | BIGINT | Foreign key as ID |
| one2many, many2many | JSONB | Stored as JSON array |
| binary | TEXT | Base64 encoded |

---

## Adding New Models

### Step 1: Add Model to YAML

```yaml
models:
  - existing.model
  - new.model       # Just add the name!
```

### Step 2: Run Sync

```bash
python -m src.main --mode full
```

### Step 3: Done!

- Table created automatically
- All fields discovered
- Data synced

---

## Custom Fields

Custom fields (`x_*`) are automatically detected and synced:

### Example

If Odoo has a custom field `x_customer_tier` on `res.partner`:

```yaml
models:
  - res.partner    # x_customer_tier automatically included!
```

### Excluding Custom Fields

```yaml
models_with_options:
  - odoo_model: res.partner
    exclusions:
      - x_internal_field    # Skip specific custom field
```

---

## Supported Models

Pre-configured models in `config/models.yaml`:

| Category | Models |
|----------|--------|
| **Core** | res.partner, product.template, product.product |
| **Sales** | sale.order, sale.order.line |
| **Purchase** | purchase.order, purchase.order.line |
| **Accounting** | account.move, account.move.line, account.payment |
| **Stock** | stock.move, stock.move.line, stock.quant |
| **Manufacturing** | mrp.production |
| **Approvals** | approval.request, approval.product.line |

---

## Running the Project

### CLI Commands

```bash
# Validate configuration
python -m src.main --validate

# Full sync
python -m src.main --mode full

# Incremental sync
python -m src.main --mode incremental

# Sync specific models
python -m src.main --models res.partner sale.order

# Check status
python -m src.main --status

# Reset state (force full re-sync)
python -m src.main --reset --models res.partner
```

### Scheduler

```bash
# Run scheduler with 15-min incremental syncs
python -m src.engine.scheduler --interval 15 --run-immediately
```

---

## REST API

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/sync-status` | Sync status |
| GET | `/sync-history` | Sync history |
| POST | `/sync` | Trigger sync |
| POST | `/sync/{model}` | Sync model |
| POST | `/reset` | Reset state |
| GET | `/models` | List models |
| POST | `/scheduler/start` | Start scheduler |
| POST | `/scheduler/stop` | Stop scheduler |

---

## Migration Guide

### From Field-Based to Model-Based

**Before (old way):**
```yaml
models:
  - odoo_model: res.partner
    postgres_table: res_partner
    fields:
      - id
      - name
      - email
      - phone
```

**After (new way):**
```yaml
models:
  - res.partner    # Just the model name!
```

**Result:** All fields (including custom fields) are automatically discovered.

### Benefits of Model-Based

1. **Less configuration** - No need to list fields
2. **Future-proof** - New Odoo fields automatically added
3. **Custom fields** - All `x_*` fields included automatically
4. **Fewer errors** - No mismatched field definitions

---

## Known Limitations

| Limitation | Workaround |
|-----------|------------|
| One2many fields | Stored as JSONB, synced automatically |
| Many2many fields | Stored as JSONB, synced automatically |
| Binary fields | Base64 encoded as TEXT |
| Single Odoo instance | Run multiple instances |

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test modules
python -m pytest tests/test_self_healing.py -v
python -m pytest tests/test_metadata_discovery.py -v
python -m pytest tests/test_error_reporting.py -v
python -m pytest tests/test_sync_engine.py -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

### Test Results

| Test Module | Tests | Status |
|-------------|-------|--------|
| `test_self_healing.py` | 33 | ✅ All passing |
| `test_metadata_discovery.py` | 19 | ✅ All passing |
| `test_error_reporting.py` | 37 | ✅ All passing |
| `test_schema_recommender.py` | 19 | ✅ All passing |
| `test_sync_engine.py` | 17 | ✅ All passing |
| **Total** | **125+** | ✅ **All passing** |

---

## Production Hardening

This section documents production-readiness features for running against production databases.

### PostgreSQL Identifier Limits

PostgreSQL restricts identifier names to **63 characters maximum**. The platform automatically handles this through centralized identifier generation:

#### Identifier Generation Strategy

The platform uses a deterministic hash-based strategy to ensure:

- **Maximum 63 characters** for all identifiers
- **Collision-safe** hash suffixes
- **Deterministic output** (same input always produces same output)
- **Readable prefixes** for debugging

```python
from src.utils.identifier import generate_safe_identifier

# Example: Long field that would exceed 63 chars
field = "x_studio_approval_request_receipt_location"
table = "purchase_order_line"

# Generates safe identifier with hash suffix
index_name = generate_safe_identifier("idx", table, field)
# Result: 'idx_purchase_order_line_x_studio_appr_a1b2c3d4'
```

#### Available Functions

| Function | Purpose |
|----------|---------|
| `generate_safe_identifier()` | Main function for custom identifiers |
| `generate_table_name()` | Generate safe table names |
| `generate_column_name()` | Generate safe column names |
| `generate_index_name()` | Generate safe index names |
| `generate_primary_key_name()` | Generate safe PK constraint names |
| `generate_foreign_key_name()` | Generate safe FK constraint names |
| `validate_identifier()` | Validate any identifier |

#### Identifier Format

```
{prefix}_{table}_{column}_{hash}
```

Where:
- `prefix`: Type identifier (idx, fk, uq, ck, seq)
- `table`: Truncated table name
- `column`: Truncated column name
- `hash`: 8-character deterministic hash

### Schema Evolution Strategy

The platform handles schema evolution automatically:

| Scenario | Action |
|----------|--------|
| New field added to Odoo | Column automatically created |
| VARCHAR too small | Migrated to TEXT |
| NUMERIC precision too low | Migrated to NUMERIC(30,10) |
| Field renamed in Odoo | New column created (old remains) |
| Field deleted in Odoo | Column retained (no data loss) |

### Custom Odoo Field Handling

#### x_studio Fields

All `x_studio_*` custom fields are automatically handled:

- **Long field names**: Truncated with hash suffix
- **Special characters**: Sanitized to underscores
- **Index generation**: Collision-safe with deterministic hashes

Example:
```
Odoo field: x_studio_approval_request_receipt_location
Generated column: x_studio_approval_request_receipt_location
Generated index: idx_purchase_order_line_x_studio_appr_a1b2c3d4
```

#### Nested Custom Fields

Very long field names are handled with truncation:

```
Original: x_studio_custom_very_long_field_name_that_exceeds_limit
Truncated: x_studio_custom_very_long_field_name_t_a1b2c3d4
```

### Type Safety

#### Numeric Fields (MONETARY/FLOAT)

Odoo monetary fields can hold values exceeding 100 billion:

| Odoo Type | PostgreSQL Type | Precision |
|-----------|----------------|-----------|
| monetary | NUMERIC(20,4) | Up to 100 trillion |
| float | NUMERIC(20,4) | Up to 100 trillion |

#### Text Fields

All VARCHAR fields are mapped to TEXT to avoid truncation:

| Odoo Type | PostgreSQL Type | Notes |
|-----------|----------------|-------|
| char | TEXT | No 255 char limit |
| text | TEXT | No limit |
| html | TEXT | Preserves formatting |
| selection | VARCHAR(255) | Limited to known values |

#### Many2one Fields

Foreign keys are stored as INTEGER:

```python
# Odoo: partner_id = fields.Many2one('res.partner')
# PostgreSQL: partner_id INTEGER  -- Just the ID, not the related record
```

#### Binary Fields

Binary fields are skipped by default (can store large objects):

```
Odoo: image_1920 = fields.Binary()
PostgreSQL: (skipped by default)
```

To sync binary fields, configure exclusions explicitly in YAML.

### Schema Validation

Before creating any schema objects, the platform validates:

1. **Identifier Length**: All names ≤ 63 characters
2. **Identifier Format**: Valid PostgreSQL characters only
3. **Reserved Keywords**: Avoids PostgreSQL reserved words
4. **Duplicates**: No duplicate table/column/index names

Failed validation results in actionable error messages:

```
ERROR: Identifier 'idx_purchase_order_line_x_studio_approval_request_receipt_location'
exceeds maximum length of 63 characters

HINT: Generated safe identifier: 'idx_purchase_order_line_x_studio_appr_a1b2c3d4'
```

### Running Tests

```bash
# Identifier generation tests
python -m pytest tests/test_identifier_generation.py -v

# Schema stress tests (100+ models, 1000+ fields)
python -m pytest tests/test_schema_stress.py -v

# Full test suite
python -m pytest tests/ -v
```

### Production Checklist

Before deploying to production:

- [ ] Run identifier tests: `pytest tests/test_identifier_generation.py`
- [ ] Run stress tests: `pytest tests/test_schema_stress.py`
- [ ] Test with production Odoo database (field discovery)
- [ ] Verify all custom fields generate valid identifiers
- [ ] Check PostgreSQL logs for identifier warnings

---

## License

MIT License - See LICENSE file.
