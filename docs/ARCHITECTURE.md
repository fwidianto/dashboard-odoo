# Architecture Documentation

This document provides detailed architecture information for the Odoo to PostgreSQL synchronization platform.

## Table of Contents

- [Component Diagram](#component-diagram)
- [Sync Flow](#sync-flow)
- [Schema Flow](#schema-flow)
- [Database Flow](#database-flow)
- [Component Details](#component-details)

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                      │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐   │
│  │   CLI Client    │    │   REST API      │    │   Scheduler        │   │
│  │   (main.py)     │    │   (api.py)      │    │   (scheduler.py)   │   │
│  └────────┬────────┘    └────────┬────────┘    └──────────┬──────────┘   │
└───────────┼──────────────────────┼───────────────────────┼────────────────┘
            │                      │                       │
            └──────────────────────┼───────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SYNC ENGINE LAYER                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                        SyncEngine                                      │  │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────────┐│  │
│  │  │ sync_model()  │  │ sync_all()   │  │  _transform_records()     ││  │
│  │  │               │  │              │  │  - many2one extraction     ││  │
│  │  │ - validate    │  │ - iterate    │  │  - datetime parsing       ││  │
│  │  │ - fetch       │  │   models     │  │  - default values         ││  │
│  │  │ - transform   │  │ - parallel   │  │  - false handling         ││  │
│  │  │ - upsert      │  │   or serial  │  │                           ││  │
│  │  │ - track       │  │              │  │                           ││  │
│  │  └───────────────┘  └───────────────┘  └───────────────────────────┘│  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                    ┌───────────────┴───────────────┐                        │
│                    ▼                               ▼                        │
│  ┌─────────────────────────┐         ┌─────────────────────────┐        │
│  │       OdooClient        │         │     PostgresClient       │        │
│  │    (XML-RPC Client)     │         │   (SQLAlchemy Client)    │        │
│  └─────────────────────────┘         └─────────────────────────┘        │
└───────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┴───────────────────────┐
            ▼                                               ▼
┌─────────────────────────────┐               ┌─────────────────────────────┐
│         Odoo ERP            │               │       PostgreSQL            │
│                             │               │                             │
│  ┌─────────────────────┐   │               │  ┌─────────────────────┐   │
│  │   XML-RPC Endpoints  │   │               │  │   System Tables     │   │
│  │                      │   │               │  │                     │   │
│  │  /xmlrpc/2/common   │   │               │  │  - sync_state       │   │
│  │  /xmlrpc/2/object   │   │               │  │  - sync_history     │   │
│  │                      │   │               │  │  - sync_audit       │   │
│  └─────────────────────┘   │               │  └─────────────────────┘   │
│                            │               │                             │
│  ┌─────────────────────┐   │               │  ┌─────────────────────┐   │
│  │   Allowed Methods    │   │               │  │   User Tables       │   │
│  │                      │   │               │  │                     │   │
│  │  ✓ search           │   │               │  │  - res_partner      │   │
│  │  ✓ read             │   │               │  │  - product_product │   │
│  │  ✓ search_read      │   │               │  │  - sale_order       │   │
│  │  ✓ search_count     │   │               │  │  - stock_move       │   │
│  │  ✓ fields_get       │   │               │  │  - [user tables]    │   │
│  │                      │   │               │  │                     │   │
│  │  ✗ create (BLOCKED) │   │               │  └─────────────────────┘   │
│  │  ✗ write (BLOCKED) │   │               │                             │
│  │  ✗ unlink (BLOCKED) │   │               │                             │
│  └─────────────────────┘   │               └─────────────────────────────┘
└─────────────────────────────┘
```

---

## Sync Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FULL SYNC FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────┘

   ┌──────────────┐
   │   Start      │
   │   --mode     │
   │   full       │
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │  Load Config │
   │ models.yaml  │
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │Test          │
   │Connections   │
   │              │
   │ Odoo ✓       │
   │ PG ✓         │
   └──────┬───────┘
          │
          ▼
   ┌──────────────────────────────────────┐
   │       For Each Model                 │
   │  ┌──────────────────────────────┐    │
   │  │ 1. Ensure Table Schema      │    │
   │  │    - create_model_table()  │    │
   │  │    - alter_table_add_columns()│   │
   │  │    - migrate_column_types()│    │
   │  │    - create_indexes()      │    │
   │  └──────────────────────────────┘    │
   │                  │                  │
   │                  ▼                  │
   │  ┌──────────────────────────────┐    │
   │  │ 2. Get Record Count          │    │
   │  │    odoo.count(model, [])     │    │
   │  └──────────────────────────────┘    │
   │                  │                  │
   │                  ▼                  │
   │  ┌──────────────────────────────┐    │
   │  │ 3. Batched Fetch Loop       │◄───┤──┐
   │  │                              │    │  │
   │  │  search_read(               │    │  │
   │  │    model=model,             │    │  │
   │  │    domain=[],              │    │  │
   │  │    fields=fields,          │    │  │
   │  │    offset=offset,          │    │  │
   │  │    limit=1000              │    │  │
   │  │  )                          │    │  │
   │  └──────────────┬───────────────┘    │  │
   │                 │                   │  │
   │                 ▼                   │  │
   │  ┌──────────────────────────────┐   │  │
   │  │ 4. Transform Records        │   │  │
   │  │    - Extract many2one IDs   │   │  │
   │  │    - Parse datetime         │   │  │
   │  │    - Handle None/False      │   │  │
   │  │    - Apply defaults         │   │  │
   │  └──────────────┬───────────────┘   │  │
   │                 │                   │  │
   │                 ▼                   │  │
   │  ┌──────────────────────────────┐   │  │
   │  │ 5. Upsert Batch              │   │  │
   │  │                              │   │  │
   │  │  INSERT INTO table (...)     │   │  │
   │  │  VALUES (...)                │   │  │
   │  │  ON CONFLICT (id) DO UPDATE  │   │  │
   │  │  RETURNING id, xmax          │   │  │
   │  │                              │   │  │
   │  │  xmax=0 → INSERT             │   │  │
   │  │  xmax>0 → UPDATE             │   │  │
   │  └──────────────┬───────────────┘   │  │
   │                 │                   │  │
   │                 ▼                   │  │
   │     offset += batch_size ───────────┘──┘
   │                 │
   │                 ▼
   │  ┌──────────────────────────────┐
   │  │ 6. Update Sync State         │
   │  │                              │
   │  │  sync_state.last_sync_date = │
   │  │    current_timestamp         │
   │  │  sync_state.record_count =   │
   │  │    total_records             │
   │  │  sync_state.status =         │
   │  │    COMPLETED                 │
   │  └──────────────────────────────┘
   │                 │
   │                 ▼
   ┌──────────────────────────────────────┐
   │         Next Model or Exit            │
   └──────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                           INCREMENTAL SYNC FLOW                              │
└─────────────────────────────────────────────────────────────────────────────┘

   ┌──────────────┐
   │   Start      │
   │   --mode     │
   │  incremental │
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │  Load Config │
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │  Get Last    │
   │  Sync Date   │
   │              │
   │  FROM        │
   │  sync_state  │
   │  WHERE       │
   │  model='...' │
   └──────┬───────┘
          │
          ▼
   ┌──────────────────────────────────────┐
   │  Build Domain Filter                 │
   │                                      │
   │  domain = [                          │
   │    ('write_date', '>=', last_date)  │
   │  ]                                   │
   │                                      │
   │  If no last_date → Full sync        │
   └──────────────┬───────────────────────┘
                  │
                  ▼
          Same batch fetch/transform/upsert
          loop as full sync (see above)
                  │
                  ▼
   ┌──────────────────────────────┐
   │  Update Sync State           │
   │                              │
   │  sync_state.last_sync_date = │
   │    current_timestamp         │
   │  sync_state.status =         │
   │    COMPLETED                 │
   └──────────────────────────────┘
```

---

## Schema Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SCHEMA EVOLUTION FLOW                             │
└─────────────────────────────────────────────────────────────────────────────┘

   ┌──────────────┐
   │   Sync       │
   │   Starts     │
   └──────┬───────┘
          │
          ▼
   ┌──────────────────────────────┐
   │  ensure_table_schema()       │
   │                              │
   │  1. create_model_table()     │
   │  2. alter_table_add_columns()│
   │  3. migrate_column_types()   │
   │  4. create_indexes_for_model()│
   └──────────────┬───────────────┘
                  │
                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                    1. CREATE MODEL TABLE                         │
   │                                                                  │
   │  Check: Does table exist?                                        │
   │          │                                                        │
   │          ├── NO → Create table with all columns                   │
   │          │         - id (INTEGER PRIMARY KEY)                     │
   │          │         - [other fields from config]                   │
   │          │         - Apply extend_existing=True                    │
   │          │                                                        │
   │          └── YES → Ensure primary key constraint exists           │
   │                    (migration for existing tables)                 │
   └─────────────────────────────────────────────────────────────────┘
                  │
                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                    2. ALTER TABLE ADD COLUMNS                    │
   │                                                                  │
   │  Get existing columns from information_schema                     │
   │          │                                                        │
   │          ▼                                                        │
   │  Compare with configured fields                                   │
   │          │                                                        │
   │          ▼                                                        │
   │  For each missing column:                                        │
   │          │                                                        │
   │          ├── Add column with correct type                         │
   │          │   ALTER TABLE ADD COLUMN col_name TYPE;               │
   │          │                                                        │
   │          └── Populate with default value if NOT NULL              │
   │              UPDATE table SET col = default WHERE col IS NULL;   │
   │                                                                  │
   │  Result: {added_columns: ['col1', 'col2']}                      │
   └─────────────────────────────────────────────────────────────────┘
                  │
                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                    3. MIGRATE COLUMN TYPES                       │
   │                                                                  │
   │  For each column:                                                │
   │          │                                                        │
   │          ▼                                                        │
   │  Is migration needed?                                            │
   │          │                                                        │
   │          ├── VARCHAR(≤255) → TEXT                                │
   │          │         Odoo values often exceed 255 chars             │
   │          │                                                        │
   │          ├── NUMERIC(<14 precision) → NUMERIC(20,4)              │
   │          │         Odoo monetary can exceed 10 billion           │
   │          │                                                        │
   │          └── Other type mismatches                               │
   │                  May require manual migration                    │
   │                                                                  │
   │  If migration needed:                                            │
   │          ALTER TABLE table_name                                  │
   │          ALTER COLUMN col_name TYPE new_type;                     │
   └─────────────────────────────────────────────────────────────────┘
                  │
                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                    4. CREATE INDEXES                            │
   │                                                                  │
   │  Index strategy:                                                 │
   │          │                                                        │
   │          ├── Primary key columns → Already indexed (PK constraint) │
   │          │                                                        │
   │          ├── Foreign key columns (*_id) → Create index           │
   │          │                                                        │
   │          ├── Sync date fields (write_date) → Create index        │
   │          │                                                        │
   │          └── User-specified indexed fields → Create index         │
   │                                                                  │
   │  CREATE INDEX idx_table_column ON table(column);                │
   └─────────────────────────────────────────────────────────────────┘
                  │
                  ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                       SCHEMA COMPLETE                            │
   │                                                                  │
   │  Table now has:                                                   │
   │  - All configured columns                                         │
   │  - Correct types (widened if needed)                             │
   │  - Primary key constraint                                        │
   │  - Indexes for FK and sync date columns                          │
   └─────────────────────────────────────────────────────────────────┘
```

---

## Database Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATABASE FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────┘

                           ODOO ERP
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   SELECT id, name, email, partner_id, write_date                          │
│   FROM res_partner                                                          │
│   WHERE write_date >= '2024-01-15 10:30:00'                                │
│   ORDER BY write_date, id                                                   │
│   LIMIT 1000                                                                │
│   OFFSET 0                                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                        XML-RPC Response
                        (Python dicts)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TRANSFORMATION                                      │
│                                                                             │
│   Input (Odoo format):                         Output (PG format):        │
│   ─────────────────────                       ──────────────────────       │
│   {                                            {                            │
│     'id': 42,           ──────────────────►     'id': 42,                   │
│     'name': 'Acme Corp',─────────────────►     'name': 'Acme Corp',         │
│     'email': False,     ──────────────────►     'email': None,              │
│     'partner_id': [15, 'Parent'], ─────────►     'partner_id': 15,          │
│     'write_date': '2024-01-15T10:30:00', ──►     'write_date': datetime    │
│     'relation_ids': [1,2,3] (many2many)    ──►     [SKIPPED]                │
│   }                                            }                            │
│                                                                             │
│   Many2one extraction:    partner_id: [15, 'Name'] → 15                     │
│   False → NULL conversion:  email: False → None                            │
│   Datetime parsing:        '2024-01-15T10:30:00' → datetime                 │
│   Many2many skip:          relation_ids: [1,2,3] → NOT INCLUDED            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              UPSERT                                          │
│                                                                             │
│   INSERT INTO res_partner                                                  │
│     (id, name, email, partner_id, write_date)                               │
│   VALUES                                                                    │
│     (:id, :name, :email, :partner_id, :write_date)                         │
│   ON CONFLICT (id) DO UPDATE SET                                            │
│     name = EXCLUDED.name,                                                   │
│     email = EXCLUDED.email,                                                 │
│     partner_id = EXCLUDED.partner_id,                                       │
│     write_date = EXCLUDED.write_date                                        │
│   RETURNING id, xmax                                                        │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  xmax Interpretation:                                                │  │
│   │                                                                       │  │
│   │  xmax = 0  →  INSERT occurred (new record)                          │  │
│   │  xmax > 0  →  UPDATE occurred (existing record modified)             │  │
│   │                                                                       │  │
│   │  Batch result:                                                       │  │
│   │    inserted: 450                                                     │  │
│   │    updated: 550                                                      │  │
│   │    errors: 0                                                         │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          STATE PERSISTENCE                                   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                        sync_state table                             │  │
│   │  ─────────────────────────────────────────────────────────────────  │  │
│   │                                                                       │  │
│   │  model_name     │ last_sync_date      │ record_count │ status      │  │
│   │  ─────────────────────────────────────────────────────────────────  │  │
│   │  res.partner    │ 2024-01-15 10:35:00 │ 15,432       │ COMPLETED   │  │
│   │  product.product│ 2024-01-15 10:34:30 │ 8,291         │ COMPLETED   │  │
│   │  sale.order     │ 2024-01-15 10:33:15 │ 3,102         │ COMPLETED   │  │
│   │  stock.move     │ 2024-01-15 10:32:00 │ 45,871        │ COMPLETED   │  │
│   │                                                                       │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                      sync_history table                              │  │
│   │  ─────────────────────────────────────────────────────────────────  │  │
│   │                                                                       │  │
│   │  model_name  │ sync_type   │ status    │ started_at   │ records_* │  │
│   │  ─────────────────────────────────────────────────────────────────  │  │
│   │  res.partner │ incremental │ completed │ 10:30:00     │ 1000      │  │
│   │  res.partner │ incremental │ completed │ 10:15:00     │ 1000      │  │
│   │  res.partner │ full        │ completed │ 09:00:00     │ 15432     │  │
│   │  ...                                                              │  │
│   │                                                                       │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### OdooClient

**File:** `src/clients/odoo_client.py`

**Purpose:** Read-only XML-RPC client for Odoo API interactions

**Key Methods:**
| Method | Description |
|--------|-------------|
| `authenticate()` | Authenticate with Odoo via API key or password |
| `search(model, domain)` | Get record IDs matching domain |
| `read(model, ids, fields)` | Read specific records |
| `search_read(model, domain, fields)` | Combined search and read |
| `count(model, domain)` | Count matching records |
| `get_model_fields(model)` | Get field definitions via `fields_get()` |
| `read_batched(model, domain, fields, batch_size)` | Generator for large datasets |

**Security:** All write operations (create, write, unlink) are blocked with `ReadOnlyViolation` exception.

### PostgresClient

**File:** `src/clients/postgres_client.py`

**Purpose:** SQLAlchemy-based PostgreSQL operations

**Key Methods:**
| Method | Description |
|--------|-------------|
| `create_model_table()` | Create table with primary key and indexes |
| `alter_table_add_columns()` | Add missing columns |
| `migrate_column_types()` | Widen column types (VARCHAR→TEXT, NUMERIC) |
| `create_indexes_for_model()` | Create FK and sync date indexes |
| `ensure_table_schema()` | Orchestrate all schema operations |
| `upsert()` | INSERT ON CONFLICT with xmax tracking |
| `upsert_batch()` | Batch upsert for large datasets |

### SyncEngine

**File:** `src/engine/sync_engine.py`

**Purpose:** Orchestrate the synchronization process

**Key Methods:**
| Method | Description |
|--------|-------------|
| `initialize()` | Test connections, create tables |
| `sync_model()` | Sync single model (full or incremental) |
| `sync_all()` | Sync all configured models |
| `_transform_records()` | Convert Odoo records to PG format |
| `get_sync_status()` | Get status of all models |

### StateManager

**File:** `src/state/state_manager.py`

**Purpose:** Persist sync state for incremental sync

**Key Methods:**
| Method | Description |
|--------|-------------|
| `get_last_sync_date()` | Get last sync timestamp for model |
| `mark_sync_started()` | Set status to RUNNING |
| `mark_sync_completed()` | Set status to COMPLETED, update counts |
| `mark_sync_failed()` | Set status to FAILED with error |
| `reset_model_state()` | Reset for full re-sync |

### ConfigLoader

**File:** `src/utils/config_loader.py`

**Purpose:** Parse and validate YAML configuration

**Key Classes:**
| Class | Description |
|-------|-------------|
| `ConfigLoader` | Load YAML, auto-detect fields, expand simple format |
| `ValidatedModelConfig` | Wrap config with Odoo field validation |

### Validator

**File:** `src/utils/validation.py`

**Purpose:** Comprehensive validation before sync

**Checks:**
- Environment variables present
- Odoo connection and authentication
- PostgreSQL connection
- models.yaml syntax and model validity

---

## Data Flow Summary

```
User Command
    │
    ▼
main.py / api.py / scheduler.py
    │
    ▼
SyncEngine.initialize()
    │
    ├── Test Odoo connection
    ├── Test PG connection
    └── Create/update schema
    │
    ▼
For each model:
    │
    ├── OdooClient.search_read() ──────► Odoo XML-RPC API
    │                                      │
    │◄──────────────────────────────────────┘
    │   Records (batched)
    │
    ▼
SyncEngine._transform_records()
    │
    ├── Extract many2one IDs
    ├── Parse datetime strings
    ├── Handle None/False values
    └── Apply default values
    │
    ▼
PostgresClient.upsert() ──────────► PostgreSQL
    │
    │   INSERT ... ON CONFLICT DO UPDATE
    │   RETURNING id, xmax
    │
    │◄──────────────────────────────────────
    │   inserted, updated counts
    │
    ▼
StateManager.mark_sync_completed()
    │
    └── Update sync_state table
         Update sync_history table
```
