# Analytics Architecture

**Generated:** 2026-06-21  
**Purpose:** Dimensional analytics architecture for dashboard reporting

---

## Overview

This document defines the dimensional analytics architecture for the Odoo PostgreSQL data warehouse. The architecture follows a **data mart** pattern, with each mart optimized for specific business domains.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PostgreSQL Data Warehouse                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │    Sales    │  │ Purchasing  │  │Manufacturing│  │  Inventory  │ │
│  │  Data Mart  │  │  Data Mart  │  │  Data Mart  │  │  Data Mart  │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
│         │                │                │                │        │
│         ▼                ▼                ▼                ▼        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │   vw_sales  │  │  vw_purchas │  │   vw_mrp    │  │  vw_invent- │ │
│  │  _summary   │  │  e_summary  │  │  _summary   │  │   ory_sum   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Design Principles

1. **Denormalization**: Views flatten related tables for efficient querying
2. **Business Language**: Column names use business terminology, not Odoo technical terms
3. **Date Intelligence**: Include date parts for easy time-based filtering
4. **Status Clarity**: Include human-readable status descriptions
5. **Optimized for Reads**: Views are optimized for dashboard consumption, not writes

---

## Sales Data Mart

### Business Purpose
Track sales orders, revenue, and customer purchasing patterns. Supports:
- Revenue analysis by period, customer, and product
- Order pipeline monitoring
- Sales performance metrics
- Delivery and invoicing status tracking

### Source Tables
```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   sale_order    │──────►│ sale_order_line │──────►│ product_product │
│                 │  1:M  │                 │  M:1  │                 │
└────────┬────────┘       └─────────────────┘       └────────┬────────┘
         │                                                   │
         │ 1:M                                               │
         ▼                                                   ▼
┌─────────────────┐                               ┌─────────────────┐
│  res_partner    │                               │product_template │
│  (Customer)     │                               │                 │
└─────────────────┘                               └─────────────────┘
```

### Join Relationships
- `sale_order.partner_id` → `res_partner.id` (Customer)
- `sale_order_line.order_id` → `sale_order.id`
- `sale_order_line.product_id` → `product_product.id`
- `product_product.id` → `product_template.id` (if template fields needed)

### Key Performance Indicators (KPIs)

| KPI | Description | Calculation |
|-----|-------------|-------------|
| Total Revenue | Sum of all sales amounts | `SUM(amount_total)` |
| Order Count | Number of orders | `COUNT(*)` |
| Average Order Value | Revenue per order | `SUM(amount_total) / COUNT(*)` |
| Lines per Order | Average order complexity | `COUNT(line_id) / COUNT(DISTINCT order_id)` |
| Units Sold | Total quantities | `SUM(product_uom_qty)` |
| Conversion Rate | % of quotations becoming sales | `COUNT(state='sale') / COUNT(*)` |
| Delivery Rate | % of orders delivered | `COUNT(delivery_status='delivered') / COUNT(*)` |

### Recommended SQL Views

| View Name | Purpose |
|-----------|---------|
| `vw_sales_order_summary` | Order-level summary with customer info |
| `vw_sales_order_lines` | Line-level detail with product info |

---

## Purchasing Data Mart

### Business Purpose
Track purchase orders, vendor performance, and procurement costs. Supports:
- Vendor analysis and performance tracking
- Purchase spend analysis
- Procurement pipeline monitoring
- Cost optimization insights

### Source Tables
```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ purchase_order  │──────►│purchase_order_  │──────►│ product_product │
│                 │  1:M  │     line        │  M:1  │                 │
└────────┬────────┘       └─────────────────┘       └────────┬────────┘
         │                                                   │
         │ 1:M                                               │
         ▼                                                   ▼
┌─────────────────┐                               ┌─────────────────┐
│  res_partner    │                               │product_template │
│  (Vendor)       │                               │                 │
└─────────────────┘                               └─────────────────┘
```

### Join Relationships
- `purchase_order.partner_id` → `res_partner.id` (Vendor)
- `purchase_order_line.order_id` → `purchase_order.id`
- `purchase_order_line.product_id` → `product_product.id`
- `product_product.id` → `product_template.id`

### Key Performance Indicators (KPIs)

| KPI | Description | Calculation |
|-----|-------------|-------------|
| Total Purchase Spend | Sum of all PO amounts | `SUM(amount_total)` |
| PO Count | Number of purchase orders | `COUNT(*)` |
| Average PO Value | Spend per order | `SUM(amount_total) / COUNT(*)` |
| Vendor Count | Unique vendors | `COUNT(DISTINCT partner_id)` |
| Lines per PO | Average PO complexity | `COUNT(line_id) / COUNT(DISTINCT order_id)` |
| Units Purchased | Total quantities | `SUM(product_qty)` |

### Recommended SQL Views

| View Name | Purpose |
|-----------|---------|
| `vw_purchase_summary` | PO-level summary with vendor info |
| `vw_purchase_order_lines` | Line-level detail with product info |

---

## Manufacturing Data Mart

### Business Purpose
Track manufacturing orders, production efficiency, and capacity utilization. Supports:
- Production planning and scheduling
- Manufacturing efficiency metrics
- Capacity planning
- Production yield analysis

### Source Tables
```
┌─────────────────┐       ┌─────────────────┐
│  mrp_production │──────►│ product_product │
│                 │  M:1  │                 │
└────────┬────────┘       └────────┬────────┘
         │                         │
         │                         ▼
         │                ┌─────────────────┐
         │                │product_template │
         │                │                 │
         │                └─────────────────┘
         │
         ▼
┌─────────────────┐
│  stock_move     │ (for component tracking - optional)
│                 │
└─────────────────┘
```

### Join Relationships
- `mrp_production.product_id` → `product_product.id` (Finished product)
- `product_product.id` → `product_template.id`

### Key Performance Indicators (KPIs)

| KPI | Description | Calculation |
|-----|-------------|-------------|
| Production Orders | Count of MOs | `COUNT(*)` |
| Total Output | Sum of finished quantities | `SUM(product_qty)` |
| Completion Rate | % of MOs completed | `COUNT(state='done') / COUNT(*)` |
| In-Progress Count | Active productions | `COUNT(state IN ('confirmed','progress'))` |
| Cycle Time | Average duration | `AVG(date_finished - date_start)` |

### Recommended SQL Views

| View Name | Purpose |
|-----------|---------|
| `vw_mrp_summary` | Production order summary with product info |

---

## Inventory Data Mart

### Business Purpose
Track inventory levels, stock movements, and warehouse operations. Supports:
- Inventory level monitoring
- Stock movement analysis
- Reorder point planning
- Warehouse efficiency metrics

### Source Tables
```
┌─────────────────┐       ┌─────────────────┐
│   stock_quant   │◄──────│ product_product │
│  (On-hand qty)  │  M:1  │                 │
└─────────────────┘       └────────┬────────┘
                                   │
┌─────────────────┐                ▼
│   stock_move    │       ┌─────────────────┐
│  (Movements)    │──────►│product_template │
└────────┬────────┘       └─────────────────┘
         │
         ▼
┌─────────────────┐
│ stock_move_line │
│   (Detailed)    │
└─────────────────┘
```

### Join Relationships
- `stock_quant.product_id` → `product_product.id`
- `stock_move.product_id` → `product_product.id`
- `stock_move_line.product_id` → `product_product.id`
- `stock_move_line.move_id` → `stock_move.id`
- `product_product.id` → `product_template.id`

### Key Performance Indicators (KPIs)

| KPI | Description | Calculation |
|-----|-------------|-------------|
| Total On-Hand | Current inventory value | `SUM(quantity * standard_price)` |
| Reserved Stock | Quantity reserved | `SUM(reserved_quantity)` |
| Available Stock | Free inventory | `SUM(quantity - reserved_quantity)` |
| SKU Count | Unique products tracked | `COUNT(DISTINCT product_id)` |
| Stock Moves | Movement count | `COUNT(*)` |
| Transfers | Internal moves | `COUNT(location_id != location_dest_id)` |

### Recommended SQL Views

| View Name | Purpose |
|-----------|---------|
| `vw_inventory_summary` | Current inventory levels by product |

---

## Common Dimensions

### Date Dimension (Derived)

All views include date parts extracted from transaction dates:

```sql
-- Example date dimension fields
EXTRACT(YEAR FROM date_order) AS order_year,
EXTRACT(QUARTER FROM date_order) AS order_quarter,
EXTRACT(MONTH FROM date_order) AS order_month,
EXTRACT(WEEK FROM date_order) AS order_week,
EXTRACT(DAY FROM date_order) AS order_day,
TO_CHAR(date_order, 'YYYY-MM') AS order_year_month,
TO_CHAR(date_order, 'YYYY-MM-DD') AS order_date
```

### Partner Dimension

Customer and vendor information is joined to provide:
- `partner_name` - Full name
- `partner_email` - Contact email
- `partner_active` - Is active

### Product Dimension

Product information includes:
- `product_name` - Product name
- `product_code` - Internal reference
- `product_type` - Type (consumable, service, storable)
- `list_price` - Sale price
- `standard_price` - Cost price

---

## View Design Patterns

### Pattern 1: Order Summary View
```sql
CREATE VIEW vw_xxx_summary AS
SELECT 
    -- Order header info
    o.id AS order_id,
    o.name AS order_number,
    o.date_order,
    
    -- Date parts for filtering
    EXTRACT(YEAR FROM o.date_order) AS order_year,
    EXTRACT(MONTH FROM o.date_order) AS order_month,
    TO_CHAR(o.date_order, 'YYYY-MM') AS order_year_month,
    
    -- Status
    o.state AS status_code,
    CASE o.state
        WHEN 'draft' THEN 'Draft'
        WHEN 'sent' THEN 'Sent'
        WHEN 'sale' THEN 'Sales Order'
        WHEN 'done' THEN 'Done'
        WHEN 'cancel' THEN 'Cancelled'
    END AS status_name,
    
    -- Partner info
    p.id AS partner_id,
    p.name AS partner_name,
    
    -- Aggregations
    o.amount_total AS total_amount,
    COUNT(l.id) AS line_count,
    SUM(l.product_uom_qty) AS total_quantity
    
FROM source_order o
LEFT JOIN source_order_line l ON l.order_id = o.id
LEFT JOIN res_partner p ON p.id = o.partner_id
GROUP BY o.id, o.name, o.date_order, o.state, p.id, p.name, o.amount_total;
```

### Pattern 2: Line Detail View
```sql
CREATE VIEW vw_xxx_lines AS
SELECT 
    -- Header info
    o.id AS order_id,
    o.name AS order_number,
    o.date_order,
    
    -- Line info
    l.id AS line_id,
    l.name AS line_description,
    l.product_uom_qty AS quantity,
    l.price_unit AS unit_price,
    l.price_subtotal AS line_total,
    
    -- Product info
    pr.id AS product_id,
    pr.name AS product_name,
    pr.default_code AS product_code,
    pt.type AS product_type,
    
    -- Partner info
    p.id AS partner_id,
    p.name AS partner_name
    
FROM source_order o
JOIN source_order_line l ON l.order_id = o.id
LEFT JOIN res_partner p ON p.id = o.partner_id
LEFT JOIN product_product pr ON pr.id = l.product_id
LEFT JOIN product_template pt ON pt.id = pr.product_tmpl_id;
```

---

## Implementation Notes

### Performance Considerations

1. **Indexes**: Ensure indexes exist on:
   - Foreign key columns (order_id, partner_id, product_id)
   - Date columns (date_order, date)
   - Status columns (state)

2. **Materialized Views**: For large datasets, consider:
   - Creating materialized views with scheduled refresh
   - Adding unique indexes on the view for incremental refresh

3. **Query Optimization**:
   - Use `LEFT JOIN` for optional relationships
   - Use `JOIN` only for required relationships
   - Include date filters in queries for better performance

### Data Quality Considerations

1. **NULL Handling**: 
   - Use `COALESCE` for amounts that might be NULL
   - Use `LEFT JOIN` for optional related data

2. **Active Records Only**:
   - Consider filtering `active = true` for partners and products
   - Include `active` flag in views for filtering

### Extensibility

1. **Adding Fields**: To add new fields:
   - Identify the source table
   - Add to the appropriate view
   - Update documentation

2. **New Views**: To create new views:
   - Follow the established patterns
   - Update this architecture document
   - Add to the data catalog

---

## Future Enhancements

1. **Dimensional Tables**: Create explicit dimension tables (dim_date, dim_product, dim_partner)
2. **Fact Tables**: Create aggregated fact tables for common queries
3. **Materialized Views**: Implement scheduled refresh for performance
4. **Data Lineage**: Add source system tracking to views
5. **Incremental Filters**: Add row filtering based on sync timestamps