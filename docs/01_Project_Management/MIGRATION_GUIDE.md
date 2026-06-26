# Migration Guide: Field-Based to Model-Based Architecture

This guide helps you migrate from the old field-based configuration to the new model-based architecture.

---

## Overview

### What Changed?

| Before | After |
|--------|-------|
| Manual field definitions in YAML | Auto-discovered from Odoo |
| Had to list every field | Just list model names |
| Custom fields needed manual config | Custom fields auto-included |
| Verbose YAML configuration | Minimal YAML |

### Benefits

1. **Dramatically simpler configuration**
2. **Zero maintenance** for new Odoo fields
3. **Automatic custom field sync** (`x_*` fields)
4. **Fewer errors** (no field typos or type mismatches)
5. **Future-proof** - works with any Odoo version

---

## Quick Migration

### Step 1: Simplify Your YAML

**Old config:**
```yaml
models:
  - odoo_model: res.partner
    postgres_table: res_partner
    fields:
      - id
      - name
      - email
      - phone
      - active
      - write_date
```

**New config:**
```yaml
models:
  - res.partner
```

That's it! All fields are auto-discovered.

### Step 2: Remove `fields:` Sections

If you have explicit field definitions, you can remove them:

**Before:**
```yaml
legacy_models:
  - odoo_model: stock.move
    postgres_table: stock_move
    description: "Stock Moves"
    fields:
      - id
      - name
      - product_id
      - product_qty
      - state
      - date
      - write_date
```

**After:**
```yaml
models:
  - stock.move
```

### Step 3: Use Options for Special Cases

For custom table names or deletion strategies:

**Before:**
```yaml
models:
  - odoo_model: res.partner
    postgres_table: contacts_archive
    description: "Partner archive"
    fields:
      - id
      - name
      - email
```

**After:**
```yaml
models_with_options:
  - odoo_model: res.partner
    postgres_table: contacts_archive
```

---

## Configuration Formats Reference

### 1. Model-Only (Simplest)

```yaml
models:
  - res.partner
  - sale.order
  - product.product
```

**What happens:**
- All fields auto-discovered from Odoo
- Table name auto-generated (`res.partner` → `res_partner`)
- All fields synced

### 2. Model with Options

```yaml
models_with_options:
  - odoo_model: sale.order
    postgres_table: my_sales
    deletion_strategy: soft_delete
    soft_delete_field: active
```

**Options available:**
| Option | Description | Default |
|--------|-------------|---------|
| `postgres_table` | Custom table name | Auto-generated |
| `deletion_strategy` | ignore/soft_delete/reconcile | ignore |
| `soft_delete_field` | Field for soft delete | - |
| `exclusions` | Fields to skip | [] |
| `inclusions` | Only sync these fields | All fields |

### 3. Legacy Format (Still Supported)

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

## Common Migration Scenarios

### Scenario 1: Custom Table Name

**Old:**
```yaml
models:
  - odoo_model: res.partner
    postgres_table: my_contacts
    fields:
      - id
      - name
      - email
```

**New:**
```yaml
models_with_options:
  - odoo_model: res.partner
    postgres_table: my_contacts
```

### Scenario 2: Soft Delete Strategy

**Old:**
```yaml
models:
  - odoo_model: res.partner
    postgres_table: res_partner
    deletion_strategy: soft_delete
    soft_delete_field: active
    fields:
      - id
      - name
      - email
      - active
```

**New:**
```yaml
models_with_options:
  - odoo_model: res.partner
    postgres_table: res_partner
    deletion_strategy: soft_delete
    soft_delete_field: active
```

### Scenario 3: Exclude Large Fields

**Old:**
```yaml
models:
  - odoo_model: product.product
    postgres_table: product_product
    fields:
      - id
      - name
      - default_code
      # Intentionally skipped: image_1920
```

**New:**
```yaml
models_with_options:
  - odoo_model: product.product
    postgres_table: product_product
    exclusions:
      - image_1920
      - image_1024
      - image_512
```

### Scenario 4: Include Only Specific Fields

**Old:**
```yaml
models:
  - odoo_model: stock.move
    postgres_table: stock_move_basic
    fields:
      - id
      - name
      - product_id
      - product_qty
      - state
      - write_date
```

**New:**
```yaml
models_with_options:
  - odoo_model: stock.move
    postgres_table: stock_move_basic
    inclusions:
      - id
      - name
      - product_id
      - product_qty
      - state
      - write_date
```

---

## Backward Compatibility

The legacy format is **fully supported**:

```yaml
# Old-style config still works!
legacy_models:
  - odoo_model: some.model
    postgres_table: some_table
    fields:
      - id
      - name
```

You can mix old and new formats:

```yaml
# Mix of formats - all supported
models:
  - res.partner                    # New model-only format
  - sale.order                     # New model-only format

models_with_options:
  - odoo_model: product.product    # New with options
    exclusions:
      - image_1920

legacy_models:
  - odoo_model: stock.move        # Legacy format
    postgres_table: stock_move
    fields:
      - id
      - name
```

---

## Field Auto-Detection Details

### What Gets Synced

| Field Type | Example | Synced As |
|-----------|---------|-----------|
| id | `id` | INTEGER PRIMARY KEY |
| char | `name`, `email` | TEXT |
| text | `description` | TEXT |
| integer | `qty_available` | INTEGER |
| float | `list_price` | NUMERIC(20,4) |
| monetary | `amount_total` | NUMERIC(20,4) |
| boolean | `active` | BOOLEAN |
| date | `date_order` | DATE |
| datetime | `write_date` | TIMESTAMP |
| many2one | `partner_id` | INTEGER (indexed) |
| selection | `state` | VARCHAR(64) |
| x_* | `x_custom_field` | TEXT |

### What Gets Skipped

| Field Type | Reason |
|-----------|--------|
| one2many | Not stored directly |
| many2many | Uses relation table |
| binary | Too large (use exclusions) |

---

## Testing Your Migration

### 1. Validate Configuration

```bash
python -m src.main --validate
```

### 2. Run Full Sync

```bash
python -m src.main --mode full
```

### 3. Compare Record Counts

```bash
# Check sync status
python -m src.main --status

# Compare with expected counts in Odoo
```

### 4. Verify New Columns

```sql
-- List all columns in synced table
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'res_partner'
ORDER BY ordinal_position;
```

---

## Troubleshooting

### Issue: Model Not Found in Odoo

**Error:**
```
Failed to connect to Odoo: Model 'invalid.model' not found
```

**Solution:** Check the model name in Odoo (Settings → Technical → Models)

### Issue: Too Many Columns

**Problem:** Table has hundreds of columns

**Solution:** Use `inclusions` to sync only needed fields:

```yaml
models_with_options:
  - odoo_model: res.partner
    inclusions:
      - id
      - name
      - email
      - phone
      - write_date
```

### Issue: Missing Write Date

**Problem:** Incremental sync not working

**Solution:** `write_date` should be auto-detected. If missing:

```yaml
models_with_options:
  - odoo_model: some.model
    inclusions:
      - id
      - write_date    # Ensure this is included
```

### Issue: Large Binary Data

**Problem:** Images causing memory issues

**Solution:** Exclude binary fields:

```yaml
models_with_options:
  - odoo_model: product.product
    exclusions:
      - image_1920
      - image_1024
      - image_512
      - image_256
      - image_128
```

---

## Production Recommendations

### 1. Start with Few Models

Don't migrate everything at once:

```yaml
models:
  - res.partner    # Start with this one
  # Add more after testing
```

### 2. Use Exclusions Wisely

Exclude large or unnecessary fields:

```yaml
models_with_options:
  - odoo_model: product.product
    exclusions:
      - image_1920
      - image_1024
      - write_date    # If not needed for sync
```

### 3. Test in Development First

Always test migration in dev environment before production.

### 4. Monitor Sync Performance

After migration, monitor:
- Sync duration
- Record counts
- Error logs

---

## Summary Checklist

- [ ] Remove explicit `fields:` sections from YAML
- [ ] Replace field lists with model names
- [ ] Add `models_with_options:` for custom table names
- [ ] Use `exclusions:` to skip large/unneeded fields
- [ ] Use `inclusions:` to sync only needed fields
- [ ] Test with `--validate` before full sync
- [ ] Monitor sync results in production
