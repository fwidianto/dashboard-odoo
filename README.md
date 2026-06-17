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

### Type Mapping

| Odoo Type | PostgreSQL Type |
|-----------|-----------------|
| integer | INTEGER |
| float, monetary | NUMERIC(20,4) |
| char, text | TEXT |
| boolean | BOOLEAN |
| date | DATE |
| datetime | TIMESTAMP |
| many2one | INTEGER |
| selection | VARCHAR(64) |

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
| One2many fields not synced | Sync child models separately |
| Many2many fields not synced | Sync relation tables manually |
| Binary fields skipped | External storage for large files |
| Single Odoo instance | Run multiple instances |

---

## License

MIT License - See LICENSE file.
