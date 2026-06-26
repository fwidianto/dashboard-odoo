# Job Order Cost Rekap SQL Design

## Purpose

This document contains the SQL design for the Phase 1 Job Order Cost Rekap views. Keep detailed SQL design here so `JOB_ORDER_COST_REKAP_REPORT.md` can remain the business/report specification.

## Confirmed Phase 1 Basis

| Decision | Phase 1 rule |
| --- | --- |
| Report entry point | SO / JO-first. |
| Internal Order role | Linked secondary context when relevant. |
| RKB PPIC | Future manual Excel upload/import into SQL staging; not currently in PostgreSQL. |
| RKB Actual | Current/latest Odoo RKB from approval lines where category = `RKB`. |
| Comparison basis | `ODOO_RKB_ACTUAL_BASELINE`. |
| Profitability | Out of scope. |

Phase 1 compares Odoo RKB Actual to ROP/PEMBELIAN and PO execution. It does not compare against manually calculated PPIC Excel values until a staging/upload workflow exists.

## Existing Inputs

| Input | Use |
| --- | --- |
| `vw_dashboard_sales_order_traceability` | SO-first report scope, current company filter, source type, customer context. |
| `vw_sale_order_internal_order_bridge` | Secondary SO-to-IO context. |
| `vw_sales_order_revenue` | SO line product/value context. |
| `vw_rkb_planning_lines` | Odoo RKB Actual baseline. |
| `vw_approval_product_line_context` | ROP/PEMBELIAN procurement-request lines. |
| `vw_procurement_lines` | PO ordered/received/billed quantities and PO values. |

## Additive SQL File

Create only new views in:

```text
sql/06_job_order_cost_rekap_views.sql
```

Do not modify existing traceability SQL views, APIs, or frontend files for Phase 1.

## Proposed Views

| View | Purpose |
| --- | --- |
| `vw_job_order_report_scope` | SO / JO-first report scope with IO as linked context. |
| `vw_job_order_odoo_rkb_actual_agg` | Aggregate Odoo RKB Actual from `vw_rkb_planning_lines`. |
| `vw_job_order_rop_agg` | Aggregate ROP/PEMBELIAN from `vw_approval_product_line_context`. |
| `vw_job_order_po_agg` | Aggregate PO execution from `vw_procurement_lines`. |
| `vw_job_order_product_universe` | Product universe across SO, Odoo RKB Actual, ROP, and PO. |
| `vw_job_order_rekap_lines` | One row per report/product for Phase 1 Rekap. |
| `vw_job_order_not_yet_rop` | Odoo RKB Actual quantity not yet covered by ROP. |
| `vw_job_order_excess_rop` | ROP quantity exceeding Odoo RKB Actual baseline. |
| `vw_job_order_po_amount_compare` | ROP vs PO operational amount comparison. |
| `vw_job_order_rekap_summary` | Rekap 2-style summary per report. |

## Grain

Phase 1 grain is:

```text
one row per report_key + product_key
```

`report_key` should be the SO/JO number. Internal Order references are retained as secondary context and join evidence; IO-only records should not become primary report entries in Phase 1.

## Source Mapping

### RKB Actual

Use:

```sql
vw_rkb_planning_lines
```

This is the Odoo baseline. It is not actual material consumption and must not be interpreted as stock valuation or COGS.

### ROP / PEMBELIAN

Use:

```sql
vw_approval_product_line_context
where approval_business_type = 'ROP_PROCUREMENT_REQUEST'
```

`ROP` and `PEMBELIAN` have the same business meaning.

### PO

Use:

```sql
vw_procurement_lines
```

PO comparisons are procurement execution comparisons only.

## Non-Goals

Do not implement:

- frontend/API endpoints
- profitability
- margin
- COGS
- estimator variance
- stock valuation
- accounting profit
- RKB PPIC upload table or import workflow

## TODOs Before Production Use

- Confirm the exact report key when one SO links to multiple IOs.
- Confirm whether SO number and JO number are always the same in the target report.
- Confirm product key strategy when product display names differ across SO, RKB, ROP, and PO.
- Confirm UoM handling for mixed-UoM products.
- Confirm whether draft/cancelled ROP and PO states should be excluded beyond the current `is_valid_for_metrics` rule.
- Add the future RKB PPIC staging table and replace the Phase 1 baseline where appropriate.