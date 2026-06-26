# Job Order Cost Rekap SQL Design

## Technical Purpose

This document contains the technical SQL design for the Phase 1 Job Order Cost Rekap views. The business/report specification is kept separately in `JOB_ORDER_COST_REKAP_REPORT.md`.

Phase 1 is operational reconciliation only. It does not implement profitability, margin, COGS, estimator variance, cost variance, stock valuation, accounting profit, or AR/payment logic.

## Confirmed Phase 1 Basis

| Decision | Phase 1 rule |
| --- | --- |
| Report entry point | SO / JO-first. |
| JO model | JO is Job Order, but every JO is still an SO; do not model JO as a separate entity outside SO. |
| Internal Order role | IO is separate from JO and appears only as linked secondary context when relevant. |
| RKB PPIC | Future manual Excel upload/import into SQL staging; not currently in PostgreSQL. |
| RKB Actual | Current/latest Odoo RKB from approval lines where category = `RKB`. |
| Comparison basis | `ODOO_RKB_ACTUAL_BASELINE`. |
| ROP/PEMBELIAN | Same business meaning: procurement request. |

Phase 1 compares Odoo RKB Actual to ROP/PEMBELIAN and PO execution. It does not compare against manually calculated PPIC Excel values until a staging/upload workflow exists.

## Existing Inputs

| Input | Use |
| --- | --- |
| `vw_dashboard_sales_order_traceability` | SO-first report scope, current company filter, source type, customer context. |
| `vw_sale_order_internal_order_bridge` | Secondary SO-to-IO context parsed from `sale_order.x_studio_io_1`. |
| `vw_sales_order_revenue` | SO line product/value context. |
| `vw_rkb_planning_lines` | Odoo RKB Actual baseline. |
| `vw_approval_product_line_context` | ROP/PEMBELIAN procurement-request lines. |
| `vw_procurement_lines` | PO ordered/received/billed quantities and PO values. |

## Source Mapping

### RKB Actual

Use:

```sql
vw_rkb_planning_lines
```

This view is the Phase 1 Odoo RKB Actual source. It represents latest/current RKB planning records in Odoo, not actual material consumption.

Report mapping rule:

1. Link to SO/JO using valid `job_order_number` when available.
2. Link through IO only when an explicit RKB `internal_order_number` matches the SO-to-IO bridge.
3. Do not use `approval_request_numeric_id` as an IO bridge for RKB rows unless a future investigation proves that the row is actually a MANUFACTURE/Internal Order row.

### ROP / PEMBELIAN

Use:

```sql
vw_approval_product_line_context
where approval_business_type = 'ROP_PROCUREMENT_REQUEST'
```

This includes both `ROP` and `PEMBELIAN` categories.

Report mapping rule:

1. Link to SO/JO using valid `job_order_number` when available.
2. Link through IO only when an explicit ROP/PEMBELIAN `internal_order_number` matches the SO-to-IO bridge.
3. Do not use `approval_request_numeric_id` as an IO bridge for ROP/PEMBELIAN rows unless the logic is separately proven.

### PO

Use:

```sql
vw_procurement_lines
```

PO mapping can use valid `job_order_number` or explicit PO `internal_order_number` matched to the SO-to-IO bridge.

PO comparisons are procurement execution comparisons only. They are not stock valuation, COGS, or accounting profit.

## Proposed Views

| View | Purpose |
| --- | --- |
| `vw_job_order_report_scope` | SO / JO-first report scope with IO as linked context. |
| `vw_job_order_odoo_rkb_actual_agg` | Aggregate Odoo RKB Actual from `vw_rkb_planning_lines`. |
| `vw_job_order_rop_agg` | Aggregate ROP/PEMBELIAN from `vw_approval_product_line_context`. |
| `vw_job_order_po_agg` | Aggregate PO execution from `vw_procurement_lines`. |
| `vw_job_order_product_universe` | Product universe across SO, Odoo RKB Actual, ROP, and PO. |
| `vw_job_order_rekap_lines` | One row per report/product for Phase 1 Rekap. |
| `vw_job_order_not_yet_rop` | Odoo RKB Actual quantity not yet covered by ROP/PEMBELIAN. |
| `vw_job_order_excess_rop` | ROP/PEMBELIAN quantity exceeding Odoo RKB Actual baseline. |
| `vw_job_order_po_amount_compare` | ROP vs PO operational amount comparison. |
| `vw_job_order_rekap_summary` | Rekap 2-style summary per report. |

## Grain

Phase 1 grain is:

```text
one row per report_key + product_key
```

`report_key` should be the SO/JO number. Internal Order references are retained as secondary context and join evidence; IO-only records should not become primary report entries in Phase 1.

## Formulas

Phase 1 uses Odoo RKB Actual as the baseline because RKB PPIC is not yet in PostgreSQL.

```sql
not_yet_rop_qty = GREATEST(rkb_actual_qty - rop_qty, 0)
not_yet_rop_amount = not_yet_rop_qty * rkb_actual_unit_price

excess_rop_qty = GREATEST(rop_qty - rkb_actual_qty, 0)
excess_rop_amount = excess_rop_qty * rop_unit_price

po_excess_qty = GREATEST(po_qty - rop_qty, 0)
po_excess_amount = po_excess_qty * po_unit_price

received_ratio = po_received_qty / NULLIF(po_qty, 0)
billed_ratio = po_billed_qty / NULLIF(po_qty, 0)

common_qty = LEAST(rop_qty, po_qty)
rop_value_for_common_qty = common_qty * rop_unit_price
po_value_for_common_qty = common_qty * po_unit_price
po_saving_amount = rop_value_for_common_qty - po_value_for_common_qty
```

`po_saving_amount` is a procurement price comparison, not profit.

## Validation Queries

### Duplicate grain check

```sql
SELECT
    report_key,
    product_key,
    COUNT(*) AS row_count
FROM vw_job_order_rekap_lines
GROUP BY report_key, product_key
HAVING COUNT(*) > 1;
```

Expected: 0 rows.

### Unmapped RKB Actual check

```sql
WITH mapped AS (
    SELECT
        rkb.approval_line_id,
        COALESCE(so_jo.name::text, bridge.so_number::text, rkb.job_order_number::text) AS report_key
    FROM vw_rkb_planning_lines rkb
    LEFT JOIN sale_order so_jo
        ON so_jo.name::text = rkb.job_order_number::text
    LEFT JOIN vw_sale_order_internal_order_bridge bridge
        ON NULLIF(BTRIM(COALESCE(rkb.internal_order_number::text, '')), '') IS NOT NULL
       AND bridge.internal_order_id::text = rkb.internal_order_number::text
    WHERE rkb.is_valid_for_metrics
)
SELECT *
FROM mapped
WHERE report_key IS NULL;
```

### Unmapped ROP/PEMBELIAN check

```sql
WITH mapped AS (
    SELECT
        apl.approval_line_id,
        COALESCE(so_jo.name::text, bridge.so_number::text, apl.job_order_number::text) AS report_key
    FROM vw_approval_product_line_context apl
    LEFT JOIN sale_order so_jo
        ON so_jo.name::text = apl.job_order_number::text
    LEFT JOIN vw_sale_order_internal_order_bridge bridge
        ON NULLIF(BTRIM(COALESCE(apl.internal_order_number::text, '')), '') IS NOT NULL
       AND bridge.internal_order_id::text = apl.internal_order_number::text
    WHERE apl.approval_business_type = 'ROP_PROCUREMENT_REQUEST'
      AND apl.is_valid_for_metrics
)
SELECT *
FROM mapped
WHERE report_key IS NULL;
```

### Unmapped PO check

```sql
WITH mapped AS (
    SELECT
        po.procurement_line_id,
        COALESCE(so_jo.name::text, bridge.so_number::text, po.job_order_number::text) AS report_key
    FROM vw_procurement_lines po
    LEFT JOIN sale_order so_jo
        ON so_jo.name::text = po.job_order_number::text
    LEFT JOIN vw_sale_order_internal_order_bridge bridge
        ON NULLIF(BTRIM(COALESCE(po.internal_order_number::text, '')), '') IS NOT NULL
       AND bridge.internal_order_id::text = po.internal_order_number::text
    WHERE po.is_valid_for_metrics
)
SELECT *
FROM mapped
WHERE report_key IS NULL;
```

### Mixed UoM check

```sql
SELECT
    report_key,
    product_key,
    uom_summary
FROM vw_job_order_rekap_lines
WHERE uom_summary ILIKE '%,%';
```

### PO without ROP check

```sql
SELECT *
FROM vw_job_order_rekap_lines
WHERE po_qty > 0
  AND COALESCE(rop_qty, 0) = 0;
```

### ROP without PO check

```sql
SELECT *
FROM vw_job_order_rekap_lines
WHERE rop_qty > 0
  AND COALESCE(po_qty, 0) = 0;
```

### Cancelled record exclusion check

```sql
SELECT COUNT(*) AS cancelled_scope_rows
FROM vw_job_order_report_scope
WHERE NOT is_valid_for_metrics;
```

Expected: 0 rows.

## Known Risks

- RKB and ROP approval request IDs may represent their own approval documents, not Internal Orders.
- Product display names may differ across SO, RKB, ROP, and PO.
- UoM may be missing or inconsistent, especially because the Excel `RKB Actual` headers are unreliable.
- One SO may link to multiple IOs, and one IO may link to multiple SOs.
- Phase 1 baseline is Odoo RKB Actual, not the future PPIC manual Excel plan.
- SQL has not yet been validated against a known manually prepared Excel report.

## TODOs Before Production Use

- Confirm whether SO number and JO number are always the same in the target report.
- Confirm product key strategy when product display names differ across SO, RKB, ROP, and PO.
- Confirm UoM handling for mixed-UoM products.
- Confirm whether draft/cancelled ROP and PO states should be excluded beyond the current `is_valid_for_metrics` rule.
- Confirm whether only approved ROP/PEMBELIAN lines should count.
- Add the future RKB PPIC staging table and replace the Phase 1 baseline where appropriate.
- Validate SQL output against at least one known manually prepared Excel report.