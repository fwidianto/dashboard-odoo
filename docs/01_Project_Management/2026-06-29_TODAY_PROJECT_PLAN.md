# Today Project Plan - 2026-06-29

Purpose: slow down the next project step and make today's work decision-driven instead of rushing into more SQL or profitability logic.

## 1. Today's Main Goal

Today is a validation and planning day.

The main goal is:

```text
Confirm whether the Sales Order Traceability Dashboard is trustworthy and useful enough to become the main operational dashboard before moving toward cost, rekap, or profitability work.
```

The project already has working traceability dashboards for Internal Orders and Sales Orders. The next risk is expanding too quickly into profitability before the operational traceability layer is accepted.

## 2. Current Scope Boundary

### In Scope Today

| Area | Purpose |
| --- | --- |
| Sales Order dashboard review | Check whether the dashboard answers real operational questions. |
| Main table simplification | Decide which fields belong in the default table versus diagnostics. |
| KPI card review | Confirm whether the KPI cards are useful and understandable. |
| Source classification review | Confirm whether source labels make sense to business users. |
| Product Type filter review | Confirm whether Product Type is useful as a primary filter. |
| Invoice progress anomaly review | Investigate why quantity invoice progress is extremely high. |
| Delay logic review | Decide whether `commitment_date` is acceptable as the delay basis. |
| Decision log | Record accepted items, blocked items, and next actions. |

### Out of Scope Today

| Area | Reason |
| --- | --- |
| Profitability engine | Cost rules and source data are not approved yet. |
| Gross margin | COGS and actual cost logic are not ready. |
| Estimator variance | Estimator or budget source is not integrated yet. |
| Final COGS | Accounting and stock valuation logic are not finalized. |
| AR/payment status | Phase 2A accounting is traceability-only. |
| Job Order Cost Rekap SQL implementation | Report grain and join rules are still proposed, not final. |
| Labor and overhead allocation | Allocation rules are not defined. |

## 3. Today's Work Sequence

## Step 1 - Review Sales Order Dashboard as a Business User

Open:

```text
/dashboard/sales-orders
```

Main review question:

```text
Can VP Operations quickly see which Sales Orders need attention today?
```

Review checklist:

| Question | Decision Needed |
| --- | --- |
| Are KPI cards understandable? | Keep, rename, or remove. |
| Is the main table too wide? | Keep columns or move some to diagnostics. |
| Is Product Type useful? | Keep as primary filter or move to secondary filter. |
| Is Source Type clear? | Keep labels or rename for business users. |
| Is Follow-up Status actionable? | Keep, revise priority, or rename. |
| Should Quantity and Amount progress both be visible? | Keep both or move one to drill-down. |

## Step 2 - Decide Main Table Design

Recommended default table should stay compact and operational.

### Candidate Main Table Columns

| Column | Reason |
| --- | --- |
| SO Number | Main business document. |
| Customer | Helps identify order owner/account. |
| Product Type | Helps product/category review. |
| Source Type | Explains stock, IO, make-to-order, mixed, or unknown source. |
| Delivery % | Main fulfillment health metric. |
| Invoice % | Main billing progress metric. |
| Status | Odoo SO status. |
| Follow-up Status | Converts traceability into action. |

### Candidate Diagnostics-Only Fields

| Field | Reason |
| --- | --- |
| Ordered quantity | Useful proof, but can make the table wide. |
| Delivered quantity | Useful proof, but not always needed in default view. |
| Invoiced quantity | Useful proof, but currently has anomaly risk. |
| Ordered amount | Better for drill-down unless management wants it. |
| Delivered amount | Better for drill-down unless management wants it. |
| Invoiced amount | Better for drill-down unless management wants it. |
| IO count | Useful traceability proof. |
| MO count | Useful traceability proof. |
| Accounting line count | Traceability only, not accounting status. |
| Raw `x_studio_io_1` | Technical diagnostic only. |

## Step 3 - Investigate Invoice Quantity Anomaly

Known issue:

```text
Sales Order quantity invoice progress is extremely high because total qty_invoiced is far above total ordered quantity.
```

Today's goal is not to fix it blindly. Today's goal is to classify the cause.

Possible classifications:

| Cause Type | Meaning | Possible Action |
| --- | --- | --- |
| Valid Odoo behavior | The value is technically correct due to Odoo process or special line behavior. | Keep formula but explain it. |
| Unit of measure mismatch | Ordered quantity and invoiced quantity are not comparable. | Use amount progress or normalize UoM. |
| Service/non-stock line behavior | Service lines may distort quantity progress. | Separate stockable and service lines. |
| Data quality issue | `qty_invoiced` is unreliable for dashboard use. | Prefer invoice status or amount progress. |
| Formula issue | The current formula needs adjustment. | Revise SQL carefully after sample review. |

Suggested sample query goal:

```text
List the top Sales Order lines where qty_invoiced > product_uom_qty, ordered by the largest invoice-to-order ratio.
```

Do not change formula until sample rows are reviewed.

## Step 4 - Review Delay Logic

Current assumed delay logic:

```text
commitment_date < today
and delivery progress < 100%
= delayed delivery
```

Decision needed:

| Option | Meaning |
| --- | --- |
| Accept `commitment_date` | Use it as official delivery promise date. |
| Use customer PO date + delivery time | Better if commitment date is incomplete or unreliable. |
| Use Odoo delivery status only | Simpler, but less precise. |
| Defer delay KPI | Safest if business has not confirmed the rule. |

Recommended temporary label:

```text
Delay based on Commitment Date
```

This makes the dashboard assumption visible.

## Step 5 - Keep Job Order Cost Rekap in Specification Mode

The Job Order Cost Rekap report is important, but today it should not become SQL implementation work.

Before implementing it, confirm:

| Open Decision | Why It Matters |
| --- | --- |
| Exact report grain | Prevents double-counting. |
| Authoritative SO / JO / IO reference | Prevents wrong joins. |
| Estimator / Budget source | Required before variance logic. |
| RKB PPIC vs RKB Actual fields | Required before planning comparison. |
| ROP / PEMBELIAN fields | Required before procurement comparison. |
| PO and receipt fields | Required before remaining/excess calculations. |
| Duplicate product handling | Prevents incorrect totals when product appears multiple times. |
| Accounting role | Should remain traceability-only unless business rule is confirmed. |

## 4. Decision Gate for Today

At the end of today, fill this section.

### Accepted

| Item | Decision | Notes |
| --- | --- | --- |
| KPI cards | TBD |  |
| Product Type filter | TBD |  |
| Source Type labels | TBD |  |
| Follow-up Status | TBD |  |
| Quantity progress | TBD |  |
| Amount progress | TBD |  |
| Delay logic | TBD |  |
| Main table columns | TBD |  |

### Blocked

| Item | Reason | Required Before Continuing |
| --- | --- | --- |
| Profitability | Cost logic not approved. | Traceability and cost source review. |
| Job Order Cost Rekap SQL | Grain and join rules not approved. | Business review of report spec. |
| Accounting-based margin | Accounting linkage is traceability-only. | Confirm revenue, COGS, AR, and payment rules. |
| Estimator variance | Estimator data source is not integrated. | Define import/source of estimator data. |

### Next Actions

| Priority | Action | Owner |
| --- | --- | --- |
| 1 | Review Sales Order dashboard with business-user mindset. | Fauzan / business reviewer |
| 2 | Pull sample rows for invoice quantity anomaly. | Developer / analyst |
| 3 | Decide whether amount progress should be preferred over quantity invoice progress. | Fauzan / business reviewer |
| 4 | Confirm delay field and label. | Fauzan / operations user |
| 5 | Update dashboard/UI only after decisions are made. | Developer |
| 6 | Review Job Order Cost Rekap specification after traceability review. | Fauzan / business reviewer |

## 5. Today's Success Criteria

Today is successful if these questions are answered:

```text
1. Is the Sales Order dashboard accepted as the main operational traceability dashboard?
2. Which default table columns should stay visible?
3. What is the likely cause category of the invoice quantity anomaly?
4. Is commitment_date accepted as the delay basis?
5. Are we still blocked from profitability and Job Order Cost Rekap SQL implementation?
```

If the answer to question 1 is no, the next step is dashboard cleanup.

If the answer to question 1 is yes, the next step is controlled investigation of cost-report readiness, not full profitability implementation.
