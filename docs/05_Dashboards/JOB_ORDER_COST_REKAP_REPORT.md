# Job Order Cost Rekap Report Specification

## 1. Purpose

This document defines the proposed future SQL report for the manually maintained Excel report `Ceking Project Indokordsa.xlsx`.

The Excel file is outside this repository and should not be read by the project code. This specification uses confirmed business notes as the source of truth.

This is a specification only. It does not implement a profitability engine, margin calculation, COGS, estimator variance, cost variance, or accounting-based profit logic.

## 2. Report Meaning

The Excel report is manually prepared for one Sales Order / Job Order.

The most important sheets are:

| Sheet | Business role |
| --- | --- |
| `Rekap` | Item-level reconciliation layer. |
| `Rekap 2` | Summary and KPI layer. |

The future SQL report should compare the project from commercial value through planning, procurement, receipt, and remaining quantity/value positions:

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

## 3. Current Dashboard Boundary

The current dashboards remain traceability-only.

Do not implement in the current Sales Order dashboard:

- profitability engine
- margin calculation
- COGS
- estimator variance
- cost variance
- accounting-based profit logic

The existing Sales Order Traceability Dashboard remains scoped to:

```text
Nobi Putra Angkasa, PT
```

PT Nobi Elektrika Sejahtera remains excluded at SQL view level.

## 4. Excel Corrections To Preserve

### Rekap Totals

In the `Rekap` sheet, totals should start from row 5, not row 6.

Future SQL logic must not copy Excel formulas that start from row 6. Row 5 must be included in item-level totals and reconciliation checks.

### RKB Actual Headers

The `RKB Actual` sheet headers are unreliable:

- Subtotal columns I and J should be treated as one subtotal concept.
- Unit of Measurement / UoM is missing.
- The SQL implementation must not blindly trust the Excel headers.
- Later SQL should use verified Odoo fields instead of copied Excel header labels.

## 5. Proposed Report Grain

This grain is proposed, not final:

```text
one row per SO or IO + product_id
```

More formally:

```text
one row per sales_order / internal_order_or_job_reference / product
```

This must be verified before final SQL implementation, especially where one Sales Order maps to multiple Internal Orders or where a product appears in more than one planning/procurement path.

## 6. Likely Source Tables

The first implementation will likely need these operational tables:

| Table | Likely use |
| --- | --- |
| `sale_order` | Sales Order header, company scope, customer, commercial value, Job Order references. |
| `sale_order_line` | Sales Order products, quantities, prices, and line values. |
| `approval_request` | Approval header context for RKB, ROP, PEMBELIAN, MANUFACTURE, and Internal Order references. |
| `approval_product_line` | RKB/ROP/IO item lines, categories, quantities, requested products, and planning/procurement context. |
| `purchase_order` | PO header context. |
| `purchase_order_line` | PO product, quantity, received quantity, billed quantity, price, subtotal, and procurement status. |
| `product_product` | Product variant bridge. |
| `product_template` | Product master attributes and product category context. |
| `mrp_production` | Possible manufacturing / Job Order / Internal Order traceability context. |

Accounting tables should be treated as later/future inputs only. They may be referenced for traceability notes, but they are not part of the first report specification unless a confirmed business rule requires them.

## 7. Approval Category Interpretation

Use the existing confirmed business rules:

| Category | Interpretation |
| --- | --- |
| `RKB` | PPIC material planning / budget comparison. |
| `ROP` | Procurement request. |
| `PEMBELIAN` | Same business meaning as ROP. |
| `MANUFACTURE` | Internal Order. |
| `INTERNAL USE` | Out of current scope. |

## 8. Proposed Future SQL Views

These objects are proposed for a later implementation. They should not be created until the report grain and join rules are reviewed.

| View | Proposed purpose |
| --- | --- |
| `vw_job_order_product_universe` | Build the reconciled product universe across SO/IO, RKB, ROP, PO, and receipts. |
| `vw_job_order_rekap_lines` | Item-level `Rekap` output, one row per verified report grain. |
| `vw_job_order_rekap_summary` | `Rekap 2` summary/KPI layer. |
| `vw_job_order_not_yet_rop` | Items planned/budgeted but not yet requested through ROP/PEMBELIAN. |
| `vw_job_order_excess_rop` | Items where ROP/PEMBELIAN exceeds planned or required position. |
| `vw_job_order_po_amount_compare` | Compare ROP/approved procurement values to PO values and received position. |

## 9. Open Decisions Before SQL

Before implementation, confirm:

- Whether the report grain is truly one row per `sales_order / internal_order_or_job_reference / product`.
- Which Odoo field is the authoritative Job Order / Internal Order reference for this report.
- How Estimator / Budget data is represented in Odoo or whether it remains outside the database.
- Which quantity and amount fields should represent RKB PPIC, RKB Actual, ROP/PEMBELIAN, PO, and received quantity.
- How to handle products appearing multiple times under the same SO/IO with different descriptions, UoM, suppliers, or procurement stages.
- Whether `mrp_production` is required in the first version or only used as traceability context.
- Whether any accounting table is needed for traceability notes only, without profit or COGS logic.

## 10. Non-Goals

The first SQL implementation must not calculate:

- final profitability
- gross margin
- COGS
- estimator variance
- cost variance
- accounting-based contribution or profit

Any saving, excess, or contribution fields in the first report must be explicitly defined as operational comparison metrics, not accounting profit.