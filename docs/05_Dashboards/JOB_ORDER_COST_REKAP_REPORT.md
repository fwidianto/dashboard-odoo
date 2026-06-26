# Job Order Cost Rekap SQL Design Specification

## 1. Purpose

This document defines the proposed SQL design for the future Job Order / Project Cost Rekap report.

The report is based on the manual Excel report `Ceking Project Indokordsa.xlsx`, especially:

* `Rekap`
* `Rekap 2`
* `Not Yet ROP`
* `Excess Qty`
* `Amount PO`

This design translates the Excel logic into SQL views, but does not yet implement a final profitability engine.


## Confirmed Phase 1 Decisions

- RKB PPIC is a manually calculated Excel file from PPIC and is not currently available in PostgreSQL.
- RKB PPIC should be handled later through an upload/import workflow into SQL staging tables.
- RKB Actual means the latest RKB updated in Odoo and should come from Odoo approval lines where category = `RKB`.
- Phase 1 comparison basis is `ODOO_RKB_ACTUAL_BASELINE`.
- The report entry point is SO / JO-first.
- Internal Order is linked secondary context when relevant, not the primary report entry point.

## 2. Current Boundary

This report is an operational cost/procurement reconciliation report first.

It must not yet calculate:

* final profitability
* gross margin
* COGS
* accounting-based contribution
* estimator variance
* actual manufacturing cost variance
* AR/payment status

Any fields named `saving`, `excess`, or `contribution` must be treated as operational comparison metrics, not accounting profit.

## 3. Business Flow Covered

The report should compare one Sales Order / Job Order / Internal Order context through these stages:

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

## 4. Important Excel Corrections

### 4.1 Rekap row range

In the Excel `Rekap` sheet, item rows start from row 5.

SQL must not replicate Excel formulas that started from row 6.

All SQL totals must include the first item row equivalent.

In SQL terms, this means:

```text
Aggregate all valid item rows.
Do not exclude the first product row.
```

### 4.2 RKB Actual header correction

The Excel `RKB Actual` sheet headers are unreliable.

Known corrections:

* Subtotal columns I and J should be treated as one subtotal concept.
* Unit of Measurement / UoM is missing.
* SQL must use verified Odoo fields.
* SQL must not blindly copy Excel column labels.

## 5. Proposed Report Grain

Initial proposed grain:

```text
one row per report reference + product
```

More explicitly:

```text
one row per sales_order / internal_order_or_job_reference / product_key
```

Recommended SQL columns:

| Column                  | Purpose                                                            |
| ----------------------- | ------------------------------------------------------------------ |
| `report_reference_type` | `SALES_ORDER`, `JOB_ORDER`, `INTERNAL_ORDER`, or `MIXED_REFERENCE` |
| `sales_order_id`        | Odoo SO ID if available                                            |
| `sales_order_number`    | SO number/name                                                     |
| `internal_order_id`     | Approval request numeric ID if available                           |
| `internal_order_number` | IO approval request display number                                 |
| `job_order_number`      | Valid JO / production SO reference if available                    |
| `product_key`           | Stable product grouping key                                        |
| `product_name`          | Display product name                                               |
| `uom_summary`           | UoM or mixed-UoM diagnostic                                        |
| `source_confidence`     | `HIGH`, `MEDIUM`, `LOW`, `PENDING_REVIEW`                          |

## 6. Reference Strategy

The report must support two business paths.

### 6.1 Make-to-order / JO path

Use when the Sales Order requires production.

Primary references:

```text
sale_order.name
mrp_production.origin
mrp_production.x_studio_nomor_jo
approval_product_line.x_studio_nomor_jo
purchase_order_line.x_studio_jo
```

JO should be treated as a production-required Sales Order reference, not as a separate business object.

### 6.2 Internal Order path

Use when a Sales Order consumes stock previously produced from Internal Order.

Primary references:

```text
approval_product_line.approval_request_id
approval_product_line.approval_request_numeric_id
mrp_production.x_studio_nomor_io
sale_order.x_studio_io_1 parsed through vw_sale_order_internal_order_bridge
purchase_order_line.x_studio_many2one_field_iJ0j0
```

Do not infer IO to SO directly from MO.

Use the existing SO-to-IO bridge where possible.

## 7. Source Tables and Existing Views

Prefer existing Data Truth Layer views over raw tables where available.

### 7.1 Existing views to reuse

| Existing view                              | Usage                                                          |
| ------------------------------------------ | -------------------------------------------------------------- |
| `vw_sales_order_revenue`                   | SO header/line revenue context                                 |
| `vw_dashboard_sales_order_traceability`    | SO dashboard context, company scope, product type, source type |
| `vw_sale_order_internal_order_bridge`      | Many-to-many SO to IO bridge                                   |
| `vw_mrp_order_context`                     | MO context and JO/IO/SO reference classification               |
| `vw_approval_product_line_context`         | Approval line category mapping for RKB, ROP, MANUFACTURE       |
| `vw_rkb_planning_lines`                    | RKB-only planning lines                                        |
| `vw_procurement_lines`                     | PO line procurement context                                    |
| `vw_dashboard_internal_order_traceability` | IO dashboard summary context                                   |

### 7.2 Raw tables likely needed only for detail fallback

| Raw table               | Use                                              |
| ----------------------- | ------------------------------------------------ |
| `sale_order`            | SO header, company filter, customer, order value |
| `sale_order_line`       | SO line product, qty, price, subtotal            |
| `approval_request`      | Approval header / IO display context             |
| `approval_product_line` | RKB, ROP, PEMBELIAN, MANUFACTURE line source     |
| `purchase_order_line`   | PO qty, received qty, unit price, subtotal       |
| `purchase_order`        | PO header if needed later                        |
| `mrp_production`        | MO traceability context                          |
| `product_product`       | Product key/name enrichment if reliable          |
| `product_template`      | Product category/context if reliable             |

## 8. Company Scope

Initial report should follow current project scope:

```text
Nobi Putra Angkasa, PT
```

Apply company filtering consistently where company fields are available:

```sql
company_id::text = 'Nobi Putra Angkasa, PT'
```

Avoid frontend-only filtering for company scope.

## 9. Proposed SQL File

Create a new additive SQL file:

```text
sql/06_job_order_cost_rekap_views.sql
```

This file should not modify existing traceability views.

It should only create new views.

Recommended execution order:

```text
01_base_views.sql
04_dashboard_traceability_views.sql
05_sales_order_dashboard_views.sql
06_job_order_cost_rekap_views.sql
```

## 10. Proposed View Layer

### 10.1 `vw_job_order_report_scope`

Purpose:

Create the report-level reference context.

One row per report reference candidate.

Suggested columns:

| Column                  | Rule                                                            |
| ----------------------- | --------------------------------------------------------------- |
| `report_key`            | Stable text key, usually SO number or IO number                 |
| `report_reference_type` | `SALES_ORDER`, `INTERNAL_ORDER`, `JOB_ORDER`, `MIXED_REFERENCE` |
| `sales_order_id`        | From SO context if available                                    |
| `sales_order_number`    | From SO context if available                                    |
| `internal_order_id`     | From bridge or approval request numeric ID                      |
| `internal_order_number` | Approval request display number / IO number                     |
| `job_order_number`      | Valid 7-digit JO if available                                   |
| `company_name`          | Company scope                                                   |
| `customer_name`         | SO customer if available                                        |
| `source_type`           | SO source type if SO exists                                     |
| `is_valid_for_metrics`  | Cancelled exclusion flag                                        |

Notes:

* For SO-first reports, anchor from `vw_dashboard_sales_order_traceability`.
* For IO-first reports, anchor from `vw_dashboard_internal_order_traceability`.
* Do not force every IO to have SO.
* Do not force every SO to have IO.

### 10.2 `vw_job_order_rkb_ppic_agg`

Purpose:

Represent PPIC planned material requirement.

Status:

```text
Partially pending source confirmation.
```

Possible source options:

1. If RKB PPIC exists in Odoo, map from the verified Odoo source.
2. If RKB PPIC remains outside Odoo, create a future imported staging table.
3. If no source exists yet, expose nullable PPIC fields and mark `rkb_ppic_source_status = 'SOURCE_NOT_IMPLEMENTED'`.

Suggested fields:

| Column                   | Meaning                              |
| ------------------------ | ------------------------------------ |
| `report_key`             | SO/IO/JO report key                  |
| `product_key`            | Product grouping key                 |
| `rkb_ppic_qty`           | Planned PPIC quantity                |
| `rkb_ppic_uom`           | Planned PPIC UoM                     |
| `rkb_ppic_unit_price`    | Planned PPIC unit price              |
| `rkb_ppic_subtotal`      | Planned PPIC subtotal                |
| `rkb_ppic_rop_plan_qty`  | Quantity planned to be ROP/requested |
| `rkb_ppic_source_status` | Source readiness flag                |

### 10.3 `vw_job_order_rkb_actual_agg`

Purpose:

Represent actual Odoo RKB planning lines.

Source:

```text
vw_rkb_planning_lines
```

or

```text
vw_approval_product_line_context
where approval_business_type = 'RKB_PLANNING'
```

Suggested fields:

| Column                  | Source                                     |
| ----------------------- | ------------------------------------------ |
| `report_key`            | Derived from IO/JO/SO reference            |
| `product_key`           | Product field from approval line           |
| `rkb_actual_qty`        | `planned_quantity`                         |
| `rkb_actual_uom`        | `unit_of_measure`                          |
| `rkb_actual_unit_price` | weighted average from `planned_unit_price` |
| `rkb_actual_subtotal`   | sum `planned_subtotal`                     |
| `rkb_actual_line_count` | count approval lines                       |
| `rkb_actual_date_min`   | earliest date of need                      |
| `rkb_actual_date_max`   | latest date of need                        |

Important:

Despite the label `RKB Actual`, this is not actual material consumption. It is actual Odoo RKB/planning record value.

Actual material consumption should remain out of scope until stock valuation and consumption rules are confirmed.

### 10.4 `vw_job_order_rop_agg`

Purpose:

Represent procurement request quantities and values.

Source:

```text
vw_approval_product_line_context
where approval_business_type = 'ROP_PROCUREMENT_REQUEST'
```

This includes both:

```text
ROP
PEMBELIAN
```

Suggested fields:

| Column                 | Source                           |
| ---------------------- | -------------------------------- |
| `report_key`           | Derived from IO/JO/SO reference  |
| `product_key`          | Product field from approval line |
| `rop_qty`              | sum planned/requested quantity   |
| `rop_uom`              | UoM summary                      |
| `rop_unit_price`       | weighted average unit price      |
| `rop_subtotal`         | sum planned subtotal             |
| `rop_date_of_need_min` | earliest date of need            |
| `rop_date_of_need_max` | latest date of need              |
| `rop_line_count`       | count approval lines             |

### 10.5 `vw_job_order_po_agg`

Purpose:

Represent purchase order execution against ROP/IO/JO.

Source:

```text
vw_procurement_lines
```

Suggested fields:

| Column                    | Source                          |
| ------------------------- | ------------------------------- |
| `report_key`              | Derived from IO/JO/SO reference |
| `product_key`             | Product field from PO line      |
| `po_qty`                  | sum ordered quantity            |
| `po_received_qty`         | sum received quantity           |
| `po_billed_qty`           | sum invoiced/billed quantity    |
| `po_uom`                  | UoM summary                     |
| `po_unit_price`           | weighted average unit price     |
| `po_subtotal`             | sum line subtotal               |
| `po_expected_arrival_min` | earliest planned date           |
| `po_expected_arrival_max` | latest planned date             |
| `po_line_count`           | count PO lines                  |
| `po_status_summary`       | distinct PO line states         |

### 10.6 `vw_job_order_product_universe`

Purpose:

Build the complete product list across all report stages.

Union products from:

* SO lines
* RKB PPIC
* RKB Actual
* ROP / PEMBELIAN
* PO

Suggested fields:

| Column                    | Rule                           |
| ------------------------- | ------------------------------ |
| `report_key`              | Report reference               |
| `product_key`             | Normalized product key         |
| `product_name`            | Best available product display |
| `appears_in_so`           | Boolean                        |
| `appears_in_rkb_ppic`     | Boolean                        |
| `appears_in_rkb_actual`   | Boolean                        |
| `appears_in_rop`          | Boolean                        |
| `appears_in_po`           | Boolean                        |
| `uom_summary`             | Distinct UoM values            |
| `product_presence_status` | Diagnostic status              |

Product presence status examples:

| Status                | Meaning                                       |
| --------------------- | --------------------------------------------- |
| `COMPLETE_THROUGH_PO` | Product exists in planning/request/PO         |
| `PLANNED_NOT_ROP`     | Product planned but not requested             |
| `ROP_NOT_PO`          | Requested but not purchased                   |
| `PO_WITHOUT_RKB`      | Purchased but not found in RKB                |
| `SO_ONLY`             | Exists only in SO lines                       |
| `MIXED_UOM_REVIEW`    | Same product appears with multiple UoM values |

### 10.7 `vw_job_order_rekap_lines`

Purpose:

Main SQL equivalent of Excel `Rekap`.

Grain:

```text
one row per report_key + product_key
```

Suggested column groups:

#### Identity

| Column                  |
| ----------------------- |
| `report_key`            |
| `sales_order_number`    |
| `internal_order_number` |
| `job_order_number`      |
| `product_key`           |
| `product_name`          |
| `uom_summary`           |

#### RKB PPIC block

| Column                  |
| ----------------------- |
| `rkb_ppic_qty`          |
| `rkb_ppic_unit_price`   |
| `rkb_ppic_subtotal`     |
| `rkb_ppic_rop_plan_qty` |

#### RKB Actual block

| Column                  |
| ----------------------- |
| `rkb_actual_qty`        |
| `rkb_actual_uom`        |
| `rkb_actual_unit_price` |
| `rkb_actual_subtotal`   |

#### ROP block

| Column                 |
| ---------------------- |
| `rop_qty`              |
| `rop_unit_price`       |
| `rop_subtotal`         |
| `rop_date_of_need_min` |
| `rop_date_of_need_max` |

#### PO block

| Column                    |
| ------------------------- |
| `po_qty`                  |
| `po_unit_price`           |
| `po_subtotal`             |
| `po_received_qty`         |
| `po_billed_qty`           |
| `po_expected_arrival_min` |
| `po_expected_arrival_max` |

#### Comparison fields

| Column               | Formula                                        |
| -------------------- | ---------------------------------------------- |
| `not_yet_rop_qty`    | `GREATEST(rkb_ppic_rop_plan_qty - rop_qty, 0)` |
| `not_yet_rop_amount` | `not_yet_rop_qty * rkb_ppic_unit_price`        |
| `excess_rop_qty`     | `GREATEST(rop_qty - rkb_ppic_rop_plan_qty, 0)` |
| `excess_rop_amount`  | `excess_rop_qty * rop_unit_price`              |
| `po_excess_qty`      | `GREATEST(po_qty - rop_qty, 0)`                |
| `po_excess_amount`   | `po_excess_qty * po_unit_price`                |
| `received_ratio`     | `po_received_qty / NULLIF(po_qty, 0)`          |
| `billed_ratio`       | `po_billed_qty / NULLIF(po_qty, 0)`            |

Fallback rule:

If `rkb_ppic_rop_plan_qty` is not available yet, use `rkb_actual_qty` only as a temporary comparison baseline and mark:

```text
comparison_basis = 'TEMP_RKB_ACTUAL_FALLBACK'
```

Preferred basis:

```text
comparison_basis = 'RKB_PPIC_ROP_PLAN'
```

### 10.8 `vw_job_order_not_yet_rop`

Purpose:

SQL equivalent of Excel `Not Yet ROP`.

Filter:

```sql
not_yet_rop_qty > 0
```

Suggested columns:

| Column                  |
| ----------------------- |
| `report_key`            |
| `product_key`           |
| `product_name`          |
| `rkb_ppic_rop_plan_qty` |
| `rop_qty`               |
| `not_yet_rop_qty`       |
| `unit_price_basis`      |
| `not_yet_rop_amount`    |
| `date_of_need_summary`  |

### 10.9 `vw_job_order_excess_rop`

Purpose:

SQL equivalent of Excel `Excess Qty`.

Filter:

```sql
excess_rop_qty > 0
```

Suggested columns:

| Column                  |
| ----------------------- |
| `report_key`            |
| `product_key`           |
| `product_name`          |
| `rkb_ppic_rop_plan_qty` |
| `rop_qty`               |
| `excess_rop_qty`        |
| `unit_price_basis`      |
| `excess_rop_amount`     |

### 10.10 `vw_job_order_po_amount_compare`

Purpose:

SQL equivalent of Excel `Amount PO`.

Compare ROP value and PO value.

Suggested formulas:

```sql
common_qty = LEAST(COALESCE(rop_qty, 0), COALESCE(po_qty, 0))

rop_value_for_common_qty = common_qty * rop_unit_price

po_value_for_common_qty = common_qty * po_unit_price

po_saving_amount = rop_value_for_common_qty - po_value_for_common_qty

po_excess_qty = GREATEST(po_qty - rop_qty, 0)

po_excess_amount = po_excess_qty * po_unit_price
```

Interpretation:

* Positive `po_saving_amount` means PO price is lower than ROP/planned price for comparable quantity.
* Negative `po_saving_amount` means PO price is higher.
* This is procurement price comparison, not accounting profit.

### 10.11 `vw_job_order_rekap_summary`

Purpose:

SQL equivalent of Excel `Rekap 2`.

Grain:

```text
one row per report_key
```

Suggested metrics:

| Metric                   | Formula                                                        |
| ------------------------ | -------------------------------------------------------------- |
| `sales_order_value`      | Sum SO amount / SO line subtotal for report key                |
| `rkb_ppic_budget_amount` | Sum `rkb_ppic_subtotal`                                        |
| `rkb_ppic_qty`           | Sum `rkb_ppic_qty`                                             |
| `rkb_ppic_rop_plan_qty`  | Sum `rkb_ppic_rop_plan_qty`                                    |
| `rkb_actual_amount`      | Sum `rkb_actual_subtotal`                                      |
| `rkb_actual_qty`         | Sum `rkb_actual_qty`                                           |
| `rop_qty`                | Sum `rop_qty`                                                  |
| `rop_amount`             | Sum `rop_subtotal`                                             |
| `not_yet_rop_qty`        | Sum `not_yet_rop_qty`                                          |
| `not_yet_rop_amount`     | Sum `not_yet_rop_amount`                                       |
| `excess_rop_qty`         | Sum `excess_rop_qty`                                           |
| `excess_rop_amount`      | Sum `excess_rop_amount`                                        |
| `po_qty`                 | Sum `po_qty`                                                   |
| `po_amount`              | Sum `po_subtotal`                                              |
| `po_received_qty`        | Sum `po_received_qty`                                          |
| `po_billed_qty`          | Sum `po_billed_qty`                                            |
| `po_saving_amount`       | Sum from `vw_job_order_po_amount_compare`                      |
| `po_excess_qty`          | Sum PO excess quantity                                         |
| `po_excess_amount`       | Sum PO excess amount                                           |
| `received_ratio`         | `SUM(po_received_qty) / NULLIF(SUM(po_qty), 0)`                |
| `billed_ratio`           | `SUM(po_billed_qty) / NULLIF(SUM(po_qty), 0)`                  |
| `rop_progress_ratio`     | `SUM(rop_qty) / NULLIF(SUM(rkb_ppic_rop_plan_qty), 0)`         |
| `not_yet_rop_ratio`      | `SUM(not_yet_rop_qty) / NULLIF(SUM(rkb_ppic_rop_plan_qty), 0)` |

Do not name these as final profitability metrics.

## 11. Validation Queries

Create validation queries before dashboard/API work.

### 11.1 Row count validation

```sql
SELECT
    report_key,
    COUNT(*) AS rekap_line_count,
    COUNT(DISTINCT product_key) AS distinct_product_count
FROM vw_job_order_rekap_lines
GROUP BY report_key;
```

### 11.2 Total inclusion validation

Purpose: prevent the Excel row-5-vs-row-6 mistake.

```sql
SELECT
    report_key,
    SUM(rkb_ppic_subtotal) AS rkb_ppic_total,
    SUM(rkb_actual_subtotal) AS rkb_actual_total,
    SUM(rop_subtotal) AS rop_total,
    SUM(po_subtotal) AS po_total
FROM vw_job_order_rekap_lines
GROUP BY report_key;
```

Rule:

```text
Totals must aggregate every row in vw_job_order_rekap_lines.
No first-row exclusion is allowed.
```

### 11.3 Duplicate grain validation

```sql
SELECT
    report_key,
    product_key,
    COUNT(*) AS row_count
FROM vw_job_order_rekap_lines
GROUP BY report_key, product_key
HAVING COUNT(*) > 1;
```

Expected:

```text
0 rows
```

If rows exist, the grain is not stable enough.

### 11.4 Mixed UoM validation

```sql
SELECT
    report_key,
    product_key,
    uom_summary
FROM vw_job_order_rekap_lines
WHERE uom_summary ILIKE '%,%';
```

Action:

```text
Review before treating quantity comparisons as valid.
```

### 11.5 PO without ROP validation

```sql
SELECT *
FROM vw_job_order_rekap_lines
WHERE po_qty > 0
  AND COALESCE(rop_qty, 0) = 0;
```

Action:

```text
Review whether PO was created without approval request, linked incorrectly, or uses another reference.
```

### 11.6 ROP without PO validation

```sql
SELECT *
FROM vw_job_order_rekap_lines
WHERE rop_qty > 0
  AND COALESCE(po_qty, 0) = 0;
```

Action:

```text
Procurement follow-up.
```

## 12. Dashboard/API Later

Do not build frontend first.

Recommended later API route:

```text
/api/dashboard/job-order-cost-rekap
```

Recommended later dashboard route:

```text
/dashboard/job-order-cost-rekap
```

Only build these after SQL validation is accepted.

## 13. Implementation Sequence

### Phase 1 - Documentation only

* Save this SQL design spec.
* Review with business/data owner.
* Confirm report grain.
* Confirm RKB PPIC source.
* Confirm RKB Actual source.
* Confirm whether estimator/budget is external or available in Odoo.

### Phase 2 - SQL skeleton

Create:

```text
sql/06_job_order_cost_rekap_views.sql
```

Implement only:

* `vw_job_order_report_scope`
* `vw_job_order_product_universe`
* stage aggregate views
* `vw_job_order_rekap_lines`
* validation queries

No frontend.

### Phase 3 - Summary views

Implement:

* `vw_job_order_rekap_summary`
* `vw_job_order_not_yet_rop`
* `vw_job_order_excess_rop`
* `vw_job_order_po_amount_compare`

### Phase 4 - API/dashboard

Only after SQL numbers are reviewed against at least one known Excel report.

## 14. Open Decisions

Before coding full SQL, confirm:

1. Is RKB PPIC stored in Odoo or only in Excel/manual files?
2. Should RKB Actual be represented by Odoo `approval_product_line` category `RKB`?
3. What is the authoritative report key for a Job Order report: SO number, JO number, IO number, or approval request number?
4. Should `product_key` be product ID, product display text, internal reference, or a normalized combination?
5. How should the report handle the same product with multiple UoMs?
6. Should PO comparison use ordered PO quantity, received quantity, or billed quantity for each KPI?
7. Should draft PO lines be included or excluded?
8. Should only approved ROP/PEMBELIAN lines be included?
9. Is `approval_product_line.x_studio_status = approved` enough, or must `approval_request.request_status` also be checked?
10. Should estimator/budget be imported into a staging table later?

## 15. Acceptance Criteria

The SQL design is ready for implementation only when:

* The report grain is confirmed.
* RKB PPIC source is confirmed.
* RKB Actual source is confirmed.
* Product key logic is confirmed.
* Cancelled records are excluded from active metrics.
* Nobi Putra Angkasa company scope is applied consistently.
* No final profitability or accounting profit is calculated.
* Validation queries are defined before frontend work.
