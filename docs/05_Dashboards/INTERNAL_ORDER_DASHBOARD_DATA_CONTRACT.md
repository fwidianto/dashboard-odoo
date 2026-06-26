# Internal Order Dashboard Data Contract

## 1. Purpose

This dashboard is for Internal Order-first operational reconciliation.
It is meant for pre-Sales-Order cases such as `426IO026`.
It compares RKB Actual, ROP / PEMBELIAN, and PO.
It must stay separate from the SO/JO Rekap dashboard.
It is not a profitability, COGS, margin, or accounting profit view.

## 2. Dashboard Route Proposal

Proposed future route names only:

- Frontend route: `/dashboard/internal-order-rekap`
- API route: `/api/dashboard/internal-order-rekap`
- Query parameter: `?internal_order_number=426IO026`

Optional future filters:

- `company_name`
- `has_sales_order_link`
- `product_trackability_class`
- `product_presence_status`

## 3. Primary SQL Sources

Primary sources:

- Summary: `vw_internal_order_rekap_summary`
- Lines: `vw_internal_order_rekap_lines`

Supporting sources when drilldown or troubleshooting is needed:

- `vw_internal_order_rekap_scope`
- `vw_internal_order_rkb_actual_agg`
- `vw_internal_order_rop_agg`
- `vw_internal_order_po_agg`
- `vw_internal_order_product_universe`

## 4. Main Dashboard Grain

- Summary grain: one row per `internal_order_number`
- Line grain: one row per `internal_order_number + product_key`
- Different Internal Orders should not be merged unless the dashboard is explicitly in overview mode
- `426IO026` should be queryable as one Internal Order detail page/report

## 5. Header / KPI Cards

Use `vw_internal_order_rekap_summary` for header cards.

1. Internal Order Number
   - field: `internal_order_number`

2. Company
   - field: `company_name`

3. Sales Order Link Status
   - field: `has_sales_order_link`
   - display: `false` = `Pre-SO Internal Order`, `true` = `Linked to Sales Order`

4. Product Count
   - field: `product_count`

5. Full RKB Actual
   - field: `rkb_actual_amount`
   - interpretation: full Odoo RKB Actual amount, including trackable and non-trackable rows

6. Trackable RKB Actual
   - field: `rkb_actual_trackable_amount`
   - interpretation: normal product/material subset; temporary classification uses a 5-digit bracketed product-code proxy

7. Non-Trackable RKB
   - field: `rkb_actual_non_trackable_amount`
   - interpretation: valid RKB rows such as `!! - OTHERS` and budget/service/adjustment rows; not a data error

8. ROP Amount
   - field: `rop_amount`

9. PO Amount
   - field: `po_amount`

10. Not Yet ROP Amount
    - field: `not_yet_rop_amount`

11. Excess ROP Amount
    - field: `excess_rop_amount`

12. PO Received Ratio
    - field: `received_ratio`
    - display `N/A` when null

13. PO Invoiced Ratio
    - field: `invoiced_ratio`
    - display `N/A` when null

14. Mixed UoM Count
    - field: `mixed_uom_count`
    - warning when greater than `0`

## 6. Suggested KPI Interpretation for `426IO026`

Known validation example:

- full RKB Actual: `9,078,236,100.61`
- trackable RKB Actual: `7,476,666,216.61`
- non-trackable RKB: `1,601,569,884.00`
- unknown-class RKB: `0.00`
- ROP amount: `6,428,714,005.63`
- PO amount: `6,111,147,209.98`
- has_sales_order_link: `false`

Interpretation:

- `9.078B` is the full Odoo RKB total.
- `7.477B` is the trackable/product-only subset.
- Both are valid depending on the report purpose.
- The dashboard should show both to avoid confusion.

## 7. Main Line Table

Use `vw_internal_order_rekap_lines` for the main table.

Required columns:

- `internal_order_number`
- `product_key`
- `product_name`
- `product_trackability_class`
- `product_classification_reason`
- `is_trackable_product`
- `product_presence_status`
- `uom_summary`
- `mixed_uom_flag`
- `rkb_actual_qty`
- `rkb_actual_unit_price`
- `rkb_actual_subtotal`
- `rop_qty`
- `rop_unit_price`
- `rop_subtotal`
- `po_qty`
- `po_unit_price`
- `po_subtotal`
- `po_received_qty`
- `po_invoiced_qty`
- `not_yet_rop_qty`
- `not_yet_rop_amount`
- `excess_rop_qty`
- `excess_rop_amount`
- `po_without_rop_flag`
- `rop_without_po_flag`

Suggested default sort:

1. `product_trackability_class`
2. `product_presence_status`
3. descending `rkb_actual_subtotal`
4. `product_key`

## 8. Recommended Detail Tables / Tabs

Suggested logical tabs, all from `vw_internal_order_rekap_lines`.

### A. All Lines

All product rows.

### B. Trackable Products

Filter:

```sql
is_trackable_product = true
```

Purpose: normal material/product comparison.

### C. Non-Trackable / Others

Filter:

```sql
product_trackability_class <> 'TRACKABLE_PRODUCT'
```

Purpose: show valid budget/service/adjustment rows separately.

### D. RKB Only

Filter:

```sql
product_presence_status = 'RKB_ONLY'
```

Purpose: RKB exists but not yet ROP/PO.

### E. RKB + ROP + PO

Filter:

```sql
product_presence_status = 'RKB_ROP_PO'
```

Purpose: fully progressed rows.

### F. ROP Without PO

Filter:

```sql
rop_without_po_flag = true
```

Purpose: procurement request exists but PO is not yet linked or found.

### G. PO Without ROP

Filter:

```sql
po_without_rop_flag = true
```

Purpose: PO exists but ROP is not linked or found.

### H. Mixed UoM

Filter:

```sql
mixed_uom_flag = true
```

Purpose: warn that quantity comparison may be unreliable.

## 9. Product Presence Status Definitions

Operational traceability states:

- `RKB_ONLY`: only RKB exists
- `ROP_ONLY`: only ROP exists
- `PO_ONLY`: only PO exists
- `RKB_ROP`: RKB and ROP exist
- `RKB_PO`: RKB and PO exist
- `ROP_PO`: ROP and PO exist
- `RKB_ROP_PO`: all three exist

These are traceability states, not automatic error states.

## 10. Trackability Class Definitions

Trackability classes:

- `TRACKABLE_PRODUCT`
- `NON_TRACKABLE_OTHERS`
- `BUDGET_SERVICE_ADJUSTMENT`
- `UNKNOWN_PRODUCT_CLASS`

Current trackability is a temporary proxy.
The current heuristic treats only bracketed 5-digit product codes as trackable, such as `[43809]`.
It does not treat all bracketed rows as trackable.

Non-trackable examples:

- `!! - OTHERS (RKB)`
- `[!! - 630411] !! - S.Part & Jasa Untuk Mesin 630411`
- `Jasa Transport [PRC]`
- `Discount [PRC]`
- `Sisa Budget Estimator`

Future source of truth:

- Odoo product trackable / tracking field should replace this heuristic once it is fetched into PostgreSQL.
- When that field exists, SQL should use the Odoo field first and only fall back to the heuristic when the field is missing.

## 11. Warning / Badge Rules

Conceptual badges for the future UI:

- `Pre-SO` when `has_sales_order_link = false`
- `Linked SO` when `has_sales_order_link = true`
- `Mixed UoM` when `mixed_uom_flag = true`
- `Non-Trackable` when `product_trackability_class <> 'TRACKABLE_PRODUCT'`
- `PO Without ROP` when `po_without_rop_flag = true`
- `ROP Without PO` when `rop_without_po_flag = true`
- `RKB Only` when `product_presence_status = 'RKB_ONLY'`

## 12. API Response Shape Proposal

Proposed JSON response shape only.

```json
{
  "internal_order_number": "426IO026",
  "summary": {
    "company_name": "Nobi Putra Angkasa, PT",
    "has_sales_order_link": false,
    "product_count": 418,
    "rkb_actual_amount": 9078236100.61,
    "rkb_actual_trackable_amount": 7476666216.61,
    "rkb_actual_non_trackable_amount": 1601569884.00,
    "rkb_actual_unknown_class_amount": 0.00,
    "rop_amount": 6428714005.63,
    "po_amount": 6111147209.98,
    "not_yet_rop_amount": 2873734605.26,
    "excess_rop_amount": 223771394.36,
    "mixed_uom_count": 0
  },
  "breakdowns": {
    "by_trackability_class": [],
    "by_product_presence_status": []
  },
  "lines": []
}
```

Optional metadata:

- `generated_at`
- `comparison_basis`
- `summary_scope`
- `warnings`

## 13. Validation Queries for API Builder

Summary query:

```sql
SELECT *
FROM vw_internal_order_rekap_summary
WHERE internal_order_number = '426IO026';
```

Line query:

```sql
SELECT *
FROM vw_internal_order_rekap_lines
WHERE internal_order_number = '426IO026'
ORDER BY
    product_trackability_class,
    product_presence_status,
    COALESCE(rkb_actual_subtotal, 0) DESC,
    product_key;
```

Trackability breakdown:

```sql
SELECT
    product_trackability_class,
    product_classification_reason,
    is_trackable_product,
    COUNT(*) AS product_count,
    SUM(rkb_actual_subtotal) AS rkb_actual_amount,
    SUM(rop_subtotal) AS rop_amount,
    SUM(po_subtotal) AS po_amount
FROM vw_internal_order_rekap_lines
WHERE internal_order_number = '426IO026'
GROUP BY
    product_trackability_class,
    product_classification_reason,
    is_trackable_product
ORDER BY
    product_trackability_class,
    product_classification_reason,
    is_trackable_product;
```

Presence breakdown:

```sql
SELECT
    product_presence_status,
    COUNT(*) AS product_count,
    SUM(rkb_actual_subtotal) AS rkb_actual_amount,
    SUM(rop_subtotal) AS rop_amount,
    SUM(po_subtotal) AS po_amount
FROM vw_internal_order_rekap_lines
WHERE internal_order_number = '426IO026'
GROUP BY product_presence_status
ORDER BY product_presence_status;
```

## 14. Out of Scope

Explicitly out of scope:

- frontend implementation
- backend/API implementation
- sync change to fetch the Odoo product trackable field
- profitability
- margin
- COGS
- accounting profit
- RKB PPIC import
- UoM conversion
- changing existing SO/JO Rekap views

## 15. Acceptance Criteria

- New document exists: `docs/05_Dashboards/INTERNAL_ORDER_DASHBOARD_DATA_CONTRACT.md`
- It clearly separates Internal Order Rekap from SO/JO Rekap
- It defines summary fields
- It defines line fields
- It defines tabs/tables
- It defines warning/badge rules
- It defines API response shape proposal
- It includes validation queries
- No SQL logic changes
- No API/frontend implementation
- No private files committed

## 16. Implementation Status

- API endpoint implemented: `/api/dashboard/internal-order-rekap`
- Frontend route implemented: `/dashboard/internal-order-rekap`
- Required parameter: `internal_order_number`
- Frontend uses the API, not direct SQL
- Response follows the `summary`, `breakdowns`, `lines`, and `metadata` shape defined above
- Charts can be improved later
- Product trackability still uses the temporary 5-digit heuristic until the Odoo field is fetched into PostgreSQL

