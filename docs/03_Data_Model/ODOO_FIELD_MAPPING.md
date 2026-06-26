# Odoo Field Mapping Documentation

This document explains how Odoo field names and types are mapped to PostgreSQL columns and types.

## Table of Contents

- [Odoo Labels vs Technical Names](#odoo-labels-vs-technical-names)
- [How fields_get Works](#how-fields_get-works)
- [Discovering New Fields](#discovering-new-fields)
- [Field Type Mapping](#field-type-mapping)
- [Examples](#examples)

---

## Odoo Labels vs Technical Names

Odoo fields have two names:

| Name Type | Example | Used For |
|-----------|---------|----------|
| **Technical Name** | `partner_id` | API calls, code, XML |
| **Label (String)** | `Contact` | UI display |

### Technical Names

Technical names are:
- Used in `fields_get()` responses
- Used in `search_read()` results
- Used in configuration (`odoo_field`)
- Snake_case format
- Unique per model

Example technical names:
```python
'partner_id'      # Many2one to res.partner
'product_id'     # Many2one to product.product
'line_ids'       # One2many relationship
'tag_ids'        # Many2many relationship
'write_date'     # System timestamp
```

### Labels

Labels are:
- Human-readable field names
- Translated to user's language
- Shown in Odoo UI forms and lists
- NOT used in API calls

Example labels:
```python
'Contact'        # Label for partner_id
'Product'        # Label for product_id
'Order Lines'    # Label for line_ids
'Tags'           # Label for tag_ids
'Last Modified'  # Label for write_date
```

### Finding Technical Names

1. **From URL** in Odoo UI:
   ```
   /web#model=sale.order&view_type=form
   ```
   The model name is `sale.order`

2. **From field definition** in developer mode:
   - Enable Developer Mode in Odoo
   - Go to Settings → Technical → Fields
   - Find your field - Technical Name column

3. **From XML views**:
   ```xml
   <field name="partner_id" />
   ```
   The `name` attribute is the technical name

4. **From `fields_get()`**:
   ```python
   fields = odoo.fields_get('sale.order')
   # Returns dict with technical names as keys
   ```

---

## How fields_get Works

`fields_get()` is an Odoo API method that returns all field definitions for a model.

### API Call

```python
fields = odoo.execute(
    model='res.partner',
    method='fields_get',
    args=[],
    kwargs={}
)
```

### Response Structure

```python
{
    'id': {
        'type': 'integer',
        'string': 'ID',
        'required': False,
        'store': True,
        'index': True,
    },
    'name': {
        'type': 'char',
        'string': 'Name',
        'required': True,
        'store': True,
        'index': False,
        'size': 128,  # Max length
    },
    'email': {
        'type': 'char',
        'string': 'Email',
        'required': False,
        'store': True,
    },
    'partner_id': {
        'type': 'many2one',
        'string': 'Contact',
        'required': False,
        'store': True,
        'relation': 'res.partner',  # Related model
        'on_delete': 'cascade',
    },
    'category_id': {
        'type': 'many2many',
        'string': 'Tags',
        'required': False,
        'store': True,
        'relation': 'res.partner.category',
    },
    'child_ids': {
        'type': 'one2many',
        'string': 'Children',
        'required': False,
        'store': True,
        'relation': 'res.partner',
        'inverse_name': 'parent_id',
    },
    'active': {
        'type': 'boolean',
        'string': 'Active',
        'required': False,
        'store': True,
        'default': True,
    },
    'write_date': {
        'type': 'datetime',
        'string': 'Last Modified',
        'required': False,
        'store': True,
    },
}
```

### Key fields_get Properties

| Property | Description |
|----------|-------------|
| `type` | Field type (char, integer, many2one, etc.) |
| `string` | Human-readable label |
| `required` | Whether field is required |
| `store` | Whether field is stored in DB |
| `index` | Whether database index exists |
| `relation` | Related model (many2one, many2many, one2many) |
| `inverse_name` | Inverse field name (one2many) |
| `default` | Default value |
| `help` | Help text |

---

## Discovering New Fields

### Method 1: Use Config Generator

Generate config from Odoo automatically:

```bash
python -m src.utils.config_generator --model res.partner
```

Output:
```yaml
models:
  - odoo_model: res.partner
    postgres_table: res_partner
    description: "Auto-generated from res.partner"
    fields:
      - odoo_field: id
        postgres_column: id
        postgres_type: INTEGER
        primary_key: true
      - odoo_field: name
        postgres_column: name
        postgres_type: TEXT
      - odoo_field: email
        postgres_column: email
        postgres_type: TEXT
      # ... all other fields
```

### Method 2: Interactive Python Script

```python
from src.clients.odoo_client import OdooClient
from src.utils.settings import get_settings

settings = get_settings()
client = OdooClient()
client.authenticate()

# Get all fields for a model
fields = client.get_model_fields('sale.order')

# Print all field names and types
for name, definition in sorted(fields.items()):
    print(f"{name:30} {definition['type']:15} {definition.get('string', '')}")
```

### Method 3: Odoo Developer Mode

1. Enable Developer Mode in Odoo
2. Go to Settings → Technical → Fields
3. Filter by your model
4. View all field definitions

### Method 4: XML View Inspection

Check XML views for field names:

```xml
<record id="view_order_form" model="ir.ui.view">
    <field name="name">sale.order.form</field>
    <field name="model">sale.order</field>
    <field name="arch" type="xml">
        <form string="Sales Order">
            <group>
                <field name="partner_id"/>
                <field name="date_order"/>
                <field name="state"/>
            </group>
            <field name="order_line">
                <tree>
                    <field name="product_id"/>
                    <field name="product_uom_qty"/>
                    <field name="price_unit"/>
                </tree>
            </field>
        </form>
    </field>
</record>
```

### Comparing Config vs Reality

Check if your config matches Odoo's fields:

```bash
# Generate expected fields from Odoo
python -m src.utils.config_generator --model res.partner > /tmp/expected.yaml

# Compare with your config
diff config/models.yaml /tmp/expected.yaml
```

---

## Field Type Mapping

### Odoo to PostgreSQL Type Mapping

| Odoo Type | PostgreSQL Type | Notes |
|-----------|-----------------|-------|
| `integer` | `INTEGER` | - |
| `bigint` | `BIGINT` | - |
| `float` | `NUMERIC(20,4)` | Large precision for Odoo monetary |
| `monetary` | `NUMERIC(20,4)` | Currency values |
| `boolean` | `BOOLEAN` | - |
| `char` | `TEXT` | Odoo char can exceed 255 |
| `text` | `TEXT` | - |
| `selection` | `VARCHAR(255)` | Fixed options |
| `date` | `DATE` | - |
| `datetime` | `TIMESTAMP` | - |
| `many2one` | `INTEGER` | Stores related ID only |
| `one2many` | **SKIPPED** | Not stored directly |
| `many2many` | **SKIPPED** | Not stored directly |
| `binary` | **SKIPPED** | Too large, use external storage |
| `html` | `TEXT` | - |
| `reference` | `VARCHAR(255)` | Dynamic reference |

### Field Name Auto-Detection

The platform auto-detects field purpose from name patterns:

| Pattern | Detected As | PostgreSQL Type | Flags |
|---------|-------------|-----------------|-------|
| `id` | Primary Key | `INTEGER` | primary_key, indexed |
| `*_id` | Foreign Key | `INTEGER` | is_foreign_key, indexed |
| `active`, `is_active` | Boolean | `BOOLEAN` | - |
| `write_date`, `create_date`, `date` | Sync Date | `TIMESTAMP` | is_sync_date, indexed |
| `*_ids` | One2many | **SKIPPED** | - |
| Other | Basic | `TEXT` | nullable |

### Many2one Handling

Many2one fields store only the related record's ID:

```
Odoo Field: partner_id (many2one to res.partner)
Value in Odoo: [42, 'Acme Corp']
Value in PostgreSQL: 42
```

Configuration:
```yaml
- odoo_field: partner_id
  postgres_column: partner_id
  postgres_type: INTEGER
  is_foreign_key: true
  indexed: true
```

### One2many Handling

One2many fields are NOT stored - they're the inverse of a many2one:

```
Odoo Field: line_ids (one2many to sale.order.line)
Not stored in sale_order table!
Stored in sale_order_line table with order_id field
```

The platform skips one2many fields. To sync them:
1. Configure the child model separately
2. The relation is maintained via the foreign key

### Many2many Handling

Many2many fields use a relation table in Odoo:

```
Odoo Field: tag_ids (many2many to res.partner.category)
Uses: res_partner_res_partner_category_rel table
Not stored directly in res_partner table!
```

The platform skips many2many fields. To sync them:
1. Sync the relation table directly
2. Or denormalize into the main table

---

## Examples

### Example 1: Simple Model

**Odoo Model:** `res.partner`

**Fields to sync:**
| Technical Name | Type | Label | PG Column | PG Type |
|----------------|------|-------|-----------|---------|
| `id` | integer | ID | `id` | INTEGER |
| `name` | char | Name | `name` | TEXT |
| `email` | char | Email | `email` | TEXT |
| `phone` | char | Phone | `phone` | TEXT |
| `active` | boolean | Active | `active` | BOOLEAN |

**Config:**
```yaml
- odoo_model: res.partner
  postgres_table: res_partner
  fields:
    - id
    - name
    - email
    - phone
    - active
```

### Example 2: Model with Foreign Keys

**Odoo Model:** `sale.order`

**Fields to sync:**
| Technical Name | Type | Label | Related To | PG Column | PG Type |
|----------------|------|-------|------------|-----------|---------|
| `id` | integer | ID | - | `id` | INTEGER |
| `name` | char | Order | - | `name` | TEXT |
| `partner_id` | many2one | Customer | res.partner | `partner_id` | INTEGER |
| `date_order` | datetime | Order Date | - | `date_order` | TIMESTAMP |
| `amount_total` | monetary | Total | - | `amount_total` | NUMERIC(20,4) |
| `state` | selection | Status | - | `state` | VARCHAR(255) |
| `write_date` | datetime | Last Modified | - | `write_date` | TIMESTAMP |

**Config:**
```yaml
- odoo_model: sale.order
  postgres_table: sale_order
  fields:
    - id
    - name
    - partner_id      # Auto-detected as foreign key
    - date_order
    - amount_total    # Auto-detected as monetary -> NUMERIC
    - state
    - write_date      # Auto-detected as sync date
```

### Example 3: Model with Lines

**Odoo Model:** `sale.order.line` (Order Lines)

**Fields to sync:**
| Technical Name | Type | Label | Related To | PG Column | PG Type |
|----------------|------|-------|------------|-----------|---------|
| `id` | integer | ID | - | `id` | INTEGER |
| `order_id` | many2one | Order | sale.order | `order_id` | INTEGER |
| `sequence` | integer | Sequence | - | `sequence` | INTEGER |
| `product_id` | many2one | Product | product.product | `product_id` | INTEGER |
| `product_uom_qty` | float | Quantity | - | `product_uom_qty` | NUMERIC(20,4) |
| `price_unit` | float | Unit Price | - | `price_unit` | NUMERIC(20,4) |
| `price_subtotal` | monetary | Subtotal | - | `price_subtotal` | NUMERIC(20,4) |

**Config:**
```yaml
- odoo_model: sale.order.line
  postgres_table: sale_order_line
  fields:
    - id
    - order_id
    - sequence
    - product_id
    - product_uom_qty
    - price_unit
    - price_subtotal
```

### Example 4: Verbose Field Configuration

When you need explicit control:

```yaml
- odoo_model: product.product
  postgres_table: product_product
  fields:
    - odoo_field: id
      postgres_column: id
      postgres_type: INTEGER
      primary_key: true
      nullable: false
      indexed: true
      
    - odoo_field: name
      postgres_column: name
      postgres_type: TEXT
      nullable: false
      # indexed not set - no index needed
      
    - odoo_field: default_code
      postgres_column: default_code
      postgres_type: VARCHAR(64)
      nullable: true
      indexed: true  # Add index for SKU lookups
      
    - odoo_field: list_price
      postgres_column: list_price
      postgres_type: NUMERIC(20,4)
      nullable: false
      default_value: 0.0
      
    - odoo_field: categ_id
      postgres_column: categ_id
      postgres_type: INTEGER
      is_foreign_key: true
      indexed: true
      field_type: many2one
      related_model: product.category
      
    - odoo_field: write_date
      postgres_column: write_date
      postgres_type: TIMESTAMP
      is_sync_date: true
      indexed: true
```

### Example 5: Discovering Fields

Interactive discovery script:

```python
#!/usr/bin/env python3
"""Discover fields for an Odoo model."""

from src.clients.odoo_client import OdooClient
from src.utils.settings import get_settings

settings = get_settings()
client = OdooClient()
client.authenticate()

model = 'stock.move'

print(f"\n{'='*60}")
print(f"Fields for: {model}")
print(f"{'='*60}\n")

fields = client.get_model_fields(model)

# Categorize by type
by_type = {}
for name, defn in fields.items():
    ftype = defn.get('type', 'unknown')
    if ftype not in by_type:
        by_type[ftype] = []
    by_type[ftype].append((name, defn))

# Print by type
for ftype in sorted(by_type.keys()):
    print(f"\n{ftype.upper()} FIELDS:")
    print("-" * 40)
    for name, defn in sorted(by_type[ftype]):
        label = defn.get('string', '')
        relation = defn.get('relation', '')
        relation_str = f" → {relation}" if relation else ""
        print(f"  {name:30} {label:30}{relation_str}")
```

Output:
```
============================================================
Fields for: stock.move
============================================================

BINARY FIELDS:
----------------------------------------
  barcode   Barcode          

BOOLEAN FIELDS:
----------------------------------------
  active   Active           
  ...
```

---

## Quick Reference

### Field Configuration Checklist

- [ ] Use technical names (not labels)
- [ ] Always include `id` as primary key
- [ ] Include `write_date` for incremental sync
- [ ] Don't include `*_ids` fields (one2many)
- [ ] Don't include `*_id` relation fields (many2many)
- [ ] Use `NUMERIC(20,4)` for monetary/float fields

### Common Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Using label "Customer" | API requires "partner_id" | Use technical name |
| Including `line_ids` | one2many not storable | Skip this field |
| Using `VARCHAR(255)` | Odoo names can be longer | Use `TEXT` |
| Small `NUMERIC` | Odoo values can be > 10B | Use `NUMERIC(20,4)` |
| Missing `id` field | No primary key | Always include `id` |
