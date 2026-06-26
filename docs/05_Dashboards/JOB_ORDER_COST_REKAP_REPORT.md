# Job Order Cost Rekap Report Specification

## Purpose

This document defines the business/report specification for the future Excel-style Job Order / Project Cost Rekap report based on the manually maintained `Ceking Project Indokordsa.xlsx` report.

The Excel file is outside this repository and should not be read by the project code. Confirmed business notes are the source of truth for this document.

## Report Meaning

The report is prepared for one Sales Order / Job Order context.

Important Excel sheets:

| Sheet | Business role |
| --- | --- |
| `Rekap` | Item-level reconciliation layer. |
| `Rekap 2` | Summary and KPI layer. |

The report compares:

```text
Sales Order value
-> Estimator / Budget
-> RKB PPIC
-> RKB Actual
-> ROP / Procurement Request
-> PO
-> Received Qty
-> Remaining / Excess / Saving / Contribution
```

## Current Dashboard Boundary

Current dashboards remain traceability-only.

Do not implement in the current dashboards:

- profitability engine
- margin calculation
- COGS
- estimator variance
- cost variance
- stock valuation
- accounting-based profit logic
- AR/payment logic

The existing Sales Order Traceability Dashboard remains scoped to `Nobi Putra Angkasa, PT`; PT Nobi Elektrika Sejahtera remains excluded at SQL view level.

## Excel Corrections To Preserve

In the `Rekap` sheet, totals should start from row 5, not row 6. Future SQL must not copy Excel formulas that accidentally exclude row 5.

In the `RKB Actual` sheet, headers are unreliable:

- Subtotal columns I and J should be treated as one subtotal concept.
- Unit of Measurement / UoM is missing.
- Future SQL should use verified Odoo fields instead of blindly trusting Excel headers.

## Confirmed Phase 1 Decisions

- JO means Job Order, but every JO is still an SO.
- JO must not be modeled as a separate entity outside SO.
- IO remains separate from JO.
- Report entry point is SO / JO-first.
- Internal Order is linked secondary context when relevant.
- RKB PPIC is a manual Excel file calculated by PPIC.
- RKB PPIC is not currently in PostgreSQL.
- RKB PPIC will later be imported/uploaded into a SQL staging table.
- RKB Actual means the current/latest RKB updated in Odoo.
- RKB Actual source is Odoo approval lines where category = `RKB`.
- ROP and PEMBELIAN have the same business meaning.
- Phase 1 baseline is `ODOO_RKB_ACTUAL_BASELINE`.

## Proposed Report Grain

The proposed grain is:

```text
one row per sales_order_or_job_order / product
```

Internal Order may appear as linked secondary context, but should not become the primary Phase 1 report entry point.

This grain must still be validated before production use, especially when one SO links to multiple IOs or the same product appears with different UoMs or descriptions.

## Likely Source Tables

| Table | Likely use |
| --- | --- |
| `sale_order` | Sales Order header, customer, company scope, and SO/JO identity. |
| `sale_order_line` | SO products, quantities, prices, and line values. |
| `approval_request` | Approval header context for RKB, ROP, PEMBELIAN, and IO references. |
| `approval_product_line` | RKB Actual and ROP/PEMBELIAN item lines. |
| `purchase_order` | PO header context if needed later. |
| `purchase_order_line` | PO product, quantity, received quantity, billed quantity, price, subtotal, and status. |
| `product_product` | Product variant bridge if product IDs are needed. |
| `product_template` | Product master attributes if needed. |
| `mrp_production` | Manufacturing / JO / IO traceability context if needed. |

Accounting tables are later/future traceability inputs only and are not part of Phase 1 profitability or costing logic.

## Approval Category Interpretation

| Category | Interpretation |
| --- | --- |
| `RKB` | Odoo RKB Actual / current RKB planning baseline. |
| `ROP` | Procurement request. |
| `PEMBELIAN` | Same business meaning as ROP. |
| `MANUFACTURE` | Internal Order. |
| `INTERNAL USE` | Out of current scope. |

## Proposed Future SQL Views

Detailed SQL design belongs in `docs/05_Dashboards/JOB_ORDER_COST_REKAP_SQL_DESIGN.md`.

Proposed Phase 1 views:

| View | Business purpose |
| --- | --- |
| `vw_job_order_report_scope` | SO / JO-first report scope with IO as linked context. |
| `vw_job_order_odoo_rkb_actual_agg` | Odoo RKB Actual aggregate baseline. |
| `vw_job_order_rop_agg` | ROP/PEMBELIAN aggregate. |
| `vw_job_order_po_agg` | PO execution aggregate. |
| `vw_job_order_product_universe` | Product universe across SO, RKB Actual, ROP, and PO. |
| `vw_job_order_rekap_lines` | Item-level `Rekap` output. |
| `vw_job_order_not_yet_rop` | RKB Actual items not yet covered by ROP/PEMBELIAN. |
| `vw_job_order_excess_rop` | ROP/PEMBELIAN exceeding RKB Actual baseline. |
| `vw_job_order_po_amount_compare` | Operational ROP vs PO amount comparison. |
| `vw_job_order_rekap_summary` | `Rekap 2` summary layer. |

## Open Decisions Before Production Use

- Confirm whether SO number and JO number are always the same in the target report.
- Confirm product key strategy across SO, RKB, ROP/PEMBELIAN, and PO.
- Confirm handling for the same product with multiple UoMs.
- Confirm whether draft ROP/PEMBELIAN or PO lines should be included.
- Confirm whether only approved ROP/PEMBELIAN lines should count.
- Confirm future RKB PPIC staging-table structure and upload workflow.
- Validate SQL output against at least one known manually prepared Excel report.

## Non-Goals

Do not implement in Phase 1:

- frontend
- API
- profitability
- margin
- COGS
- estimator variance
- cost variance
- stock valuation
- accounting profit
- AR/payment logic

Any saving, excess, or contribution fields are operational comparison metrics, not accounting profit.