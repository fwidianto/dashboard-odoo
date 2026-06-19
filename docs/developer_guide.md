# Developer Guide

**Date:** 2026-06-18
**Purpose:** Guide for developers working on the Odoo Dashboard project

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Local Development Setup](#local-development-setup)
3. [Running the Project](#running-the-project)
4. [Adding New Models](#adding-new-models)
5. [Incremental Sync Logic](#incremental-sync-logic)
6. [Schema Evolution](#schema-evolution)
7. [Error Handling](#error-handling)
8. [Testing](#testing)
9. [Logging Standards](#logging-standards)
10. [Code Style](#code-style)

---

## Project Structure

```
dashboard-odoo/
├── config/                     # Configuration files
│   ├── models.yaml            # Model definitions
│   ├── database.yaml          # Database settings
│   └── sync.yaml              # Sync settings
├── docs/                       # Documentation
│   ├── FINAL_ARCHITECTURE.md  # Architecture reference
│   ├── SCHEMA_EVOLUTION.md     # Schema evolution guide
│   └── reports/                # QA and audit reports
├── migrations/                 # Database migrations
├── reports/                    # Generated reports
├── scripts/                    # Utility scripts
├── src/                        # Source code
│   ├── clients/               # External service clients
│   │   ├── odoo_client.py     # Odoo XML-RPC API
│   │   └── postgres_client.py # PostgreSQL operations
│   ├── engine/                # Core sync logic
│   │   └── sync_engine.py     # Main sync orchestrator
│   ├── models/                # Data models
│   │   ├── config.py          # Configuration models
│   │   └── state.py           # State models
│   ├── odoo/                 # Odoo-specific utilities
│   │   ├── metadata_discovery.py
│   │   ├── schema_validator.py
│   │   └── self_healing.py
│   ├── reporting/             # Error reporting
│   │   ├── error_reporter.py
│   │   └── schema_recommender.py
│   ├── state/                 # State management
│   │   └── state_manager.py
│   ├── utils/                 # Utilities
│   │   ├── config_loader.py
│   │   ├── logging.py
│   │   └── settings.py
│   └── main.py                # Entry point
└── tests/                      # Test suite
```

---

## Local Development Setup

### Prerequisites

- Python 3.10+
- PostgreSQL 12+
- Access to Odoo instance (or mock)

### 1. Clone Repository

```bash
git clone <repository-url>
cd dashboard-odoo
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Odoo Configuration
ODOO_URL=https://your-odoo-instance.com
ODOO_API_KEY=your_api_key_here
ODOO_DB=your_database

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sync_dashboard
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
```

### 5. Verify Setup

```bash
python -c "from src.clients.odoo_client import OdooClient; print('OK')"
```

---

## Running the Project

### Full Sync

Syncs all records from all configured models:

```bash
python -m src.main --mode full
```

### Full Sync (Specific Model)

```bash
python -m src.main --mode full --models sale.order
```

### Incremental Sync

Syncs only changed records since last sync:

```bash
python -m src.main --mode incremental
```

### Incremental Sync (Specific Model)

```bash
python -m src.main --mode incremental --models stock.quant
```

### With Limit

```bash
python -m src.main --mode full --limit 100 --models sale.order
```

---

## Adding New Models

### Option 1: Add to models.yaml

Edit `config/models.yaml`:

```yaml
models:
  - res.partner
  - sale.order
  - product.product
  - account.move        # Add this line
```

The platform automatically discovers all fields via `fields_get()`.

### Option 2: Temporary Model

Use the `--models` flag for one-time syncs:

```bash
python -m src.main --mode full --models account.move
```

---

## Incremental Sync Logic

### How It Works

The incremental sync uses a watermark-based approach:

1. **Read Checkpoint**: Load `last_sync_date` and `last_sync_id` from `sync_state` table
2. **Generate Domain**: Filter records where:
   - `write_date > last_sync_date`, OR
   - `write_date == last_sync_date AND id > last_sync_id`
3. **Track MAX**: During sync, track the maximum `write_date` across ALL records
4. **Save Checkpoint**: Store new `(max_date, max_id)` watermark

### Checkpoint Calculation

```python
# Track MAX write_date across ALL records in ALL batches
for record in batch:
    record_write_date = record.get("write_date")
    
    # Skip invalid values (None, False, non-datetime)
    if not isinstance(record_write_date, (str, datetime)):
        continue
    
    # Update if higher
    if last_write_date is None or record_write_date > last_write_date:
        last_write_date = record_write_date
        last_id = record_id
    # Same date, use max id
    elif record_write_date == last_write_date and record_id > last_id:
        last_id = record_id
```

### Why batch[-1] Was Wrong

Previous implementation only checked the last record in each batch:

```python
# WRONG - misses records with higher write_date in same batch
batch_last_record = batch[-1]
```

Current implementation checks EVERY record:

```python
# CORRECT - finds true MAX across all records
for record in batch:
    ...
```

### Handle NULL/False write_date

Some models (e.g., `stock.quant`) have records with `write_date=False`:

```python
# Skip these records
if record_write_date is None:
    continue
if record_write_date is False:
    continue
if isinstance(record_write_date, bool):
    continue
```

### Sync State Table

```sql
CREATE TABLE sync_state (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING',
    last_sync_date TIMESTAMP,
    last_sync_id INTEGER,
    records_synced INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);
```

---

## Schema Evolution

### How It Works

The platform automatically handles schema changes:

1. **New Columns**: Added when Odoo adds fields
2. **Type Changes**: VARCHAR → TEXT when needed
3. **NULL Constraints**: Auto-fixed when records fail

### Example: New Field

1. Odoo adds field `x_custom_field` to model
2. Next sync run:
   - `fields_get()` discovers new field
   - Schema validation detects missing column
   - `ALTER TABLE ADD COLUMN` executed

### Example: Type Change

1. Records fail with `DATA_TOO_LONG`
2. `SchemaRecommender` detects pattern
3. Generates: `ALTER COLUMN column_name TYPE TEXT`
4. User applies migration

### Example: NULL Constraint

1. Records fail with `NULL_CONSTRAINT`
2. Auto-detection adds: `ALTER COLUMN column_name DROP NOT NULL`

### Manual Migrations

Generated in `reports/schema_recommendations/migration_suggestions.sql`:

```sql
-- migration_suggestions.sql

-- New columns
ALTER TABLE sale_order ADD COLUMN IF NOT EXISTS x_custom_field TEXT;

-- Type changes
ALTER TABLE sale_order ALTER COLUMN notes TYPE TEXT;

-- NULL constraints
ALTER TABLE account_move_line ALTER COLUMN move_id DROP NOT NULL;
```

---

## Error Handling

### Error Categories

| Category | Meaning | Auto-fix |
|----------|---------|----------|
| `NULL_CONSTRAINT` | Column cannot be NULL | DROP NOT NULL |
| `DATA_TOO_LONG` | Value exceeds width | ALTER TYPE TEXT |
| `NUMERIC_OVERFLOW` | Number too large | ALTER TYPE NUMERIC(20,4) |
| `SCHEMA_ERROR` | Missing column | ADD COLUMN |
| `UNKNOWN_ERROR` | Other errors | None |

### Error Reporter

```python
from src.reporting.error_reporter import ErrorReporter

reporter = ErrorReporter()

# Start tracking a batch
reporter.start_batch("sale.order", "sale_order")

# Record success
reporter.record_success(100)

# Record error
reporter.record_error(
    model="sale.order",
    table_name="sale_order",
    category=ErrorCategory.NULL_CONSTRAINT,
    record_id=123,
    error_message="null value in column violates not-null constraint",
    column_name="partner_id"
)

# Get summary
summary = reporter.get_batch_summary()
```

### Self-Healing

The `SelfHealing` module automatically repairs:

1. Missing columns
2. Type mismatches
3. NULL constraints

```python
# In sync_engine.py, errors are passed to self-healing:
self._self_healing.check_and_repair(model, records, errors)
```

---

## Testing

### Run All Tests

```bash
python -m pytest tests/ -v
```

### Run Specific Test Module

```bash
python -m pytest tests/test_sync_engine.py -v
```

### Run with Coverage

```bash
python -m pytest tests/ --cov=src --cov-report=html
```

### Test Categories

| File | Tests | Purpose |
|------|-------|---------|
| `test_sync_engine.py` | 17 | Core sync logic |
| `test_incremental_sync_flow.py` | 5 | Checkpoint handling |
| `test_nullable_sync.py` | 5 | NULL handling |
| `test_self_healing.py` | 33 | Auto-repair logic |
| `test_metadata_discovery.py` | 19 | Odoo metadata |
| `test_error_reporting.py` | 37 | Error classification |

---

## Logging Standards

### Log Levels

| Level | Use Case |
|-------|----------|
| `DEBUG` | Detailed tracing (checkpoint calculations) |
| `INFO` | Operation progress, audit trail |
| `WARNING` | Recoverable issues (NULL values skipped) |
| `ERROR` | Operation failures (needs attention) |

### Structured Logging

```python
from src.utils.logging import get_logger

logger = get_logger("sync_engine")

# Structured log with context
logger.info(
    "CHECKPOINT_SAVED",
    model="sale.order",
    raw_last_write_date="2026-06-19 09:52:36",
    raw_last_id=3910,
)

# Error with details
logger.error(
    "WRITE_DATE_COMPARISON_ERROR",
    model="stock.quant",
    record_id=123,
    record_write_date=False,
    error="'>' not supported between 'bool' and 'str'",
)
```

### Keep/Remove Classification

| Log Type | Recommendation |
|----------|----------------|
| Audit trail (CHECKPOINT_SAVED) | KEEP - INFO level |
| Error tracking (WRITE_DATE_COMPARISON_ERROR) | KEEP - ERROR level |
| Debug tracing (MAX_WRITE_DATE_FOUND) | DEMOTE - DEBUG level |

---

## Code Style

### Python Style Guide

- Follow PEP 8
- Use type hints where possible
- Maximum line length: 100 characters

### Imports

```python
# Standard library
from datetime import datetime
from typing import Optional

# Third-party
from sqlalchemy import create_engine

# Local
from src.clients.odoo_client import OdooClient
from src.models.config import ModelConfig
```

### Docstrings

```python
def sync_model(self, model_config: ModelConfig, full_sync: bool) -> None:
    """Sync a single model to PostgreSQL.
    
    Args:
        model_config: Model configuration with Odoo/PG settings
        full_sync: If True, sync all records; otherwise incremental
    
    Returns:
        None
    
    Raises:
        OdooConnectionError: If Odoo is unreachable
        PostgresConnectionError: If PostgreSQL is unreachable
    """
```

### Error Handling

```python
try:
    result = client.execute(model, method, args)
except OdooError as e:
    logger.error("ODOO_API_ERROR", model=model, error=str(e))
    raise
except Exception as e:
    logger.error("UNEXPECTED_ERROR", error=str(e))
    raise
```

---

## Common Patterns

### Batch Processing

```python
for batch in self._odoo.read_batched(
    model=model_config.odoo_model,
    domain=domain,
    fields=field_names,
    batch_size=batch_size,
    order="id",
):
    # Process batch
    transformed = self._transform_records(batch, validated)
    inserted, updated, errors = self._pg.upsert(...)
    
    # Track for checkpoint
    for record in batch:
        # Update max write_date
        ...
```

### Config Validation

```python
from src.utils.config_loader import get_config

config = get_config()
for model_config in config.models:
    # Validate required fields
    if not model_config.odoo_model:
        raise ValueError(f"Model missing odoo_model")
```

### State Management

```python
from src.state.state_manager import StateManager

state_mgr = StateManager(pg_client, logger)

# Read current state
state = state_mgr.get_sync_state("sale.order")
if state:
    last_date = state.last_sync_date
    last_id = state.last_sync_id

# Mark as running
state_mgr.mark_sync_started("sale.order", last_sync_id=last_id)

# Mark as completed
result = SyncResult()
result.records_synced = 100
result.end_time = datetime.now()
state_mgr.mark_sync_completed(model_config, result)
```

---

## Debugging Tips

### Enable Debug Logging

```bash
export LOG_LEVEL=DEBUG
python -m src.main --mode incremental
```

### Check Sync State

```bash
python scripts/diagnose_sync_state.py
```

### View Recent Errors

```bash
python scripts/check_errors.py
```

### Repair Schema

```bash
python scripts/repair_schema.py
```

---

## Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make changes
3. Add tests
4. Run test suite: `pytest tests/ -v`
5. Commit with clear message
6. Push and create PR
